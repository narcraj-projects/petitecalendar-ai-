from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from app.api.bookings import LifecycleInput
from app.config import Settings
from app.db.bookings import get_booking_repository
from app.integrations.google import CalendarError, GoogleCalendar, calendar_event_id
from app.main import app
from app.services.booking_email import confirmation_payload
from app.services.calendar import get_calendar_service
from app.services.icalendar import calendar_file
from app.services.lifecycle import require_action
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.exceptions import HTTPException


@pytest.mark.parametrize("operation", ["cancellation", "reschedule"])
def test_saved_cutoff_and_host_override(operation):
    start = datetime(2026, 11, 1, 10, tzinfo=UTC)
    row = {"status": "confirmed", "start_at": start, "snapshot": {operation + "_hours": 12}}
    require_action(row, operation, start - timedelta(hours=12, seconds=1))
    with pytest.raises(HTTPException) as e:
        require_action(row, operation, start - timedelta(hours=12))
    assert e.value.detail["code"] == "POLICY_DEADLINE"
    require_action(row, operation, start - timedelta(seconds=1), host=True)
    with pytest.raises(HTTPException):
        require_action(row, operation, start, host=True)
    with pytest.raises(HTTPException):
        require_action(row | {"status": "cancelled"}, operation, start - timedelta(days=2))


def test_change_inputs_reject_naive_duplicate_and_unbounded_dates():
    base = {"action": "reschedule", "revision": 1, "idempotency_key": uuid4()}
    for candidates in (
        ["2026-11-01T10:00:00"],
        ["2026-11-01T10:00:00Z"] * 2,
        ["2026-11-01T10:00:00Z", "2027-11-01T10:00:00Z"],
    ):
        with pytest.raises(ValidationError):
            LifecycleInput(**base, candidates=candidates)
    with pytest.raises(ValidationError):
        LifecycleInput(**base, timezone="Invalid/Timezone")


def test_excluding_own_event_preserves_overlapping_external_and_all_day_events():
    booking_id = uuid4()
    own_id = calendar_event_id(booking_id, 1)
    start = datetime(2026, 11, 1, 10, tzinfo=UTC)
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.params["singleEvents"] == "true"
        assert request.url.params["fields"].find("description") == -1
        if "pageToken" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "nextPageToken": "second",
                    "timeZone": "Asia/Kolkata",
                    "items": [
                        {
                            "id": own_id,
                            "start": {"dateTime": start.isoformat()},
                            "end": {"dateTime": (start + timedelta(minutes=30)).isoformat()},
                            "extendedProperties": {
                                "private": {
                                    "petitecalendarBooking": str(booking_id),
                                    "petitecalendarRevision": "1",
                                }
                            },
                        },
                        {
                            "id": "external",
                            "start": {"dateTime": start.isoformat()},
                            "end": {"dateTime": (start + timedelta(minutes=15)).isoformat()},
                        },
                        {"id": "transparent", "transparency": "transparent"},
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "timeZone": "Asia/Kolkata",
                "items": [
                    {
                        "id": "all-day",
                        "start": {"date": "2026-11-02"},
                        "end": {"date": "2026-11-03"},
                    }
                ],
            },
        )

    provider = GoogleCalendar(Settings(), httpx.Client(transport=httpx.MockTransport(respond)))
    busy = provider.busy_without_booking(
        "synthetic", "fixture", start, start + timedelta(days=3), booking_id, {own_id: 1}
    )
    assert len(busy) == 2 and busy[0].end == start + timedelta(minutes=15)
    assert busy[1].start == datetime(2026, 11, 1, 18, 30, tzinfo=UTC)
    assert len(calls) == 2
    provider.close()


@pytest.mark.parametrize("delete_status", [204, 404, 410, 412, 503])
def test_owned_delete_etag_and_safe_retry(delete_status):
    booking_id = uuid4()

    def respond(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "etag": '"revision"',
                    "extendedProperties": {
                        "private": {
                            "petitecalendarBooking": str(booking_id),
                            "petitecalendarRevision": "1",
                        }
                    },
                },
            )
        assert request.method == "DELETE" and request.headers["if-match"] == '"revision"'
        assert request.url.params["sendUpdates"] == "none"
        return httpx.Response(delete_status)

    provider = GoogleCalendar(Settings(), httpx.Client(transport=httpx.MockTransport(respond)))
    if delete_status in (412, 503):
        with pytest.raises(CalendarError):
            provider.delete_owned_event("synthetic", "fixture", booking_id, 1)
    else:
        provider.delete_owned_event("synthetic", "fixture", booking_id, 1)
    provider.close()


def test_delete_never_deletes_unowned_event():
    provider = GoogleCalendar(
        Settings(),
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"extendedProperties": {"private": {}}})
            )
        ),
    )
    with pytest.raises(CalendarError) as e:
        provider.delete_owned_event("synthetic", "fixture", uuid4(), 1)
    assert e.value.code == "event_changed"
    provider.close()


def test_cancelled_and_rescheduled_ics_and_notification():
    start = datetime(2026, 11, 1, 10, tzinfo=UTC)
    row = {
        "id": str(uuid4()),
        "revision": 3,
        "status": "cancelled",
        "start_at": start,
        "end_at": start + timedelta(minutes=30),
        "created_at": start - timedelta(days=10),
        "updated_at": start - timedelta(days=2),
        "duration": 30,
        "invitee_email": "fixture@example.com",
        "invitee_timezone": "UTC",
        "snapshot": {
            "title": "Call",
            "host_name": "Fixture",
            "host_timezone": "UTC",
            "location": "Online",
        },
    }
    payload = confirmation_payload(
        row, "", Settings(app_base_url="http://127.0.0.1:8017"), "booking_cancelled"
    )
    assert payload["subject"] == "Booking cancelled: Call"
    assert "/booking/" not in payload["text"] and "original confirmation" in payload["text"]
    raw = calendar_file(row)
    assert b"STATUS:CANCELLED" in raw and b"SEQUENCE:3" in raw
    assert b"DTSTAMP:20261030T100000Z" in raw
    moved = calendar_file(
        row
        | {
            "status": "confirmed",
            "revision": 4,
            "start_at": start + timedelta(days=1),
            "end_at": start + timedelta(days=1, minutes=30),
        }
    )
    assert f"UID:{row['id']}@petitecalendar".encode() in moved and b"SEQUENCE:4" in moved


def test_lifecycle_api_requires_private_capability_and_host_auth():
    app.dependency_overrides[get_booking_repository] = lambda: object()
    app.dependency_overrides[get_calendar_service] = lambda: object()
    try:
        client = TestClient(app)
        path = f"/api/bookings/{uuid4()}"
        body = {"action": "cancel", "revision": 1, "idempotency_key": str(uuid4())}
        result = client.post(path + "/actions", json=body)
        assert result.status_code == 404 and result.headers["cache-control"] == "no-store"
        assert (
            client.get(
                path + "/slots?start_date=2026-11-01&end_date=2026-11-02&timezone=UTC"
            ).status_code
            == 404
        )
        assert (
            client.post(path.replace("/api/", "/api/me/") + "/actions", json=body).status_code
            == 401
        )
        result = client.post(path + "/actions", json=body | {"capability": "a" * 64})
        assert result.status_code == 422 and "a" * 64 not in result.text
    finally:
        app.dependency_overrides.clear()
