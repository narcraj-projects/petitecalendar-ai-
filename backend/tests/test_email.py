import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from app.config import Settings
from app.db.bookings import get_booking_repository
from app.email_worker import EmailWorker
from app.integrations.email import EmailError, ResendEmail
from app.main import app
from app.services.booking_email import confirmation_payload
from app.services.icalendar import calendar_file
from fastapi.testclient import TestClient


def booking():
    return {
        "id": str(uuid4()),
        "user_id": uuid4(),
        "revision": 1,
        "status": "confirmed",
        "start_at": datetime(2026, 10, 25, 1, 30, tzinfo=UTC),
        "end_at": datetime(2026, 10, 25, 2, 15, tzinfo=UTC),
        "created_at": datetime(2026, 10, 11, 6, tzinfo=UTC),
        "duration": 45,
        "invitee_name": "Fixture",
        "invitee_email": "fixture@example.com",
        "invitee_timezone": "Europe/London",
        "meet_url": "https://meet.google.com/abc-defg-hij",
        "snapshot": {
            "title": "Plan, test; review",
            "host_name": "Fixture host",
            "host_timezone": "Asia/Kolkata",
            "location": "Online",
        },
    }


def settings():
    return Settings(
        resend_api_key="synthetic-key",
        email_from="Fixture <onboarding@resend.dev>",
        token_encryption_key="synthetic-key",
    )


def test_ics_utc_dst_stable_uid_and_no_private_capability():
    value = booking()
    data = calendar_file(value).decode().replace("\r\n ", "")
    assert "DTSTART:20261025T013000Z\r\n" in data
    assert "DTEND:20261025T021500Z\r\n" in data
    assert "DTSTAMP:20261011T060000Z\r\n" in data
    assert "UID:" + value["id"] + "@petitecalendar\r\n" in data
    assert "01:30 GMT (+0000)" in data and "07:00 IST (+0530)" in data
    assert "SUMMARY:Plan\\, test\\; review" in data
    assert "mailto:" not in data and value["invitee_email"] not in data
    assert "/booking/" not in data
    before = calendar_file(value | {"meet_url": None}).decode()
    assert before.split("UID:")[1].split("\r\n")[0] == data.split("UID:")[1].split("\r\n")[0]


def test_ics_unicode_folding_and_property_injection_protection():
    value = booking()
    value["snapshot"]["title"] = "\u00e9\U0001f680" * 70 + "\r\nATTENDEE:injected"
    raw = calendar_file(value)
    assert all(len(line) <= 75 for line in raw.split(b"\r\n"))
    unfolded = raw.decode().replace("\r\n ", "")
    assert "\r\nATTENDEE:" not in unfolded
    assert "\\nATTENDEE:injected" in unfolded
    assert "\u00e9\U0001f680" * 70 in unfolded


def test_email_escapes_content_has_both_zones_private_link_and_ics():
    value = booking()
    value["snapshot"]["title"] = '<script>alert("x")</script>'
    payload = confirmation_payload(value, "a" * 64, settings())
    assert "<script>" not in payload["html"] and "&lt;script&gt;" in payload["html"]
    assert "Europe/London" in payload["text"] and "Asia/Kolkata" in payload["text"]
    assert f"/booking/{value['id']}#" + "a" * 64 in payload["text"]
    attachment = base64.b64decode(payload["attachments"][0]["content"]).decode()
    assert "DTSTART:20261025T013000Z" in attachment and "a" * 64 not in attachment
    assert payload["to"] == ["fixture@example.com"]


@pytest.mark.parametrize("base", ["http://public.example.com", "https://example.com?x=1"])
def test_email_rejects_unsafe_base_url(base):
    with pytest.raises(EmailError):
        confirmation_payload(booking(), "a" * 64, Settings(app_base_url=base))


def test_resend_retries_use_identical_payload_and_idempotency_key():
    seen = []

    def handler(request):
        seen.append((request.content, request.headers["Idempotency-Key"]))
        if len(seen) == 1:
            raise httpx.ReadTimeout("synthetic", request=request)
        return httpx.Response(200, json={"id": "provider-fixture"})

    provider = ResendEmail(settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(EmailError) as error:
        provider.send({"text": "fixture"}, "stable-fixture")
    assert error.value.ambiguous
    assert provider.send({"text": "fixture"}, "stable-fixture") == "provider-fixture"
    assert seen[0] == seen[1]
    provider.close()


@pytest.mark.parametrize(
    "status,code,permanent",
    [
        (401, "sender_configuration", True),
        (403, "sender_configuration", True),
        (422, "invalid_email", True),
        (429, "rate_limited", False),
        (409, "idempotency_conflict", False),
        (500, "provider_unavailable", False),
    ],
)
def test_resend_failure_redaction(status, code, permanent):
    provider = ResendEmail(
        settings(),
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(status, json={"message": "sensitive-provider-details"})
            )
        ),
    )
    with pytest.raises(EmailError) as error:
        provider.send({}, "fixture")
    assert error.value.code == code and error.value.permanent == permanent
    assert "sensitive-provider-details" not in str(error.value)
    provider.close()


def test_expired_email_retry_window_never_sends():
    worker = EmailWorker.__new__(EmailWorker)
    row = booking()
    job = {"revision": 1, "frozen_at": datetime.now(UTC) - timedelta(hours=23)}
    worker.claim = lambda host=None: job
    worker.load = lambda job: (row, None)
    finishes = []
    worker.finish = lambda job, **kw: finishes.append(kw)
    worker.deliver(job)
    assert finishes[0]["uncertain"] and finishes[0]["error"].code == "retry_window_expired"


def test_pending_meet_defers_email_before_freezing():
    worker = EmailWorker.__new__(EmailWorker)
    job = {
        "revision": 1,
        "frozen_at": None,
        "payload_ciphertext": None,
        "created_at": datetime.now(UTC),
    }
    worker.claim = lambda host=None: job
    worker.load = lambda job: (booking(), {"status": "working"})
    deferred = []
    worker.defer = lambda job: deferred.append(job)
    worker.deliver(job)
    assert deferred == [job]


def test_private_calendar_download_authentication_and_headers():
    value = booking()

    def manage(id, capability):
        assert capability == "a" * 64
        return value

    app.dependency_overrides[get_booking_repository] = lambda: SimpleNamespace(manage=manage)
    try:
        client = TestClient(app)
        path = f"/api/bookings/{value['id']}/calendar.ics"
        assert client.get(path).status_code == 404
        response = client.get(path, headers={"X-Booking-Capability": "a" * 64})
        assert response.status_code == 200 and response.content == calendar_file(value)
        assert response.headers["content-type"].startswith("text/calendar")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert value["id"] in response.headers["content-disposition"]
    finally:
        app.dependency_overrides.clear()


def test_calendar_only_cli_does_not_start_email_delivery(monkeypatch):
    from app import worker

    calendar = SimpleNamespace(
        settings=SimpleNamespace(email_configured=True),
        provider=SimpleNamespace(close=lambda: None),
        run_once=lambda: False,
    )
    monkeypatch.setattr(worker, "CalendarWorker", lambda: calendar)

    def forbidden_email_worker():
        raise AssertionError("Email delivery must remain disabled in calendar-only mode")

    monkeypatch.setattr(worker, "EmailWorker", forbidden_email_worker)
    monkeypatch.setattr("sys.argv", ["worker", "--once", "--calendar-only"])
    worker.main()
