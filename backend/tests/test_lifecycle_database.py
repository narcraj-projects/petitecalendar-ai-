import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from app.api.availability import ScheduleInput
from app.api.bookings import BookingInput, LifecycleInput
from app.api.events import EventInput
from app.config import get_settings
from app.db.availability import ScheduleRepository
from app.db.bookings import BookingRepository
from app.db.calendar import CalendarRepository
from app.db.events import EventRepository
from app.domain.availability import Interval
from app.email_worker import EmailWorker
from app.integrations.google import CalendarItem, TokenVault, calendar_event_id
from app.services.calendar import CalendarService
from app.services.lifecycle import LifecycleService
from app.worker import CalendarWorker
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1", reason="Opt-in development database test"
)
def test_lifecycle_atomic_replacement_approval_races_and_delivery(monkeypatch):
    settings = replace(
        get_settings(),
        token_encryption_key=Fernet.generate_key().decode(),
        resend_api_key="synthetic",
        email_from="Fixture <onboarding@resend.dev>",
    )
    monkeypatch.setattr("app.db.bookings.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.lifecycle.get_settings", lambda: settings)
    repo = BookingRepository(settings.database_url)
    calendars = CalendarRepository(settings.database_url)
    host, other = uuid4(), uuid4()
    username = "lifecycle-check-" + uuid4().hex[:10]
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = now + timedelta(days=4, hours=10)
    events = EventRepository(settings.database_url)
    vault = TokenVault(settings.token_encryption_key)

    class Provider:
        blocked = ()
        created, deleted = [], []

        def access_token(self, refresh):
            assert refresh == "synthetic-refresh"
            return "synthetic-access"

        def free_busy(self, token, ids, lower, upper):
            return self.blocked

        def busy_without_booking(self, token, dest, lower, upper, booking_id, excluded):
            assert calendar_event_id(booking_id, 1) in excluded
            return self.blocked

        def ensure_event(self, token, dest, booking, meet):
            assert "invitee_email" not in booking
            self.created.append((booking["id"], booking["revision"]))
            return {
                "event_id": calendar_event_id(booking["id"], booking["revision"]),
                "meet_url": "https://meet.google.com/abc-defg-hij",
            }

        def delete_owned_event(self, token, dest, booking_id, revision):
            self.deleted.append((booking_id, revision))

    provider = Provider()
    calendar = CalendarService(calendars, provider, settings)
    service = LifecycleService(repo, calendar)
    worker = CalendarWorker(repo.engine, provider, settings)
    email_calls = []

    class EmailProvider:
        def send(self, payload, key):
            email_calls.append((payload, key))
            return "synthetic-provider-id"

    email_worker = EmailWorker(repo.engine, EmailProvider(), settings)

    def reserve(time):
        body = BookingInput(
            start=time,
            duration=30,
            timezone="UTC",
            name="Fixture",
            email="fixture@example.com",
            idempotency_key=uuid4(),
            capability=uuid4().hex + uuid4().hex,
        )
        return repo.reserve(username, "test-call", body, now, calendar), body.capability

    def action(kind, revision, **values):
        return LifecycleInput(action=kind, revision=revision, idempotency_key=uuid4(), **values)

    try:
        with repo.engine.begin() as c:
            c.execute(
                text("INSERT INTO auth.users(id) VALUES (:host),(:other)"),
                {"host": host, "other": other},
            )
            c.execute(
                text("""INSERT INTO app_private.host_profiles
                    (user_id,display_name,username,timezone) VALUES
                    (:host,'Lifecycle fixture',:name,'UTC'),
                    (:other,'Other fixture',:othername,'UTC')"""),
                {"host": host, "other": other, "name": username, "othername": username + "-other"},
            )
        calendars.connect(
            host,
            "fixture",
            vault.seal(host, "synthetic-refresh"),
            [CalendarItem("fixture", "Fixture", True, True, True)],
        )
        with repo.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE app_private.google_connections SET blocking_ids='[\"fixture\"]', "
                    "destination_id='fixture' WHERE user_id=:host"
                ),
                {"host": host},
            )
        values = EventInput(
            title="Lifecycle fixture",
            slug="test-call",
            durations=[30],
            default_duration=30,
            notice_minutes=0,
            buffer_before=0,
            buffer_after=0,
            max_per_day=1,
            cancellation_hours=12,
            reschedule_hours=12,
            reschedule_requires_approval=False,
        ).model_dump()
        event = events.save_event(host, values)
        event = events.save_event(host, values | {"published": True}, event["id"], 1)
        schedule = ScheduleInput(
            revision=0,
            timezone="UTC",
            enabled=True,
            weekly=[{"weekday": i, "start": "09:00", "end": "17:00"} for i in range(7)],
            focus=[],
            overrides=[],
            increment_minutes=15,
            host_daily_cap=1,
            weekly_cap_minutes=120,
            prefer_cluster=True,
        ).model_dump(mode="json", exclude={"revision"})
        ScheduleRepository(settings.database_url).save(host, schedule, 0)
        first, capability = reserve(start)
        booking_id = UUID(first["id"])
        assert worker.run_once(host)
        assert email_worker.run_once(host)
        with pytest.raises(HTTPException) as denied:
            service.act(booking_id, action("cancel", 1), "b" * 64, now=now)
        assert denied.value.status_code == 404
        with pytest.raises(HTTPException) as denied:
            service.act(booking_id, action("cancel", 1), actor=other, now=now)
        assert denied.value.status_code == 404
        report = service.slots(booking_id, capability, start.date(), start.date(), "UTC", now=now)
        shifted = start + timedelta(minutes=15)
        assert any(datetime.fromisoformat(s["start"]) == shifted for s in report["slots"])
        provider.blocked = (Interval(shifted, shifted + timedelta(minutes=30)),)
        with pytest.raises(HTTPException) as conflict:
            service.act(
                booking_id, action("reschedule", 1, candidates=[shifted]), capability, now=now
            )
        assert conflict.value.status_code == 409
        assert repo.manage(booking_id, capability)["start_at"] == start
        provider.blocked = ()
        move = action("reschedule", 1, candidates=[shifted], timezone="Asia/Kolkata")
        moved = service.act(booking_id, move, capability, now=now)["booking"]
        assert moved["revision"] == 2 and moved["start_at"] == shifted
        assert service.act(booking_id, move, capability, now=now)["booking"]["revision"] == 2
        assert worker.run_once(host) and (booking_id, 1) in provider.deleted
        assert email_worker.run_once(host)
        assert email_calls[-1][0]["subject"].startswith("Booking rescheduled:")
        assert email_calls[-1][1].endswith("/2")
        with pytest.raises(HTTPException):
            service.act(booking_id, action("cancel", 1), capability, now=now)
        with pytest.raises(HTTPException):
            service.act(
                booking_id, action("cancel", 2), capability, now=shifted - timedelta(hours=12)
            )

        # Saved approval policy survives future editor changes. Pending alternatives are not held.
        event = events.save_event(
            host,
            values
            | {"published": True, "reschedule_requires_approval": True, "allow_alternatives": True},
            event["id"],
            event["revision"],
        )
        second, cap2 = reserve(start + timedelta(days=1))
        second_id = UUID(second["id"])
        times = [start + timedelta(days=2), start + timedelta(days=3)]
        request = action("reschedule", 1, candidates=times, timezone="UTC")
        proposed = service.act(second_id, request, cap2, now=now)["booking"]
        assert proposed["start_at"] == second["start_at"] and proposed["revision"] == 1
        request_id = proposed["change_request"]["id"]
        blocker, blocker_cap = reserve(times[0])
        with pytest.raises(HTTPException):
            service.act(
                second_id,
                action("approve", 1, request_id=request_id, candidates=[times[0]]),
                actor=host,
                now=now,
            )
        assert repo.manage(second_id, cap2)["change_request"]["status"] == "pending"
        approved = service.act(
            second_id,
            action("approve", 1, request_id=request_id, candidates=[times[1]]),
            actor=host,
            now=now,
        )["booking"]
        assert approved["revision"] == 2 and approved["change_request"]["status"] == "approved"
        assert approved["start_at"] == times[1]
        # Decline and withdrawal preserve the original and erase the temporary capability.
        for decision in ("decline", "withdraw"):
            req = service.act(
                second_id,
                action("reschedule", 2, candidates=[start + timedelta(days=4)]),
                cap2,
                now=now,
            )["booking"]["change_request"]
            resolved = service.act(
                second_id,
                action(decision, 2, request_id=req["id"]),
                cap2 if decision == "withdraw" else "",
                actor=host if decision == "decline" else None,
                now=now,
            )["booking"]
            assert resolved["change_request"]["status"] == (
                "declined" if decision == "decline" else "withdrawn"
            )
            assert resolved["start_at"] == times[1]
        # Competing cancellation and reschedule can commit only one revision.
        barrier = Barrier(2)

        def compete(kind):
            barrier.wait(timeout=15)
            try:
                return service.act(
                    booking_id,
                    action(
                        kind,
                        2,
                        candidates=[start + timedelta(days=5)] if kind == "reschedule" else [],
                    ),
                    capability,
                    now=now,
                )
            except HTTPException as error:
                return error.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(compete, ["cancel", "reschedule"]))
        assert sum(isinstance(r, dict) for r in outcomes) == 1 and outcomes.count(409) == 1
        current = repo.manage(booking_id, capability)
        if current["status"] != "cancelled":
            current = service.act(
                booking_id, action("cancel", current["revision"]), capability, now=now
            )["booking"]
        assert current["status"] == "cancelled"
        # Drain only our synthetic host; superseded revisions cannot create events/send messages.
        while worker.run_once(host):
            pass
        while email_worker.run_once(host):
            pass
        current = repo.manage(booking_id, capability)
        assert current["calendar_status"] == "synced" and current["email_status"] == "accepted"
        assert any(p["subject"].startswith("Booking cancelled:") for p, _ in email_calls)
        assert reserve(start)[0]["status"] == "confirmed"  # cancelled slot released
        with repo.engine.begin() as c:
            assert (
                c.execute(
                    text(
                        "SELECT count(*) FROM app_private.booking_changes WHERE user_id=:host "
                        "AND status!='pending' AND capability_ciphertext IS NOT NULL"
                    ),
                    {"host": host},
                ).scalar()
                == 0
            )
    except SQLAlchemyError:
        pytest.fail("Lifecycle database check failed; SQL and credentials withheld.", pytrace=False)
    finally:
        with repo.engine.begin() as c:
            for table in ("bookings", "google_connections", "availability", "event_types"):
                c.execute(
                    text(f"DELETE FROM app_private.{table} WHERE user_id=:host"), {"host": host}
                )
            c.execute(
                text("DELETE FROM app_private.host_profiles WHERE user_id IN (:host,:other)"),
                {"host": host, "other": other},
            )
            c.execute(
                text("DELETE FROM auth.users WHERE id IN (:host,:other)"),
                {"host": host, "other": other},
            )
