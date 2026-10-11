import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, text, update

from app.db.invitations import InvitationJob
from app.db.lifecycle import delivery_lock
from app.email_worker import EmailWorker
from app.integrations.email import EmailError
from app.integrations.google import TokenVault


class InvitationWorker(EmailWorker):
    def claim(self, host=None):
        with self.engine.begin() as c:
            self._role(c)
            row = (
                c.execute(
                    text("""WITH candidate AS (
                SELECT id FROM app_private.invitation_jobs
                WHERE ((status IN ('queued','retry') AND due_at<=now())
                    OR (status='working' AND lease_until<now()))
                    AND (CAST(:host AS uuid) IS NULL OR user_id=CAST(:host AS uuid))
                ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE app_private.invitation_jobs j SET status='working',lease_token=:lease,
                lease_until=now()+interval '90 seconds',attempts=attempts+1
                FROM candidate c WHERE j.id=c.id RETURNING j.*"""),
                    {"host": host, "lease": uuid4()},
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def _owned(self, job):
        return (
            InvitationJob.id == job["id"],
            InvitationJob.status == "working",
            InvitationJob.lease_token == job["lease_token"],
        )

    def finish(self, job, provider_id=None, error=None, uncertain=False):
        terminal = bool(
            provider_id or uncertain or (error and error.permanent) or job["attempts"] >= 12
        )
        status = (
            "accepted"
            if provider_id
            else "uncertain"
            if uncertain or (terminal and error and error.ambiguous)
            else "failed"
            if terminal
            else "retry"
        )
        with self.engine.begin() as c:
            self._role(c)
            c.execute(
                update(InvitationJob)
                .where(*self._owned(job))
                .values(
                    status=status,
                    provider_id=provider_id,
                    last_error=error.code if error else None,
                    lease_token=None,
                    lease_until=None,
                    payload_ciphertext=None if terminal else job["payload_ciphertext"],
                    due_at=func.now()
                    + text(f"interval '{min(300, 2 ** min(job['attempts'], 8))} seconds'"),
                )
            )

    def run_once(self, host=None):
        job = self.claim(host)
        if not job:
            return False
        with delivery_lock(self.engine, job["id"]):
            self.deliver(job)
        return True

    def deliver(self, job):
        try:
            now = datetime.now(UTC)
            if job["frozen_at"] and now - job["frozen_at"] >= timedelta(hours=23):
                self.finish(job, error=EmailError("retry_window_expired"), uncertain=True)
                return
            with self.engine.begin() as c:
                self._role(c)
                current = (
                    c.execute(
                        select(InvitationJob.__table__).where(
                            *self._owned(job), InvitationJob.lease_until > func.now()
                        )
                    )
                    .mappings()
                    .first()
                )
                if not current:
                    return
                frozen_at = current["frozen_at"] or now
                c.execute(
                    update(InvitationJob).where(*self._owned(job)).values(frozen_at=frozen_at)
                )
                job = dict(current) | {"frozen_at": frozen_at}
            payload = json.loads(
                TokenVault(self.settings.token_encryption_key).open(
                    job["user_id"], job["payload_ciphertext"]
                )
            )
            self.finish(
                job, provider_id=self.provider.send(payload, f"event-invitation/{job['id']}")
            )
        except EmailError as error:
            self.finish(job, error=error)
        except Exception:
            self.finish(job, error=EmailError("delivery_unavailable", ambiguous=True))
