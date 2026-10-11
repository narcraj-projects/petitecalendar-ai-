"""Real PostgreSQL proposal confirmation and isolation; everything rolls back."""

import os
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from app.api.assistant import AssistantInput
from app.api.events import EventInput
from app.config import Settings, get_settings
from app.db.events import EventRepository
from app.services.assistant import Assistant, EventPatch
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


@pytest.mark.skipif(os.getenv("RUN_DATABASE_TESTS") != "1", reason="Opt-in database test")
def test_agent_draft_confirmation_uses_real_rls_host_lock_and_revision():
    repo = EventRepository(get_settings().database_url)
    first, other = uuid4(), uuid4()
    try:
        with repo.engine.connect() as c:
            transaction = c.begin()
            try:
                c.execute(
                    text("INSERT INTO auth.users(id) VALUES (:a),(:b)"), {"a": first, "b": other}
                )
                c.execute(
                    text("""INSERT INTO app_private.host_profiles
                    (user_id,display_name,username,timezone) VALUES
                    (:a,'Agent fixture',:n,'UTC'),(:b,'Other agent fixture',:m,'UTC')"""),
                    {
                        "a": first,
                        "b": other,
                        "n": "agent-" + uuid4().hex[:16],
                        "m": "agent-" + uuid4().hex[:16],
                    },
                )

                class Engine:
                    @contextmanager
                    def begin(self):
                        with c.begin_nested():
                            yield c

                repo.engine = Engine()
                event = repo.save_event(
                    first,
                    EventInput(
                        title="Fixture call",
                        slug="fixture-call",
                        durations=[30],
                        default_duration=30,
                    ).model_dump(),
                )

                class Provider:
                    def interpret(self, *args):
                        return "draft_event_settings", EventPatch.model_validate(
                            dict.fromkeys(EventPatch.model_fields)
                            | {"durations": [45], "default_duration": 45}
                        )

                service = Assistant(
                    Settings(token_encryption_key=Fernet.generate_key().decode()),
                    Provider(),
                    events=repo,
                )
                body = AssistantInput(
                    messages=["make it 45 minutes"], timezone="UTC", event_id=UUID(event["id"])
                )
                proposal = service.propose(body, actor=first)
                assert repo.list_events(first)[0]["default_duration"] == 30
                with pytest.raises(HTTPException):
                    service.propose(body, actor=other)
                with pytest.raises(HTTPException):
                    service.confirm(proposal["proposal"], actor=other)
                saved = service.confirm(proposal["proposal"], actor=first)
                assert saved["event"]["default_duration"] == 45 and saved["event"]["revision"] == 2
                assert service.confirm(proposal["proposal"], actor=first) == saved
                stale = service.propose(body, actor=first)
                assert stale["kind"] == "clarification"
                service.provider.interpret = lambda *args: (
                    "draft_event_settings",
                    EventPatch.model_validate(
                        dict.fromkeys(EventPatch.model_fields) | {"buffer_before": 25}
                    ),
                )
                stale = service.propose(body, actor=first)
                values = {k: v for k, v in saved["event"].items() if k not in {"id", "revision"}}
                repo.save_event(first, values | {"buffer_after": 20}, UUID(event["id"]), 2)
                with pytest.raises(HTTPException) as error:
                    service.confirm(stale["proposal"], actor=first)
                assert error.value.detail["code"] == "STALE_EVENT"
            finally:
                transaction.rollback()
    except SQLAlchemyError:
        pytest.fail("Assistant DB check failed; credentials withheld.", pytrace=False)
