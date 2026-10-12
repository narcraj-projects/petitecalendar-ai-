import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.config import Settings
from app.email_worker import EmailWorker
from app.host_email_worker import HostEmailWorker
from app.integrations.email import EmailError
from app.integrations.google import TokenVault
from app.services.host_notification import host_notification_payload
from cryptography.fernet import Fernet


def booking():
    return {
        "id": str(uuid4()),
        "user_id": uuid4(),
        "revision": 1,
        "status": "confirmed",
        "start_at": datetime(2026, 10, 25, 1, 30, tzinfo=UTC),
        "duration": 30,
        "invitee_name": "Guest <script>",
        "invitee_email": "guest@example.com",
        "invitee_timezone": "Europe/London",
        "meet_url": "https://meet.google.com/abc-defg-hij",
        "snapshot": {
            "title": "Project <review>\r\n",
            "host_name": "Host",
            "host_timezone": "Asia/Kolkata",
            "location": "Online",
        },
    }


def settings():
    return Settings(
        app_base_url="https://app.example.com",
        email_from="bookings@example.com",
        resend_api_key="synthetic",
        token_encryption_key=Fernet.generate_key().decode(),
    )


def test_host_receives_separate_message_with_own_zone_guest_details_and_authenticated_link():
    payload = host_notification_payload(booking(), "host@example.com", settings())
    assert payload["to"] == ["host@example.com"] and "cc" not in payload and "bcc" not in payload
    assert "guest@example.com" in payload["text"] and "Asia/Kolkata" in payload["text"]
    assert "Europe/London" in payload["text"] and "07:00" in payload["text"]
    assert "https://app.example.com/app/bookings" in payload["text"]
    assert "/booking/" not in payload["text"] and "#" not in payload["text"]
    assert "<script>" not in payload["html"] and "&lt;script&gt;" in payload["html"]
    assert "\r" not in payload["subject"] and "\n" not in payload["subject"]


@pytest.mark.parametrize(
    "base",
    ["http://public.example.com", "https://app.example.com/path", "https://app.example.com?x=1"],
)
def test_host_notification_rejects_unsafe_dashboard_origin(base):
    with pytest.raises(EmailError):
        host_notification_payload(booking(), "host@example.com", Settings(app_base_url=base))


def test_host_without_verified_contact_fails_without_sending_to_guest():
    with pytest.raises(EmailError) as error:
        host_notification_payload(booking(), None, settings())
    assert error.value.code == "host_contact_unavailable" and error.value.permanent


def test_host_and_guest_delivery_keys_are_independent():
    job = {"booking_id": uuid4(), "revision": 1, "event_type": "booking_confirmed"}
    host, guest = HostEmailWorker.__new__(HostEmailWorker), EmailWorker.__new__(EmailWorker)
    assert host.delivery_key(job).startswith("host-booking-confirmed/")
    assert guest.delivery_key(job).startswith("booking-confirmed/")
    assert host.delivery_key(job) != guest.delivery_key(job)
    assert host.job_table != guest.job_table


def test_host_retry_keeps_frozen_recipient_body_and_key_after_contact_changes():
    worker = HostEmailWorker.__new__(HostEmailWorker)
    worker.settings = settings()
    value = booking()
    job = {
        "booking_id": value["id"],
        "user_id": value["user_id"],
        "revision": 1,
        "event_type": "booking_confirmed",
        "frozen_at": None,
        "payload_ciphertext": None,
        "created_at": datetime.now(UTC),
    }
    worker.load = lambda _: (value, None)
    builds, sends, finishes = [], [], []

    def build(*_):
        builds.append(True)
        return host_notification_payload(value, "original-host@example.com", worker.settings)

    def freeze(_, payload, now):
        job["payload_ciphertext"] = TokenVault(worker.settings.token_encryption_key).seal(
            value["user_id"], json.dumps(payload)
        )
        job["frozen_at"] = now
        return True

    def send(payload, key):
        sends.append((payload, key))
        if len(sends) == 1:
            raise EmailError(ambiguous=True)
        return "provider-fixture"

    worker.build_payload, worker.freeze = build, freeze
    worker.provider = SimpleNamespace(send=send)
    worker.finish = lambda *_, **kw: finishes.append(kw)
    worker.deliver(job)
    worker.build_payload = lambda *_: pytest.fail(
        "Frozen retry must not resolve a new host address"
    )
    worker.deliver(job)
    assert len(builds) == 1 and sends[0] == sends[1]
    assert sends[1][0]["to"] == ["original-host@example.com"]
    assert finishes[-1]["provider_id"] == "provider-fixture"
