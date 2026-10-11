from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.api.bookings import BookingInput
from app.auth import HostIdentity, current_host
from app.db.bookings import digest, get_booking_repository, occupancy_from_rows
from app.main import app
from fastapi.testclient import TestClient
from pydantic import ValidationError


def request_data(**changes):
    return {
        "start": "2026-10-12T05:30:00Z",
        "duration": 45,
        "timezone": "Asia/Kolkata",
        "name": "Fixture Invitee",
        "email": "fixture@example.com",
        "idempotency_key": str(uuid4()),
        "capability": "a" * 64,
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"start": "2026-10-12T05:30:00"},
        {"timezone": "wrong"},
        {"email": "bad"},
        {"duration": True},
        {"name": "a"},
        {"capability": "short"},
        {"owner": "fake"},
    ],
)
def test_booking_validation(changes):
    with pytest.raises(ValidationError):
        BookingInput(**request_data(**changes))


def test_occupancy_uses_current_schedule_zone_and_all_event_buffers():
    event, other = uuid4(), uuid4()
    start = datetime(2026, 10, 12, 23, 30, tzinfo=UTC)
    rows = [
        {
            "start_at": start,
            "blocked_start": start - timedelta(minutes=10),
            "blocked_end": start + timedelta(minutes=60),
            "event_id": e,
            "duration": 45,
        }
        for e in (event, other)
    ]
    occupied = occupancy_from_rows(rows, event, "Asia/Kolkata")
    assert occupied.host_counts == {date(2026, 10, 13): 2}
    assert occupied.event_counts == {date(2026, 10, 13): 1}
    assert occupied.week_minutes == {date(2026, 10, 12): 90}
    assert len(occupied.reservations) == 2
    assert occupied.reservations[0].start == start - timedelta(minutes=10)


def test_booking_api_auth_capability_and_private_headers():
    class Repo:
        def reserve(self, username, slug, body, **kwargs):
            assert body.name == "Fixture Invitee"
            return {"id": str(uuid4()), "status": "confirmed"}

        def manage(self, booking_id, capability):
            assert capability == "a" * 64
            return {"id": str(booking_id)}

        def dashboard(self, actor, start, end):
            assert actor == UUID("11111111-1111-4111-8111-111111111111")
            return {"bookings": []}

    app.dependency_overrides[get_booking_repository] = lambda: Repo()
    try:
        client = TestClient(app)
        assert client.get("/api/me/bookings?start=2026-10-01&end=2026-11-01").status_code == 401
        app.dependency_overrides[current_host] = lambda: HostIdentity(
            UUID("11111111-1111-4111-8111-111111111111"), None
        )
        assert client.get("/api/me/bookings?start=2026-10-01&end=2027-11-01").status_code == 422
        assert client.get("/api/me/bookings?start=2026-10-01&end=2026-11-01").status_code == 200
        path = "/api/bookings/" + str(uuid4())
        assert client.get(path).status_code == 404
        response = client.get(path, headers={"X-Booking-Capability": "a" * 64})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert (
            client.post(
                "/api/public/events/fixture/test-call/bookings", json=request_data()
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/public/events/ananya/career-strategy/bookings", json=request_data()
            ).status_code
            == 409
        )
    finally:
        app.dependency_overrides.clear()


def test_capability_is_hash_only():
    assert digest("a" * 64) != "a" * 64
    assert len(digest("a" * 64)) == 64
