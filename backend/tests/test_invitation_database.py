import os
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from app.api.events import EventInput
from app.api.invitations import InvitationInput
from app.config import Settings, get_settings
from app.db.events import EventRepository
from app.db.invitations import InvitationJob, InvitationRepository
from app.invitation_worker import InvitationWorker
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1", reason="Opt-in rollback-only database test"
)
def test_invitation_isolation_deduplication_limits_and_delivery(monkeypatch):
    repo = InvitationRepository(get_settings().database_url)
    settings = Settings(
        token_encryption_key=Fernet.generate_key().decode(),
        resend_api_key="synthetic",
        email_from="bookings@example.com",
        app_base_url="https://app.example.com",
    )
    monkeypatch.setattr("app.db.invitations.get_settings", lambda: settings)
    first, other = uuid4(), uuid4()
    with repo.engine.connect() as c:
        transaction = c.begin()
        try:
            c.execute(text("INSERT INTO auth.users(id) VALUES (:a),(:b)"), {"a": first, "b": other})
            c.execute(
                text("""INSERT INTO app_private.host_profiles
                (user_id,display_name,username,timezone)
                VALUES (:a,'Sample host',:n,'UTC'),(:b,'Other host',:m,'UTC')"""),
                {
                    "a": first,
                    "b": other,
                    "n": "invite-" + uuid4().hex[:12],
                    "m": "invite-" + uuid4().hex[:12],
                },
            )

            class Engine:
                @contextmanager
                def begin(self):
                    with c.begin_nested():
                        yield c

            engine = Engine()
            repo.engine = engine
            events = EventRepository.__new__(EventRepository)
            events.engine = engine
            values = EventInput(
                title="Review", slug="review", durations=[30], default_duration=30
            ).model_dump()
            draft = events.save_event(first, values)
            body = InvitationInput(
                revision=1, recipients=["guest@example.com"], idempotency_key=uuid4()
            )
            with pytest.raises(HTTPException) as unpublished:
                repo.queue(first, UUID(draft["id"]), body)
            assert unpublished.value.detail["code"] == "EVENT_CHANGED"
            event = events.save_event(first, values | {"published": True}, UUID(draft["id"]), 1)
            body.revision = event["revision"]
            batch = repo.queue(first, UUID(event["id"]), body)
            assert batch["counts"] == {"queued": 1}
            assert repo.queue(first, UUID(event["id"]), body) == batch
            with pytest.raises(HTTPException) as forbidden:
                repo.status(other, UUID(event["id"]), body.idempotency_key)
            assert forbidden.value.status_code == 404
            with pytest.raises(HTTPException) as ownership:
                repo.queue(other, UUID(event["id"]), body)
            assert ownership.value.status_code == 404
            changed = body.model_copy(update={"recipients": ["other@example.com"]})
            with pytest.raises(HTTPException) as conflict:
                repo.queue(first, UUID(event["id"]), changed)
            assert conflict.value.detail["code"] == "IDEMPOTENCY_CONFLICT"
            repo._set_actor(c, first)
            with pytest.raises(SQLAlchemyError):
                with c.begin_nested():
                    c.execute(select(InvitationJob.payload_ciphertext)).all()
            deliveries = []

            class Provider:
                def send(self, payload, key):
                    deliveries.append((payload, key))
                    return "synthetic-provider-id"

            worker = InvitationWorker(engine=engine, provider=Provider(), settings=settings)
            # Synthetic job is visible only inside this uncommitted transaction.
            job = worker.claim(first)
            assert "guest@example.com" not in job["payload_ciphertext"]
            worker.deliver(job)
            assert deliveries[0][0]["to"] == ["guest@example.com"]
            assert deliveries[0][1] == f"event-invitation/{job['id']}"
            assert repo.status(first, UUID(event["id"]), body.idempotency_key)["counts"] == {
                "accepted": 1
            }
            assert worker.claim(first) is None
            # Clear payload at terminal delivery, preserving only status metadata.
            worker._role(c)
            assert (
                c.execute(
                    select(InvitationJob.payload_ciphertext).where(InvitationJob.id == job["id"])
                ).scalar()
                is None
            )
            repo.queue(
                first,
                UUID(event["id"]),
                body.model_copy(
                    update={
                        "idempotency_key": uuid4(),
                        "recipients": [f"g{i}@example.com" for i in range(10)],
                    }
                ),
            )
            with pytest.raises(HTTPException) as limit:
                repo.queue(
                    first,
                    UUID(event["id"]),
                    body.model_copy(
                        update={
                            "idempotency_key": uuid4(),
                            "recipients": [f"h{i}@example.com" for i in range(10)],
                        }
                    ),
                )
            assert limit.value.status_code == 429
        finally:
            transaction.rollback()
