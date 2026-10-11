import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from app.api.availability import ScheduleInput
from app.api.bookings import BookingInput
from app.api.events import EventInput
from app.config import get_settings
from app.db.availability import ScheduleRepository
from app.db.bookings import Booking, BookingRepository
from app.db.events import EventRepository
from app.services.availability import public_slots
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1", reason="Opt-in development database test"
)
def test_booking_race_idempotency_caps_capability_and_isolation():
    repo = BookingRepository(get_settings().database_url)
    events = EventRepository(get_settings().database_url)
    schedules = ScheduleRepository(get_settings().database_url)
    host, other = uuid4(), uuid4()
    username = "booking-check-" + uuid4().hex[:12]
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    day = (now + timedelta(days=3)).date()

    def body(start, **kw):
        return BookingInput(
            start=start,
            duration=30,
            timezone="UTC",
            name="Booking fixture",
            email="fixture@example.com",
            idempotency_key=uuid4(),
            capability=uuid4().hex + uuid4().hex,
            **kw,
        )

    try:
        with repo.engine.begin() as c:
            c.execute(
                text("INSERT INTO auth.users(id) VALUES (:host),(:other)"),
                {"host": host, "other": other},
            )
            c.execute(
                text("""INSERT INTO app_private.host_profiles
                (user_id,display_name,username,timezone)
                VALUES (:host,'Booking fixture',:username,'UTC'),
                       (:other,'Other fixture',:othername,'UTC')"""),
                {
                    "host": host,
                    "other": other,
                    "username": username,
                    "othername": username + "-other",
                },
            )
        values = EventInput(
            title="Booking fixture",
            slug="test-call",
            durations=[30],
            default_duration=30,
            notice_minutes=0,
            buffer_before=15,
            buffer_after=15,
            max_per_day=2,
        ).model_dump()
        event = events.save_event(host, values)
        events.save_event(host, values | {"published": True}, event["id"], 1)
        payload = ScheduleInput(
            revision=0,
            timezone="UTC",
            enabled=True,
            weekly=[{"weekday": i, "start": "09:00", "end": "17:00"} for i in range(7)],
            focus=[],
            overrides=[],
            increment_minutes=15,
            host_daily_cap=2,
            weekly_cap_minutes=60,
            prefer_cluster=True,
        ).model_dump(mode="json", exclude={"revision"})
        schedules.save(host, payload, 0)
        start = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=10)
        attempts = [body(start), body(start)]
        barrier = Barrier(2)

        def reserve(b):
            barrier.wait(timeout=15)
            try:
                return repo.reserve(username, "test-call", b, now=now)
            except HTTPException as e:
                return e.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, attempts))
        assert sum(isinstance(r, dict) for r in results) == 1
        assert results.count(409) == 1
        index = next(i for i, r in enumerate(results) if isinstance(r, dict))
        saved = results[index]
        original = attempts[index]
        assert repo.reserve(username, "test-call", original, now=now)["id"] == saved["id"]
        changed = original.model_copy(update={"name": "Changed fixture"})
        with pytest.raises(HTTPException) as conflict:
            repo.reserve(username, "test-call", changed, now=now)
        assert conflict.value.status_code == 409
        assert (
            repo.manage(UUID(saved["id"]), original.capability)["snapshot"]["buffer_before"] == 15
        )
        with pytest.raises(HTTPException) as invalid:
            repo.manage(UUID(saved["id"]), "0" * 64)
        assert invalid.value.status_code == 404
        row = schedules.public_schedule(username, "test-call")
        occupied = repo.occupancy(row, day, day)
        slots = public_slots(
            row,
            start_date=day,
            end_date=day,
            timezone="UTC",
            duration=30,
            now=now,
            occupancy=occupied,
        )
        assert start.isoformat() not in [s["start"] for s in slots["slots"]]
        # Own before-buffer still overlaps the earlier buffered reservation.
        with pytest.raises(HTTPException):
            repo.reserve(username, "test-call", body(start + timedelta(minutes=45)), now=now)
        # Different non-overlapping times still compete for the final aggregate cap slot.
        with ThreadPoolExecutor(max_workers=2) as pool:
            capped_race = list(
                pool.map(
                    reserve, [body(start + timedelta(hours=2)), body(start + timedelta(hours=4))]
                )
            )
        assert sum(isinstance(r, dict) for r in capped_race) == 1
        assert capped_race.count(409) == 1
        second = next(r for r in capped_race if isinstance(r, dict))
        with pytest.raises(HTTPException):
            repo.reserve(username, "test-call", body(start + timedelta(hours=4)), now=now)
        # The next local day is also blocked by the weekly minute cap.
        with pytest.raises(HTTPException):
            repo.reserve(username, "test-call", body(start + timedelta(days=1)), now=now)
        occupied = repo.occupancy(row, day, day)
        assert not public_slots(
            row,
            start_date=day,
            end_date=day,
            timezone="UTC",
            duration=30,
            now=now,
            occupancy=occupied,
        )["slots"]
        assert repo.dashboard(other, day, day + timedelta(days=1))["bookings"] == []
        assert len(repo.dashboard(host, day, day + timedelta(days=1))["bookings"]) == 2
        # Database exclusion protects even a writer that omits the service lock/recheck.
        with repo.engine.begin() as c:
            source = (
                c.execute(select(Booking.__table__).where(Booking.id == UUID(second["id"])))
                .mappings()
                .one()
            )
            replacement = dict(source, id=uuid4(), idempotency_key=uuid4())
            with pytest.raises(IntegrityError):
                with c.begin_nested():
                    c.execute(Booking.__table__.insert().values(**replacement))
            assert (
                c.execute(
                    text("SELECT count(*) FROM app_private.booking_outbox WHERE user_id=:id"),
                    {"id": host},
                ).scalar_one()
                == 2
            )
            repo._set_actor(c, other)
            assert c.execute(select(Booking.id).where(Booking.user_id == host)).all() == []
        # Policy edits do not rewrite saved confirmation; exact retry works after unpublishing.
        events.save_event(
            host, values | {"published": False, "title": "Changed title"}, event["id"], 2
        )
        assert (
            repo.reserve(username, "test-call", original, now=now)["snapshot"]["title"]
            == "Booking fixture"
        )
    except SQLAlchemyError:
        pytest.fail(
            "Booking database check failed; SQL details and credentials withheld.", pytrace=False
        )
    finally:
        # Only these random synthetic fixture IDs are removed; concurrency needs committed rows.
        with repo.engine.begin() as c:
            c.execute(text("DELETE FROM app_private.bookings WHERE user_id=:host"), {"host": host})
            c.execute(
                text("DELETE FROM app_private.availability WHERE user_id=:host"), {"host": host}
            )
            c.execute(
                text("DELETE FROM app_private.event_types WHERE user_id=:host"), {"host": host}
            )
            c.execute(
                text("DELETE FROM app_private.host_profiles WHERE user_id IN (:host,:other)"),
                {"host": host, "other": other},
            )
            c.execute(
                text("DELETE FROM auth.users WHERE id IN (:host,:other)"),
                {"host": host, "other": other},
            )
