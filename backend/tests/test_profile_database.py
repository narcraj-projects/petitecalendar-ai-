"""Development PostgreSQL checks; every temporary fixture is rolled back."""

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from app.config import get_settings
from app.db.profiles import ProfileRepository
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1", reason="Opt-in development database test"
)
def test_database_tenant_isolation_and_uniqueness():
    repo = ProfileRepository(get_settings().database_url)
    first, second = uuid4(), uuid4()
    username = "check-" + uuid4().hex[:16]
    try:
        with repo.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text("INSERT INTO auth.users (id) VALUES (:a), (:b)"), {"a": first, "b": second}
                )
                repo._set_actor(connection, first)
                connection.execute(
                    text("""INSERT INTO app_private.host_profiles
                    (user_id, display_name, username, timezone)
                    VALUES (:id, 'Temporary fixture', :name, 'UTC')"""),
                    {"id": first, "name": username},
                )
                repo._set_actor(connection, second)
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM app_private.host_profiles")
                    ).scalar()
                    == 0
                )
                assert (
                    connection.execute(
                        text("""UPDATE app_private.host_profiles
                    SET display_name = 'Blocked' WHERE user_id = :id"""),
                        {"id": first},
                    ).rowcount
                    == 0
                )
                with connection.begin_nested() as nested:
                    with pytest.raises(SQLAlchemyError) as conflict:
                        connection.execute(
                            text("""INSERT INTO app_private.host_profiles
                            (user_id, display_name, username, timezone)
                            VALUES (:id, 'Other fixture', :name, 'UTC')"""),
                            {"id": second, "name": username},
                        )
                    assert conflict.value.orig.sqlstate == "23505"
                    nested.rollback()
                with connection.begin_nested() as nested:
                    with pytest.raises(SQLAlchemyError) as forbidden:
                        connection.execute(
                            text("""INSERT INTO app_private.host_profiles
                            (user_id, display_name, username, timezone)
                            VALUES (:id, 'Blocked', :name, 'UTC')"""),
                            {"id": first, "name": username + "-other"},
                        )
                    assert forbidden.value.orig.sqlstate == "42501"
                    nested.rollback()
                repo._set_actor(connection, first)
                assert (
                    connection.execute(
                        text("SELECT display_name FROM app_private.host_profiles")
                    ).scalar()
                    == "Temporary fixture"
                )

                class TransactionEngine:
                    @contextmanager
                    def begin(self):
                        with connection.begin_nested():
                            yield connection

                # Exercise the actual repository within the rollback-only fixture transaction.
                repo.engine = TransactionEngine()
                values = {
                    "display_name": "Updated fixture",
                    "username": username,
                    "timezone": "Asia/Tokyo",
                }
                saved = repo.save(first, values)
                assert saved == {"user_id": str(first), **values}
                assert repo.get(first) == saved
                assert repo.get(second) is None
                with pytest.raises(HTTPException) as duplicate:
                    repo.save(second, values)
                assert duplicate.value.status_code == 409
            finally:
                transaction.rollback()
    except SQLAlchemyError:
        pytest.fail(
            "Development database check failed; credentials and SQL details withheld.",
            pytrace=False,
        )
