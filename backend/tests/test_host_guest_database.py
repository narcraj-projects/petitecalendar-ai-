"""Apply the new migration and test synthetic data inside one rollback-only dev transaction."""

import importlib.util
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.api.availability import ScheduleInput
from app.api.bookings import BookingInput
from app.api.events import EventInput
from app.config import Settings, get_settings
from app.db.availability import ScheduleRepository
from app.db.bookings import Booking, BookingRepository
from app.db.email import EmailJob, HostEmailJob
from app.db.events import EventRepository
from app.db.guest_history import GuestHistoryRepository
from app.guest_auth import GuestIdentity
from app.host_email_worker import HostEmailWorker
from app.integrations.email import EmailError
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError


@pytest.mark.skipif(
    os.getenv("RUN_GUEST_DATABASE_TESTS") != "1", reason="Opt-in dev rollback-only migration test"
)
def test_migration_atomic_host_jobs_retry_and_verified_guest_rls(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    dev, hosted = dotenv_values(root / ".env"), dotenv_values(root / ".env.staging")
    assert dev.get("SUPABASE_URL") and dev["SUPABASE_URL"] != hosted.get("SUPABASE_URL"), (
        "Use isolated development, never hosted storage."
    )
    assert get_settings().database_url == dev["DATABASE_URL"]
    settings = Settings(
        database_url=dev["DATABASE_URL"],
        app_base_url="https://app.example.com",
        resend_api_key="synthetic",
        email_from="bookings@example.com",
        token_encryption_key=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr("app.db.bookings.get_settings", lambda: settings)
    bookings = BookingRepository(settings.database_url)
    original_engine = bookings.engine
    host, other = uuid4(), uuid4()
    name = "history-" + uuid4().hex[:12]
    host_email = name + "@example.invalid"
    now = datetime.now(UTC)
    start = (now + timedelta(days=4)).replace(hour=10, minute=0, second=0, microsecond=0)
    with bookings.engine.connect() as c:
        transaction = c.begin()
        try:
            before = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert before == "0009_event_invitations", "Rollback test expects unapplied migration."
            spec = importlib.util.spec_from_file_location(
                "host_guest_migration",
                root / "backend/migrations/versions/0010_host_notifications_guest_history.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(c)):
                module.upgrade()

            class Engine:
                @contextmanager
                def begin(self):
                    with c.begin_nested():
                        yield c

            engine = Engine()
            bookings.engine = engine
            c.execute(
                text(
                    "INSERT INTO auth.users(id,email,email_confirmed_at) "
                    "VALUES (:a,:email,now()),(:b,:other,now())"
                ),
                {
                    "a": host,
                    "b": other,
                    "email": host_email,
                    "other": name + "-other@example.invalid",
                },
            )
            c.execute(
                text("""INSERT INTO app_private.host_profiles
                (user_id,display_name,username,timezone)
                VALUES (:a,'Host fixture',:name,'UTC'),(:b,'Other host',:othername,'UTC')"""),
                {"a": host, "b": other, "name": name, "othername": name + "-other"},
            )
            events = EventRepository.__new__(EventRepository)
            events.engine = engine
            values = EventInput(
                title="Guest history fixture",
                slug="review",
                durations=[30],
                default_duration=30,
                notice_minutes=0,
            ).model_dump()
            event = events.save_event(host, values)
            events.save_event(host, values | {"published": True}, event["id"], 1)
            schedule = ScheduleRepository.__new__(ScheduleRepository)
            schedule.engine = engine
            payload = ScheduleInput(
                revision=0,
                timezone="UTC",
                enabled=True,
                increment_minutes=30,
                host_daily_cap=10,
                weekly_cap_minutes=3000,
                prefer_cluster=False,
                weekly=[{"weekday": i, "start": "09:00", "end": "17:00"} for i in range(7)],
                focus=[],
                overrides=[],
            ).model_dump(mode="json", exclude={"revision"})
            schedule.save(host, payload, 0)
            request = BookingInput(
                start=start,
                duration=30,
                timezone="UTC",
                name="Guest fixture",
                email="Guest@Example.com",
                idempotency_key=uuid4(),
                capability=uuid4().hex + uuid4().hex,
            )
            saved = bookings.reserve(name, "review", request, now=now)
            assert bookings.reserve(name, "review", request, now=now)["id"] == saved["id"]
            c.execute(text("RESET ROLE"))
            assert c.execute(select(HostEmailJob.booking_id)).all() == [(UUID(saved["id"]),)]
            row = dict(
                c.execute(select(Booking.__table__).where(Booking.id == UUID(saved["id"])))
                .mappings()
                .one()
            )
            for minutes, status, email in [
                (-10000, "confirmed", "guest@example.com"),
                (120, "cancelled", "guest@example.com"),
                (240, "confirmed", "someone-else@example.com"),
            ]:
                stamp = start + timedelta(minutes=minutes)
                c.execute(
                    Booking.__table__.insert().values(
                        row
                        | {
                            "id": uuid4(),
                            "idempotency_key": uuid4(),
                            "request_hash": uuid4().hex,
                            "capability_hash": uuid4().hex,
                            "status": status,
                            "invitee_email": email,
                            "start_at": stamp,
                            "end_at": stamp + timedelta(minutes=30),
                            "blocked_start": stamp - timedelta(minutes=10),
                            "blocked_end": stamp + timedelta(minutes=45),
                        }
                    )
                )
            history = GuestHistoryRepository.__new__(GuestHistoryRepository)
            history.engine = engine
            identity = GuestIdentity(uuid4(), "guest@example.com")
            for kind in ("upcoming", "past", "cancelled"):
                result = history.history(identity, kind, now=now)
                assert len(result["bookings"]) == 1 and not result["has_more"]
                assert not any(
                    "capability" in key or "email" in key
                    for key in result["bookings"][0]
                    if key != "email_status"
                )
            assert (
                history.history(GuestIdentity(uuid4(), "absent@example.com"), "upcoming")[
                    "bookings"
                ]
                == []
            )
            # RLS independently restricts even a query with no explicit email predicate.
            with c.begin_nested():
                c.execute(text("SET LOCAL ROLE petitecalendar_guest"))
                c.execute(text("SELECT set_config('app.guest_email','guest@example.com',true)"))
                assert len(c.execute(text("SELECT id FROM app_private.bookings")).all()) == 3
                with pytest.raises(SQLAlchemyError):
                    with c.begin_nested():
                        c.execute(text("SELECT capability_hash FROM app_private.bookings"))
                with pytest.raises(SQLAlchemyError):
                    with c.begin_nested():
                        c.execute(
                            text("SELECT app_private.host_notification_email(:id,1)"),
                            {"id": saved["id"]},
                        )
            c.execute(text("RESET ROLE"))
            c.execute(
                update(EmailJob)
                .where(EmailJob.booking_id == UUID(saved["id"]))
                .values(status="failed")
            )
            sent = []

            class Provider:
                def send(self, payload, key):
                    sent.append((payload, key))
                    if len(sent) == 1:
                        raise EmailError(ambiguous=True)
                    return "host-provider-fixture"

            worker = HostEmailWorker(engine, Provider(), settings)
            assert worker.run_once(host)
            c.execute(text("RESET ROLE"))
            c.execute(
                text("UPDATE auth.users SET email=:email WHERE id=:id"),
                {"email": name + "-changed@example.invalid", "id": host},
            )
            c.execute(update(HostEmailJob).values(due_at=now - timedelta(seconds=1)))
            assert worker.run_once(host)
            assert sent[0] == sent[1] and sent[1][0]["to"] == [host_email]
            assert "/booking/" not in sent[1][0]["text"]
            c.execute(text("RESET ROLE"))
            assert (
                c.execute(
                    select(EmailJob.status).where(EmailJob.booking_id == UUID(saved["id"]))
                ).scalar_one()
                == "failed"
            )
            job = c.execute(select(HostEmailJob.__table__)).mappings().one()
            assert job["status"] == "accepted" and job["payload_ciphertext"] is None
            assert (
                bookings.dashboard(host, start.date(), (start + timedelta(days=1)).date())[
                    "bookings"
                ][0]["host_email_status"]
                == "accepted"
            )
            c.execute(text("RESET ROLE"))
            assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == before
        except SQLAlchemyError:
            pytest.fail(
                "Rollback-only guest/host DB check failed; SQL details withheld.", pytrace=False
            )
        finally:
            transaction.rollback()
    with original_engine.connect() as verify:
        assert (
            verify.execute(text("SELECT to_regclass('app_private.host_email_jobs')")).scalar_one()
            is None
        )
