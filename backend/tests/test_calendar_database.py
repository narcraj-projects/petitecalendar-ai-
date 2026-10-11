import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.api.availability import ScheduleInput
from app.api.bookings import BookingInput
from app.api.calendar import CalendarPreferences
from app.api.events import EventInput
from app.config import get_settings
from app.db.availability import ScheduleRepository
from app.db.bookings import BookingRepository, digest
from app.db.calendar import CalendarJob, CalendarRepository, GoogleConnection
from app.db.email import EmailJob
from app.db.events import EventRepository
from app.domain.availability import Interval
from app.email_worker import EmailWorker
from app.integrations.email import EmailError
from app.integrations.google import CalendarError, CalendarItem, TokenVault
from app.services.calendar import CalendarService
from app.worker import CalendarWorker
from cryptography.fernet import Fernet
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1", reason="Opt-in development database test"
)
def test_calendar_consent_reservation_queue_leases_and_isolation(monkeypatch):
    settings = replace(
        get_settings(),
        token_encryption_key=Fernet.generate_key().decode(),
        resend_api_key="synthetic",
        email_from="Fixture <onboarding@resend.dev>",
    )
    monkeypatch.setattr("app.db.bookings.get_settings", lambda: settings)
    repo = CalendarRepository(settings.database_url)
    bookings = BookingRepository(settings.database_url)
    host, other = uuid4(), uuid4()
    username = "cal-check-" + uuid4().hex[:12]
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = now + timedelta(days=3, hours=10)
    calendars = [CalendarItem("fixture", "Fixture", True, True, True)]

    class Provider:
        busy = ()
        fail = False
        calls = 0

        def access_token(self, refresh):
            assert refresh == "synthetic-refresh"
            return "synthetic-access"

        def calendars(self, token):
            return calendars

        def free_busy(self, token, ids, begin, end):
            assert ids == ["fixture"]
            if self.fail:
                raise CalendarError("provider_unavailable")
            return self.busy

        def ensure_event(self, token, destination, booking, meet):
            assert destination == "fixture" and meet
            assert "invitee_email" not in booking
            self.calls += 1
            return {"event_id": "pcfixture", "meet_url": "https://meet.google.com/abc-defg-hij"}

    provider = Provider()
    service = CalendarService(repo, provider, settings)
    worker = CalendarWorker(repo.engine, provider, settings)
    vault = TokenVault(settings.token_encryption_key)

    def body(time):
        return BookingInput(
            start=time,
            duration=30,
            timezone="UTC",
            name="Fixture",
            email="fixture@example.com",
            idempotency_key=uuid4(),
            capability=uuid4().hex + uuid4().hex,
        )

    try:
        with repo.engine.begin() as c:
            c.execute(
                text("INSERT INTO auth.users(id) VALUES (:host),(:other)"),
                {"host": host, "other": other},
            )
            c.execute(
                text("""INSERT INTO app_private.host_profiles
                (user_id,display_name,username,timezone) VALUES
                (:host,'Calendar fixture',:username,'UTC'),
                (:other,'Other fixture',:othername,'UTC')"""),
                {
                    "host": host,
                    "other": other,
                    "username": username,
                    "othername": username + "-other",
                },
            )
        repo.start_state(host, digest("state"), digest("binding"), vault.seal(host, "verifier"))
        assert repo.consume_state(digest("state"), digest("wrong")) is None
        stored = repo.consume_state(digest("state"), digest("binding"))
        assert stored["user_id"] == host
        assert vault.open(host, stored["verifier_ciphertext"]) == "verifier"
        assert repo.consume_state(digest("state"), digest("binding")) is None
        repo.connect(host, "fixture", vault.seal(host, "synthetic-refresh"), calendars)
        assert repo.read(other) is None
        service.save(
            host,
            CalendarPreferences(
                revision=1, blocking_ids=[], destination_id="fixture", create_meet=True
            ),
        )
        row = repo.read(host)
        assert row["blocking_ids"] == ["fixture"] and row["revision"] == 2
        with pytest.raises(HTTPException) as stale:
            service.save(
                host,
                CalendarPreferences(
                    revision=1, blocking_ids=[], destination_id="fixture", create_meet=True
                ),
            )
        assert stale.value.status_code == 409
        values = EventInput(
            title="Calendar fixture",
            slug="test-call",
            durations=[30],
            default_duration=30,
            notice_minutes=0,
        ).model_dump()
        events = EventRepository(settings.database_url)
        event = events.save_event(host, values)
        events.save_event(host, values | {"published": True}, event["id"], 1)
        schedule = ScheduleInput(
            revision=0,
            timezone="UTC",
            enabled=True,
            weekly=[{"weekday": i, "start": "09:00", "end": "17:00"} for i in range(7)],
            focus=[],
            overrides=[],
            increment_minutes=15,
            host_daily_cap=10,
            weekly_cap_minutes=600,
            prefer_cluster=False,
        )
        ScheduleRepository(settings.database_url).save(
            host, schedule.model_dump(mode="json", exclude={"revision"}), 0
        )
        provider.busy = (Interval(start, start + timedelta(hours=1)),)
        with pytest.raises(HTTPException) as occupied:
            bookings.reserve(username, "test-call", body(start), now=now, calendar_service=service)
        assert occupied.value.status_code == 409
        provider.fail = True
        with pytest.raises(HTTPException) as unavailable:
            bookings.reserve(username, "test-call", body(start), now=now, calendar_service=service)
        assert unavailable.value.status_code == 503
        provider.busy, provider.fail = (), False
        request = body(start)
        saved = bookings.reserve(username, "test-call", request, now=now, calendar_service=service)
        assert saved["calendar_status"] == "queued"
        assert (
            bookings.reserve(username, "test-call", request, now=now, calendar_service=service)[
                "id"
            ]
            == saved["id"]
        )
        with repo.engine.begin() as c:
            assert c.execute(select(CalendarJob).where(CalendarJob.user_id == host)).one()
            repo._set_actor(c, other)
            assert c.execute(select(CalendarJob).where(CalendarJob.user_id == host)).all() == []
            assert (
                c.execute(select(GoogleConnection).where(GoogleConnection.user_id == host)).all()
                == []
            )
        first = worker.claim(host)
        assert first and worker.claim(host) is None
        with repo.engine.begin() as c:
            c.execute(
                update(CalendarJob)
                .where(CalendarJob.booking_id == UUID(saved["id"]))
                .values(lease_until=now - timedelta(seconds=1))
            )
        reclaimed = worker.claim(host)
        assert reclaimed["lease_token"] != first["lease_token"]
        worker.finish(first, result={"event_id": "stale", "meet_url": None})
        assert (
            bookings.manage(UUID(saved["id"]), request.capability)["calendar_status"] == "working"
        )
        worker.finish(reclaimed, error="provider_unavailable")
        repo.retry(host, UUID(saved["id"]))
        assert worker.run_once(host)
        delivered = bookings.manage(UUID(saved["id"]), request.capability)
        assert delivered["calendar_status"] == "synced" and delivered["meet_url"].startswith(
            "https://meet.google.com/"
        )
        assert provider.calls == 1 and not worker.run_once(host)
        assert delivered["email_status"] == "queued"

        class EmailProvider:
            calls = []

            def send(self, payload, key):
                self.calls.append((payload, key))
                if len(self.calls) == 1:
                    raise EmailError(ambiguous=True)
                return "synthetic-provider-id"

        email_provider = EmailProvider()
        email_worker = EmailWorker(repo.engine, email_provider, settings)
        original_lease = email_worker.claim(host)
        assert original_lease and email_worker.claim(host) is None
        with repo.engine.begin() as c:
            c.execute(
                update(EmailJob)
                .where(EmailJob.booking_id == UUID(saved["id"]))
                .values(lease_until=now - timedelta(seconds=1))
            )
        reclaimed_email = email_worker.claim(host)
        assert reclaimed_email["lease_token"] != original_lease["lease_token"]
        email_worker.finish(original_lease, provider_id="stale")
        email_worker.finish(reclaimed_email, error=EmailError("rate_limited"))
        with repo.engine.begin() as c:
            c.execute(
                update(EmailJob).where(EmailJob.booking_id == UUID(saved["id"])).values(due_at=now)
            )
        assert email_worker.run_once(host)
        assert bookings.manage(UUID(saved["id"]), request.capability)["email_status"] == "retry"
        with repo.engine.begin() as c:
            job = (
                c.execute(
                    select(EmailJob.__table__).where(EmailJob.booking_id == UUID(saved["id"]))
                )
                .mappings()
                .one()
            )
            assert request.capability not in job["capability_ciphertext"]
            assert request.capability not in job["payload_ciphertext"]
            c.execute(
                update(EmailJob).where(EmailJob.booking_id == UUID(saved["id"])).values(due_at=now)
            )
            c.execute(
                update(CalendarJob)
                .where(CalendarJob.booking_id == UUID(saved["id"]))
                .values(meet_url="https://meet.google.com/new-link-test")
            )
            repo._set_actor(c, other)
            assert c.execute(select(EmailJob.status).where(EmailJob.user_id == host)).all() == []
            with pytest.raises(SQLAlchemyError):
                with c.begin_nested():
                    c.execute(select(EmailJob.payload_ciphertext))
        assert email_worker.run_once(host) and not email_worker.run_once(host)
        assert email_provider.calls[0] == email_provider.calls[1]
        assert request.capability in email_provider.calls[0][0]["text"]
        assert bookings.manage(UUID(saved["id"]), request.capability)["email_status"] == "accepted"
        assert (
            bookings.reserve(username, "test-call", request, now=now, calendar_service=service)[
                "email_status"
            ]
            == "accepted"
        )
        with repo.engine.begin() as c:
            job = (
                c.execute(
                    select(EmailJob.__table__).where(EmailJob.booking_id == UUID(saved["id"]))
                )
                .mappings()
                .one()
            )
            assert job["capability_ciphertext"] is None and job["payload_ciphertext"] is None
        assert (
            len(
                bookings.dashboard(host, start.date(), (start + timedelta(days=1)).date())[
                    "bookings"
                ]
            )
            == 1
        )
        with pytest.raises(HTTPException):
            repo.retry(other, UUID(saved["id"]))
        repo.disconnect(host, 2)
        assert repo.read(host)["token_ciphertext"] is None
        assert bookings.manage(UUID(saved["id"]), request.capability)["status"] == "confirmed"
    except SQLAlchemyError:
        pytest.fail(
            "Calendar database check failed; SQL details and credentials withheld.", pytrace=False
        )
    finally:
        with repo.engine.begin() as c:
            for table in (
                "bookings",
                "google_oauth_states",
                "google_connections",
                "availability",
                "event_types",
            ):
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
