import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from app.api.events import EventInput
from app.config import get_settings
from app.db.events import EventRepository
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1", reason="Opt-in development database test"
)
def test_event_lifecycle_isolation_publication_and_revisions():
    repo = EventRepository(get_settings().database_url)
    first, second = uuid4(), uuid4()
    username = "check-" + uuid4().hex[:16]
    try:
        with repo.engine.connect() as c:
            transaction = c.begin()
            try:
                c.execute(
                    text("INSERT INTO auth.users (id) VALUES (:a),(:b)"), {"a": first, "b": second}
                )
                c.execute(
                    text("""INSERT INTO app_private.host_profiles
                    (user_id, display_name, username, timezone)
                    VALUES (:a,'Temporary fixture',:name,'UTC'),
                           (:b,'Other fixture',:other,'UTC')"""),
                    {"a": first, "b": second, "name": username, "other": username + "-other"},
                )

                class TransactionEngine:
                    @contextmanager
                    def begin(self):
                        with c.begin_nested():
                            yield c

                repo.engine = TransactionEngine()
                values = EventInput(
                    title="Test event",
                    slug="strategy-call",
                    durations=[30, 45, 60],
                    default_duration=45,
                ).model_dump()
                draft = repo.save_event(first, values)
                assert draft["published"] is False
                assert len(repo.list_events(first)) == 1
                assert repo.list_events(second) == []
                with pytest.raises(HTTPException) as hidden:
                    repo.public_event(username, values["slug"])
                assert hidden.value.status_code == 404
                with pytest.raises(HTTPException) as forbidden:
                    repo.save_event(second, values | {"published": True}, draft["id"], 1)
                assert forbidden.value.status_code == 404
                with pytest.raises(HTTPException) as conflict:
                    repo.save_event(first, values)
                assert conflict.value.status_code == 409
                # Identical slugs are allowed for different hosts.
                repo.save_event(second, values)
                published = repo.save_event(first, values | {"published": True}, draft["id"], 1)
                assert published["revision"] == 2
                public = repo.public_event(username, values["slug"])
                assert public["title"] == "Test event"
                assert not {"id", "user_id", "revision", "created_at"} & public.keys()
                assert public["availability_ready"] is False
                with pytest.raises(HTTPException) as stale:
                    repo.save_event(first, values | {"published": False}, draft["id"], 1)
                assert stale.value.detail["code"] == "STALE_EVENT"
                renamed = repo.save_event(
                    first, values | {"slug": "new-slug", "published": True}, draft["id"], 2
                )
                assert repo.public_event(username, "new-slug")["title"] == "Test event"
                with pytest.raises(HTTPException):
                    repo.public_event(username, values["slug"])
                repo.save_event(
                    first,
                    values | {"slug": "new-slug", "published": False},
                    draft["id"],
                    renamed["revision"],
                )
                with pytest.raises(HTTPException):
                    repo.public_event(username, "new-slug")
            finally:
                transaction.rollback()
    except SQLAlchemyError:
        pytest.fail(
            "Database event check failed; SQL details and credentials withheld.", pytrace=False
        )
