"""Separate durable host notification with its own recipient and retry key."""

from sqlalchemy import text

from app.db.email import HostEmailJob
from app.email_worker import EmailWorker
from app.services.host_notification import host_notification_payload


class HostEmailWorker(EmailWorker):
    job_model = HostEmailJob
    job_table = "host_email_jobs"

    def build_payload(self, booking, job, vault):
        # Narrow privileged DB function returns only this job owner's verified auth email.
        # It does not grant the worker general access to auth.users or browser-supplied contacts.
        with self.engine.begin() as c:
            self._role(c)
            recipient = c.execute(
                text("SELECT app_private.host_notification_email(:id,:revision)"),
                {"id": job["booking_id"], "revision": job["revision"]},
            ).scalar_one_or_none()
        return host_notification_payload(booking, recipient, self.settings)

    def delivery_key(self, job):
        return f"host-booking-confirmed/{job['booking_id']}/{job['revision']}"
