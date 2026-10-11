from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.api.invitations import InvitationInput
from app.auth import HostIdentity, current_host
from app.config import Settings
from app.db.invitations import get_invitation_repository
from app.integrations.email import EmailError
from app.invitation_worker import InvitationWorker
from app.main import app
from app.services.event_invitation import invitation_payload
from fastapi.testclient import TestClient
from pydantic import ValidationError

ACTOR = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(autouse=True)
def clear():
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "values",
    [
        [],
        ["bad"],
        ["a@b.com", "A@B.COM"],
        ["a@b.com"] * 11,
        ["x" * 255 + "@example.com"],
        ["guest@example.com\r\nBcc: attacker@example.com"],
    ],
)
def test_invalid_recipients(values):
    with pytest.raises(ValidationError):
        InvitationInput(revision=1, recipients=values, idempotency_key=uuid4())


def test_authenticated_actor_and_normalized_recipients():
    seen = []

    class Repo:
        def queue(self, actor, event, body):
            seen.append((actor, event, body.recipients))
            return {"id": str(body.idempotency_key), "counts": {"queued": 2}}

    app.dependency_overrides[current_host] = lambda: HostIdentity(ACTOR, "")
    app.dependency_overrides[get_invitation_repository] = lambda: Repo()
    event = uuid4()
    response = TestClient(app).post(
        f"/api/me/event-types/{event}/invitations",
        json={
            "revision": 1,
            "recipients": [" B@example.com ", "a@example.com"],
            "idempotency_key": str(uuid4()),
        },
    )
    assert response.status_code == 200
    assert seen == [(ACTOR, event, ["a@example.com", "b@example.com"])]


def test_unauthenticated_sharing_is_rejected():
    app.dependency_overrides[get_invitation_repository] = lambda: object()
    response = TestClient(app).post(
        f"/api/me/event-types/{uuid4()}/invitations",
        json={"revision": 1, "recipients": ["guest@example.com"], "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 401


def test_branded_payload_escapes_content_and_has_only_public_link():
    payload = invitation_payload(
        {"display_name": "<script>Host</script>", "username": "host"},
        {"title": "Review <img src=x>", "slug": "review", "durations": [30, 45]},
        "guest@example.com",
        Settings(app_base_url="https://app.example.com", email_from="bookings@example.com"),
    )
    assert payload["to"] == ["guest@example.com"]
    assert "<script>" not in payload["html"] and "&lt;script&gt;" in payload["html"]
    assert "https://app.example.com/host/review" in payload["text"]
    assert "This invitation has not reserved a time" in payload["text"]
    assert "Choose a time" in payload["html"] and "#c8f25c" in payload["html"]
    assert "/booking/" not in payload["html"] and "attachments" not in payload


@pytest.mark.parametrize(
    "base",
    [
        "http://evil.example",
        "https://example.com?next=x",
        "https://example.com/path",
        "javascript:alert(1)",
    ],
)
def test_unsafe_email_origin(base):
    with pytest.raises(EmailError):
        invitation_payload({}, {}, "guest@example.com", Settings(app_base_url=base))


def test_worker_stops_after_deduplication_window():
    worker = InvitationWorker.__new__(InvitationWorker)
    finishes = []
    worker.finish = lambda job, **kwargs: finishes.append(kwargs)
    worker.deliver({"frozen_at": datetime.now(UTC) - timedelta(hours=23)})
    assert finishes[0]["uncertain"] and finishes[0]["error"].code == "retry_window_expired"
