"""Durable confirmation delivery; uses an immutable payload within Resend's retry window."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, text, update

from app.config import get_settings
from app.db.bookings import Booking
from app.db.calendar import CalendarJob
from app.db.email import EmailJob
from app.db.lifecycle import delivery_lock
from app.db.profiles import get_engine
from app.integrations.email import EmailError, ResendEmail
from app.integrations.google import TokenVault
from app.services.booking_email import confirmation_payload, payload_text


class EmailWorker:
    job_model = EmailJob
    job_table = "email_jobs"

    def __init__(self, engine=None, provider=None, settings=None):
        self.settings = settings or get_settings()
        self.engine = engine or get_engine(self.settings.database_url)
        self.provider = provider or ResendEmail(self.settings)

    def _role(self, c):
        c.execute(text("SET LOCAL ROLE petitecalendar_email_worker"))

    def claim(self, host=None):
        with self.engine.begin() as c:
            self._role(c)
            row = (
                c.execute(
                    text(f"""WITH candidate AS (
                SELECT booking_id,revision FROM app_private.{self.job_table}
                WHERE ((status IN ('queued','retry') AND due_at<=now())
                    OR (status='working' AND lease_until<now()))
                    AND (CAST(:host AS uuid) IS NULL OR user_id=CAST(:host AS uuid))
                ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE app_private.{self.job_table} j SET status='working',lease_token=:lease,
                lease_until=now()+interval '90 seconds',attempts=attempts+1
                FROM candidate c WHERE j.booking_id=c.booking_id AND j.revision=c.revision
                RETURNING j.*"""),
                    {"host": host, "lease": uuid4()},
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def _owned(self, job):
        return (
            self.job_model.booking_id == job["booking_id"],
            self.job_model.revision == job["revision"],
            self.job_model.status == "working",
            self.job_model.lease_token == job["lease_token"],
        )

    def load(self, job):
        with self.engine.begin() as c:
            self._role(c)
            row = (
                c.execute(
                    select(
                        Booking.id,
                        Booking.user_id,
                        Booking.start_at,
                        Booking.end_at,
                        Booking.duration,
                        Booking.invitee_name,
                        Booking.invitee_email,
                        Booking.invitee_timezone,
                        Booking.snapshot,
                        Booking.status,
                        Booking.revision,
                        Booking.created_at,
                        Booking.updated_at,
                    ).where(Booking.id == job["booking_id"], Booking.user_id == job["user_id"])
                )
                .mappings()
                .first()
            )
            calendar = (
                c.execute(
                    select(CalendarJob.status, CalendarJob.meet_url).where(
                        CalendarJob.booking_id == job["booking_id"],
                        CalendarJob.revision == job["revision"],
                    )
                )
                .mappings()
                .first()
            )
            booking = dict(row) if row else None
            if booking:
                booking["meet_url"] = calendar["meet_url"] if calendar else None
            return booking, dict(calendar) if calendar else None

    def defer(self, job):
        with self.engine.begin() as c:
            self._role(c)
            c.execute(
                update(self.job_model)
                .where(*self._owned(job))
                .values(
                    status="retry",
                    attempts=max(0, job["attempts"] - 1),
                    due_at=func.now() + text("interval '15 seconds'"),
                    lease_token=None,
                    lease_until=None,
                )
            )

    def freeze(self, job, payload, now):
        vault = TokenVault(self.settings.token_encryption_key)
        ciphertext = job["payload_ciphertext"] or vault.seal(job["user_id"], payload_text(payload))
        with self.engine.begin() as c:
            self._role(c)
            saved = c.execute(
                update(self.job_model)
                .where(*self._owned(job), self.job_model.lease_until > func.now())
                .values(payload_ciphertext=ciphertext, frozen_at=job["frozen_at"] or now)
                .returning(self.job_model.booking_id)
            ).first()
        return bool(saved)

    def finish(self, job, provider_id=None, error=None, uncertain=False):
        terminal = bool(
            provider_id or uncertain or (error and error.permanent) or job["attempts"] >= 12
        )
        status = (
            "accepted"
            if provider_id
            else (
                "uncertain"
                if uncertain or (terminal and error and error.ambiguous)
                else "failed"
                if terminal
                else "retry"
            )
        )
        values = {
            "status": status,
            "provider_id": provider_id,
            "last_error": error.code if error else None,
            "lease_token": None,
            "lease_until": None,
            "due_at": func.now()
            + text(f"interval '{min(300, 2 ** min(job['attempts'], 8))} seconds'"),
        }
        if terminal:
            values.update(capability_ciphertext=None, payload_ciphertext=None)
        with self.engine.begin() as c:
            self._role(c)
            c.execute(update(self.job_model).where(*self._owned(job)).values(**values))

    def build_payload(self, booking, job, vault):
        capability = vault.open(job["user_id"], job["capability_ciphertext"])
        return confirmation_payload(
            booking, capability, self.settings, job.get("event_type", "booking_confirmed")
        )

    def delivery_key(self, job):
        event_type = job.get("event_type", "booking_confirmed").replace("_", "-")
        return f"{event_type}/{job['booking_id']}/{job['revision']}"

    def run_once(self, host=None):
        job = self.claim(host)
        if not job:
            return False
        with delivery_lock(self.engine, job["booking_id"]):
            self.deliver(job)
        return True

    def deliver(self, job):
        now = datetime.now(UTC)
        try:
            booking, calendar = self.load(job)
            if (
                not booking
                or booking["status"]
                != ("cancelled" if job.get("event_type") == "booking_cancelled" else "confirmed")
                or booking["revision"] != job["revision"]
            ):
                raise EmailError("stale_booking", permanent=True)
            # Stop before Resend expires its 24-hour deduplication key; never auto-resend later.
            if job["frozen_at"] and now - job["frozen_at"] >= timedelta(hours=23):
                self.finish(job, error=EmailError("retry_window_expired"), uncertain=True)
                return
            if (
                not job["payload_ciphertext"]
                and calendar
                and calendar["status"] in ("queued", "working", "retry")
                and now - job["created_at"] < timedelta(minutes=10)
            ):
                self.defer(job)
                return
            vault = TokenVault(self.settings.token_encryption_key)
            if job["payload_ciphertext"]:
                payload = json.loads(vault.open(job["user_id"], job["payload_ciphertext"]))
            else:
                payload = self.build_payload(booking, job, vault)
            if self.freeze(job, payload, now):
                self.finish(job, provider_id=self.provider.send(payload, self.delivery_key(job)))
        except EmailError as error:
            self.finish(job, error=error)
        except Exception:
            # Provider acceptance may be uncertain; no personal data/traceback is emitted.
            self.finish(job, error=EmailError("delivery_unavailable", ambiguous=True))
