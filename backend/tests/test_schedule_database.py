import os
from contextlib import contextmanager
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from app.api.availability import ScheduleInput
from app.api.events import EventInput
from app.config import get_settings
from app.db.availability import ScheduleRepository
from app.db.events import EventRepository
from app.services.availability import public_slots
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1", reason="Opt-in development database test"
)
def test_saved_availability_public_slots_and_tenant_isolation():
    repo = ScheduleRepository(get_settings().database_url)
    events = EventRepository(get_settings().database_url)
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
                    (user_id,display_name,username,timezone)
                    VALUES (:a,'Schedule fixture',:name,'Asia/Kolkata'),
                           (:b,'Other fixture',:other,'UTC')"""),
                    {"a": first, "b": second, "name": username, "other": username + "-other"},
                )

                class TransactionEngine:
                    @contextmanager
                    def begin(self):
                        with c.begin_nested():
                            yield c

                repo.engine = events.engine = TransactionEngine()
                values = EventInput(
                    title="Test event",
                    slug="strategy-call",
                    durations=[30, 45, 60],
                    default_duration=45,
                    notice_minutes=0,
                    buffer_before=0,
                    buffer_after=0,
                ).model_dump()
                event = events.save_event(first, values)
                events.save_event(first, values | {"published": True}, event["id"], 1)
                assert repo.load(first) is None
                assert not events.public_event(username, "strategy-call")["availability_ready"]
                payload = ScheduleInput(
                    revision=0,
                    timezone="Asia/Kolkata",
                    enabled=True,
                    weekly=[{"weekday": n, "start": "09:00", "end": "17:00"} for n in range(5)],
                    overrides=[
                        {"date": "2026-10-13", "windows": []},
                        {"date": "2026-10-14", "windows": [{"start": "10:00", "end": "12:00"}]},
                    ],
                    focus=[{"weekday": 0, "start": "09:00", "end": "11:00"}],
                    increment_minutes=15,
                    host_daily_cap=4,
                    weekly_cap_minutes=720,
                    prefer_cluster=True,
                ).model_dump(mode="json", exclude={"revision"})
                saved = repo.save(first, payload, 0)
                assert repo.load(first) == saved
                assert repo.load(second) is None
                repo._set_actor(c, second)
                assert (
                    c.execute(
                        text("UPDATE app_private.availability SET revision=99 WHERE user_id=:id"),
                        {"id": first},
                    ).rowcount
                    == 0
                )
                with pytest.raises(HTTPException) as stale:
                    repo.save(first, payload, 0)
                assert stale.value.detail["code"] == "STALE_SCHEDULE"
                metadata = events.public_event(username, "strategy-call")
                assert metadata["availability_ready"] is True
                assert "weekly" not in metadata and "focus" not in metadata
                row = repo.public_schedule(username, "strategy-call")

                def slots(day):
                    return public_slots(
                        row,
                        start_date=day,
                        end_date=day,
                        timezone="Asia/Kolkata",
                        duration=45,
                        now=datetime(2026, 10, 11, tzinfo=UTC),
                    )

                monday = slots(date(2026, 10, 12))
                assert monday["slots"][0]["start"] == "2026-10-12T05:30:00+00:00"
                assert "focus_blocks" in monday["explanations"]
                assert not slots(date(2026, 10, 13))["slots"]
                wednesday = slots(date(2026, 10, 14))
                assert wednesday["slots"][0]["start"] == "2026-10-14T04:30:00+00:00"
                assert wednesday["slots"][-1]["end"] <= "2026-10-14T06:30:00+00:00"
                repo.save(first, payload | {"enabled": False}, 1)
                assert (
                    events.public_event(username, "strategy-call")["availability_status"]
                    == "paused"
                )
                row = repo.public_schedule(username, "strategy-call")
                assert slots(date(2026, 10, 12))["explanations"] == ["availability_paused"]
                assert repo.load(first)["revision"] == 2
            finally:
                transaction.rollback()
    except SQLAlchemyError:
        pytest.fail(
            "Schedule database check failed; credentials and SQL details withheld.", pytrace=False
        )
