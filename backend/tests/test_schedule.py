from dataclasses import replace
from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest
from app.api.availability import ScheduleInput
from app.auth import HostIdentity, current_host
from app.db.availability import get_schedule_repository
from app.domain.availability import Interval, Occupancy, Rules, Window, get_slot_report
from app.main import app
from fastapi.testclient import TestClient

PAYLOAD = {
    "revision": 0,
    "timezone": "Asia/Kolkata",
    "enabled": True,
    "weekly": [{"weekday": 0, "start": "09:00", "end": "17:00"}],
    "overrides": [],
    "focus": [],
    "increment_minutes": 15,
    "host_daily_cap": 4,
    "weekly_cap_minutes": 720,
    "prefer_cluster": False,
}


@pytest.mark.parametrize(
    "changes",
    [
        {"timezone": "Mars/Unknown"},
        {"revision": -1},
        {"increment_minutes": 7},
        {"host_daily_cap": 0},
        {"weekly_cap_minutes": -1},
        {"enabled": "true"},
        {"user_id": "someone-else"},
        {"weekly": [{"weekday": 0, "start": "17:00", "end": "09:00"}]},
        {
            "weekly": [
                {"weekday": 0, "start": "09:00", "end": "12:00"},
                {"weekday": 0, "start": "11:00", "end": "14:00"},
            ]
        },
        {"focus": [{"weekday": 8, "start": "09:00", "end": "11:00"}]},
        {
            "overrides": [
                {"date": "2026-10-12", "windows": []},
                {"date": "2026-10-12", "windows": []},
            ]
        },
    ],
)
def test_bad_schedule_rejected(changes):
    with pytest.raises(ValueError):
        ScheduleInput(**(PAYLOAD | changes))


def test_schedule_api_uses_verified_actor():
    actor = UUID("11111111-1111-4111-8111-111111111111")
    calls = []

    class Repo:
        def load(self, user):
            calls.append(user)
            return None

        def save(self, user, payload, revision):
            calls.append((user, revision))
            return payload | {"revision": 1}

    app.dependency_overrides[current_host] = lambda: HostIdentity(actor, "")
    app.dependency_overrides[get_schedule_repository] = lambda: Repo()
    try:
        client = TestClient(app)
        assert client.get("/api/me/availability?user_id=other").json() == {"schedule": None}
        assert client.put("/api/me/availability", json=PAYLOAD).json()["schedule"]["revision"] == 1
        assert (
            client.put("/api/me/availability", json=PAYLOAD | {"user_id": "other"}).status_code
            == 422
        )
        assert calls == [actor, (actor, 0)]
    finally:
        app.dependency_overrides.clear()


def test_schedule_requires_authentication():
    assert TestClient(app).get("/api/me/availability").status_code == 401


def report(rules, day, occupancy=Occupancy()):
    return get_slot_report(
        rules,
        occupancy,
        start_date=day,
        end_date=day,
        invitee_timezone=rules.timezone,
        duration_minutes=60,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )


def rules():
    return Rules(
        "UTC",
        (Window(0, time(9), time(17)),),
        increment_minutes=60,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
        notice_minutes=0,
        horizon_days=365,
    )


def test_closed_override_and_custom_date_hours_replace_weekly_hours():
    monday = date(2026, 10, 12)
    tuesday = date(2026, 10, 13)
    r = replace(rules(), overrides={monday: (), tuesday: (Window(0, time(10), time(12)),)})
    assert report(r, monday).slots == ()
    assert [s.start.hour for s in report(r, tuesday).slots] == [10, 11]


def test_focus_blocks_explain_exclusions():
    r = replace(rules(), focus_windows=(Window(0, time(11), time(12)),))
    result = report(r, date(2026, 10, 12))
    assert 11 not in [s.start.hour for s in result.slots]
    assert result.excluded["focus_blocks"] > 0


def test_weekly_cap_limits_candidates_without_limiting_choice_count():
    result = report(replace(rules(), weekly_cap_minutes=60, host_daily_cap=1), date(2026, 10, 12))
    assert len(result.slots) == 8
    assert report(replace(rules(), weekly_cap_minutes=30), date(2026, 10, 12)).slots == ()


def test_clustering_recommends_without_removing_valid_slots():
    busy = Interval(datetime(2026, 10, 12, 12, tzinfo=UTC), datetime(2026, 10, 12, 13, tzinfo=UTC))
    normal = report(rules(), date(2026, 10, 12), Occupancy(busy=(busy,)))
    clustered = report(
        replace(rules(), prefer_cluster=True), date(2026, 10, 12), Occupancy(busy=(busy,))
    )
    assert normal.slots == clustered.slots
    assert {11, 13} <= {t.hour for t in clustered.recommended}
    assert not report(replace(rules(), prefer_cluster=True), date(2026, 10, 12)).recommended


def test_focus_boundary_in_dst_gap_protects_real_remaining_hour():
    day = date(2026, 3, 8)
    r = replace(
        rules(),
        timezone="America/New_York",
        windows=(Window(6, time(1), time(5)),),
        focus_windows=(Window(6, time(2, 30), time(4)),),
    )
    result = report(r, day)
    from zoneinfo import ZoneInfo

    assert 3 not in [s.start.astimezone(ZoneInfo(r.timezone)).hour for s in result.slots]
    assert result.excluded["focus_blocks"] > 0


def test_explanations_do_not_include_days_outside_requested_range():
    result = report(rules(), date(2026, 10, 12))
    assert "closed_days" not in result.excluded


def test_published_slot_endpoint_and_duration_validation(monkeypatch):
    from types import SimpleNamespace

    from app import main
    from app.api.events import EventInput

    payload = ScheduleInput(**PAYLOAD).model_dump(mode="json", exclude={"revision"})
    row = EventInput(
        title="Test event",
        slug="test-call",
        durations=[30, 45, 60],
        default_duration=45,
        notice_minutes=0,
    ).model_dump() | {"payload": payload, "user_id": UUID("11111111-1111-4111-8111-111111111111")}

    class Repo:
        def public_schedule(self, username, slug):
            return row

    monkeypatch.setattr(main, "get_schedule_repository", lambda: Repo())
    monkeypatch.setattr(
        main, "get_booking_repository", lambda: SimpleNamespace(occupancy=lambda *args: Occupancy())
    )

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, zone=None):
            return datetime(2026, 10, 11, tzinfo=UTC)

    monkeypatch.setattr(main, "datetime", FixedDateTime)
    monkeypatch.setitem(
        app.dependency_overrides,
        main.get_calendar_service,
        lambda: SimpleNamespace(busy=lambda *args: SimpleNamespace(stamp=None, busy=())),
    )
    client = TestClient(app)
    path = "/api/public/events/test-host/test-call/slots"
    params = {
        "start_date": "2026-10-12",
        "end_date": "2026-10-12",
        "timezone": "Asia/Kolkata",
        "duration": 45,
    }
    response = client.get(path, params=params)
    assert response.status_code == 200
    assert response.json()["mode"] == "published"
    assert response.json()["slots"][0]["start"] == "2026-10-12T03:45:00+00:00"
    assert client.get(path, params=params | {"duration": 120}).status_code == 422
    assert (
        client.get(
            path, params=params | {"start_date": "9999-12-31", "end_date": "9999-12-31"}
        ).status_code
        == 422
    )
