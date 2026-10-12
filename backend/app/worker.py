"""Durable calendar delivery. Run separately: python -m app.worker [--once]."""

import argparse
import time
from uuid import uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.bookings import Booking
from app.db.calendar import CalendarJob, GoogleConnection
from app.db.lifecycle import delivery_lock
from app.db.profiles import get_engine
from app.email_worker import EmailWorker
from app.integrations.google import CalendarError, GoogleCalendar, TokenVault
from app.invitation_worker import InvitationWorker


class CalendarWorker:
    def __init__(self, engine=None, provider=None, settings=None):
        self.settings = settings or get_settings()
        self.engine = engine or get_engine(self.settings.database_url)
        self.provider = provider or GoogleCalendar(self.settings)

    def _role(self, c):
        c.execute(text("SET LOCAL ROLE petitecalendar_worker"))

    def claim(self, host=None):
        lease = uuid4()
        with self.engine.begin() as c:
            self._role(c)
            row = (
                c.execute(
                    text("""WITH candidate AS (
                SELECT booking_id,revision FROM app_private.calendar_jobs
                WHERE ((status IN ('queued','retry') AND due_at<=now())
                    OR (status='working' AND lease_until<now()))
                    AND (CAST(:host AS uuid) IS NULL OR user_id=CAST(:host AS uuid))
                ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE app_private.calendar_jobs j
                SET status='working',lease_token=:lease,lease_until=now()+interval '90 seconds',
                    attempts=attempts+1,updated_at=now()
                FROM candidate c WHERE j.booking_id=c.booking_id AND j.revision=c.revision
                RETURNING j.*"""),
                    {"lease": lease, "host": host},
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def load(self, job):
        with self.engine.begin() as c:
            self._role(c)
            connection = (
                c.execute(
                    select(GoogleConnection.__table__).where(
                        GoogleConnection.user_id == job["user_id"]
                    )
                )
                .mappings()
                .first()
            )
            booking = (
                c.execute(
                    select(
                        Booking.id,
                        Booking.user_id,
                        Booking.start_at,
                        Booking.end_at,
                        Booking.invitee_name,
                        Booking.snapshot,
                        Booking.status,
                        Booking.revision,
                    ).where(Booking.id == job["booking_id"], Booking.user_id == job["user_id"])
                )
                .mappings()
                .first()
            )
            return dict(connection) if connection else None, dict(booking) if booking else None

    def finish(self, job, result=None, error=None):
        permanent = error in ("connection_changed", "stale_booking", "event_changed", "meet_failed")
        failed = permanent or job["attempts"] >= 12
        with self.engine.begin() as c:
            self._role(c)
            values = {
                "status": "synced" if result else "failed" if failed else "retry",
                "last_error": error,
                "lease_token": None,
                "lease_until": None,
                "updated_at": func.now(),
            }
            if result:
                values.update(event_id=result["event_id"], meet_url=result["meet_url"])
            else:
                delay = min(300, 2 ** min(job["attempts"], 8))
                values["due_at"] = func.now() + text(f"interval '{delay} seconds'")
            c.execute(
                update(CalendarJob)
                .where(
                    CalendarJob.booking_id == job["booking_id"],
                    CalendarJob.revision == job["revision"],
                    CalendarJob.status == "working",
                    CalendarJob.lease_token == job["lease_token"],
                )
                .values(**values)
            )
            if error == "reconnect_required":
                c.execute(
                    update(GoogleConnection)
                    .where(
                        GoogleConnection.user_id == job["user_id"],
                        GoogleConnection.generation == job["generation"],
                        GoogleConnection.status == "connected",
                    )
                    .values(status="reconnect_required")
                )

    def run_once(self, host=None):
        job = self.claim(host)
        if not job:
            return False
        with delivery_lock(self.engine, job["booking_id"]):
            self.deliver(job)
        return True

    def deliver(self, job):
        try:
            connection, booking = self.load(job)
            if (
                not booking
                or booking["status"]
                != ("cancelled" if job.get("operation") == "cancel" else "confirmed")
                or booking["revision"] != job["revision"]
            ):
                raise CalendarError("stale_booking")
            if not connection or connection["generation"] != job["generation"]:
                raise CalendarError("connection_changed")
            if connection["status"] != "connected" or not connection["token_ciphertext"]:
                raise CalendarError("reconnect_required")
            vault = TokenVault(self.settings.token_encryption_key)
            refresh = vault.open(job["user_id"], connection["token_ciphertext"])
            token = self.provider.access_token(refresh)
            with self.engine.begin() as c:
                self._role(c)
                owned = c.execute(
                    select(CalendarJob.booking_id).where(
                        CalendarJob.booking_id == job["booking_id"],
                        CalendarJob.revision == job["revision"],
                        CalendarJob.status == "working",
                        CalendarJob.lease_token == job["lease_token"],
                        CalendarJob.lease_until > func.now(),
                    )
                ).first()
                history = (
                    c.execute(
                        select(CalendarJob.__table__).where(
                            CalendarJob.booking_id == job["booking_id"],
                            CalendarJob.revision < job["revision"],
                        )
                    )
                    .mappings()
                    .all()
                )
            if not owned:
                return
            if any(j["generation"] != job["generation"] for j in history):
                raise CalendarError("connection_changed")
            result = (
                {"event_id": None, "meet_url": None}
                if job.get("operation") == "cancel"
                else self.provider.ensure_event(
                    token, job["destination_id"], booking, job["create_meet"]
                )
            )
            # Include never-finished insert jobs: an ambiguous POST may have created the event.
            for old in history:
                if old.get("operation") != "cancel":
                    self.provider.delete_owned_event(
                        token, old["destination_id"], job["booking_id"], old["revision"]
                    )
            self.finish(job, result=result)
        except CalendarError as e:
            self.finish(job, error=e.code)
        except Exception:
            # No raw payload/URL/token or exception traceback is logged.
            self.finish(job, error="provider_unavailable")


def main():
    from app.host_email_worker import HostEmailWorker

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--calendar-only", action="store_true")
    args = parser.parse_args()
    worker = CalendarWorker()
    email_worker = (
        EmailWorker() if worker.settings.email_configured and not args.calendar_only else None
    )
    invitation_worker = InvitationWorker() if email_worker else None
    host_email_worker = HostEmailWorker() if email_worker else None
    try:
        while True:
            try:
                worked = worker.run_once()
                if email_worker:
                    worked = email_worker.run_once() or worked
                if invitation_worker:
                    worked = invitation_worker.run_once() or worked
                if host_email_worker:
                    worked = host_email_worker.run_once() or worked
            except SQLAlchemyError:
                worked = False
                print("Calendar worker: storage unavailable; retrying.", flush=True)
            if args.once:
                break
            time.sleep(0.1 if worked else 2)
    finally:
        worker.provider.close()
        if email_worker:
            email_worker.provider.close()
        if invitation_worker:
            invitation_worker.provider.close()
        if host_email_worker:
            host_email_worker.provider.close()


if __name__ == "__main__":
    main()
