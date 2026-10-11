import hashlib
import json
from uuid import uuid4

from sqlalchemy import Column, Date, DateTime, Integer, String, Text, Uuid, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.auth import failure
from app.config import get_settings
from app.db.events import EventType
from app.db.profiles import Base, HostProfile, ProfileRepository
from app.integrations.email import EmailError
from app.integrations.google import TokenVault
from app.services.event_invitation import invitation_payload


class InvitationBatch(Base):
    __tablename__ = "invitation_batches"
    __table_args__ = {"schema": "app_private"}
    id = Column(Uuid, primary_key=True)
    user_id = Column(Uuid, nullable=False)
    event_id = Column(Uuid, nullable=False)
    request_hash = Column(String(64), nullable=False)
    recipient_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class InvitationBudget(Base):
    __tablename__ = "invitation_budget"
    __table_args__ = {"schema": "app_private"}
    day = Column(Date, primary_key=True)
    recipients = Column(Integer, nullable=False)


class InvitationJob(Base):
    __tablename__ = "invitation_jobs"
    __table_args__ = {"schema": "app_private"}
    id = Column(Uuid, primary_key=True)
    batch_id = Column(Uuid, nullable=False)
    user_id = Column(Uuid, nullable=False)
    status = Column(String(20), nullable=False)
    attempts = Column(Integer, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    lease_token = Column(Uuid)
    lease_until = Column(DateTime(timezone=True))
    payload_ciphertext = Column(Text)
    frozen_at = Column(DateTime(timezone=True))
    provider_id = Column(String(100))
    last_error = Column(String(40))


class InvitationRepository(ProfileRepository):
    def _status(self, c, actor, batch_id):
        batch = c.execute(
            text("""SELECT id FROM app_private.invitation_batches
            WHERE id=:id AND user_id=:actor"""),
            {"id": batch_id, "actor": actor},
        ).first()
        if not batch:
            raise failure(404, "INVITATION_NOT_FOUND", "This invitation is not available.")
        counts = c.execute(
            select(InvitationJob.status, func.count())
            .where(InvitationJob.batch_id == batch_id, InvitationJob.user_id == actor)
            .group_by(InvitationJob.status)
        ).all()
        return {"id": str(batch_id), "counts": dict(counts)}

    def status(self, actor, event_id, batch_id):
        try:
            with self.engine.begin() as c:
                self._set_actor(c, actor)
                owns = c.execute(
                    text("""SELECT id FROM app_private.invitation_batches
                    WHERE id=:id AND event_id=:event AND user_id=:actor"""),
                    {"id": batch_id, "event": event_id, "actor": actor},
                ).first()
                if not owns:
                    raise failure(404, "INVITATION_NOT_FOUND", "This invitation is not available.")
                return self._status(c, actor, batch_id)
        except SQLAlchemyError:
            raise failure(
                503, "INVITATION_UNAVAILABLE", "Invitation status could not be loaded."
            ) from None

    def queue(self, actor, event_id, body):
        settings = get_settings()
        if not settings.email_configured:
            raise failure(503, "EMAIL_NOT_CONFIGURED", "Email sharing is not configured.")
        fingerprint = hashlib.sha256(
            json.dumps(
                {"event": str(event_id), "revision": body.revision, "recipients": body.recipients},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        try:
            with self.engine.begin() as c:
                self._set_actor(c, actor)
                profile = (
                    c.execute(
                        select(HostProfile.__table__)
                        .where(HostProfile.user_id == actor)
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if not profile:
                    raise failure(409, "PROFILE_REQUIRED", "Complete your host profile first.")
                previous = c.execute(
                    text("""SELECT request_hash FROM app_private.invitation_batches
                    WHERE id=:id AND user_id=:actor"""),
                    {"id": body.idempotency_key, "actor": actor},
                ).scalar()
                if previous:
                    if previous != fingerprint:
                        raise failure(
                            409,
                            "IDEMPOTENCY_CONFLICT",
                            "Retry the original recipients or start a new invitation.",
                        )
                    return self._status(c, actor, body.idempotency_key)
                event = (
                    c.execute(
                        select(EventType.__table__)
                        .where(EventType.id == event_id, EventType.user_id == actor)
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if not event:
                    raise failure(404, "EVENT_NOT_FOUND", "This event type is not available.")
                if not event["published"] or event["revision"] != body.revision:
                    raise failure(
                        409,
                        "EVENT_CHANGED",
                        "Reload and review the published event before sharing.",
                    )
                used = c.execute(
                    text("""SELECT COALESCE(sum(recipient_count),0)
                    FROM app_private.invitation_batches WHERE user_id=:actor
                    AND created_at >=
                        date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"""),
                    {"actor": actor},
                ).scalar_one()
                if used + len(body.recipients) > 20:
                    raise failure(
                        429, "INVITATION_LIMIT", "You can invite up to 20 recipients per UTC day."
                    )
                budget = c.execute(
                    text("""INSERT INTO app_private.invitation_budget(day,recipients)
                    VALUES ((now() AT TIME ZONE 'UTC')::date,:n)
                    ON CONFLICT(day) DO UPDATE SET recipients=invitation_budget.recipients+:n
                    WHERE invitation_budget.recipients+:n<=50 RETURNING recipients"""),
                    {"n": len(body.recipients)},
                ).first()
                if not budget:
                    raise failure(
                        429,
                        "INVITATION_LIMIT",
                        "Email sharing reached today's app limit. Share the public link directly.",
                    )
                c.execute(
                    text("""INSERT INTO app_private.invitation_batches
                    (id,user_id,event_id,request_hash,recipient_count)
                    VALUES (:id,:actor,:event,:hash,:n)"""),
                    {
                        "id": body.idempotency_key,
                        "actor": actor,
                        "event": event_id,
                        "hash": fingerprint,
                        "n": len(body.recipients),
                    },
                )
                vault = TokenVault(settings.token_encryption_key)
                for recipient in body.recipients:
                    payload = invitation_payload(profile, event, recipient, settings)
                    c.execute(
                        InvitationJob.__table__.insert().values(
                            id=uuid4(),
                            batch_id=body.idempotency_key,
                            user_id=actor,
                            payload_ciphertext=vault.seal(actor, json.dumps(payload)),
                        )
                    )
                return self._status(c, actor, body.idempotency_key)
        except EmailError:
            raise failure(
                503, "EMAIL_NOT_CONFIGURED", "Check the configured email sender and app URL."
            ) from None
        except SQLAlchemyError:
            raise failure(
                503,
                "INVITATION_UNAVAILABLE",
                "Invitation could not be verified. Retry the same recipients.",
            ) from None


def get_invitation_repository():
    try:
        return InvitationRepository(get_settings().database_url)
    except ValueError:
        raise failure(
            503, "INVITATION_UNAVAILABLE", "Invitation storage is not available."
        ) from None
