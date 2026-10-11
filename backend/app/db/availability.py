from sqlalchemy import Column, DateTime, Integer, Uuid, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import SQLAlchemyError

from app.auth import failure
from app.config import get_settings
from app.db.events import EventType
from app.db.profiles import Base, HostProfile, ProfileRepository


class Availability(Base):
    __tablename__ = "availability"
    __table_args__ = {"schema": "app_private"}
    user_id = Column(Uuid, primary_key=True)
    payload = Column(JSONB, nullable=False)
    revision = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ScheduleRepository(ProfileRepository):
    def load(self, actor):
        try:
            with self.engine.begin() as c:
                self._set_actor(c, actor)
                row = (
                    c.execute(select(Availability.__table__).where(Availability.user_id == actor))
                    .mappings()
                    .first()
                )
                return dict(row["payload"], revision=row["revision"]) if row else None
        except SQLAlchemyError:
            raise failure(
                503, "SCHEDULE_UNAVAILABLE", "Availability could not be loaded. Try again."
            ) from None

    def save(self, actor, payload, revision):
        try:
            with self.engine.begin() as c:
                self._set_actor(c, actor)
                profile = c.execute(
                    select(HostProfile.user_id)
                    .where(HostProfile.user_id == actor)
                    .with_for_update()
                ).first()
                if not profile:
                    raise failure(409, "PROFILE_REQUIRED", "Complete your profile first.")
                row = c.execute(
                    select(Availability.revision).where(Availability.user_id == actor)
                ).first()
                if (row.revision if row else 0) != revision:
                    raise failure(
                        409, "STALE_SCHEDULE", "Availability changed. Reload before saving."
                    )
                statement = insert(Availability).values(
                    user_id=actor, payload=payload, revision=revision + 1
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[Availability.user_id],
                    set_={"payload": payload, "revision": revision + 1, "updated_at": func.now()},
                )
                c.execute(statement)
                return dict(payload, revision=revision + 1)
        except SQLAlchemyError:
            raise failure(
                503, "SCHEDULE_UNAVAILABLE", "Availability could not be saved. Try again."
            ) from None

    def public_schedule(self, username, slug):
        try:
            with self.engine.begin() as c:
                c.execute(text("SET LOCAL ROLE petitecalendar_public"))
                e, p, a = EventType.__table__, HostProfile.__table__, Availability.__table__
                row = (
                    c.execute(
                        select(e, a.c.payload)
                        .join(p, e.c.user_id == p.c.user_id)
                        .outerjoin(a, e.c.user_id == a.c.user_id)
                        .where(p.c.username == username, e.c.slug == slug, e.c.published.is_(True))
                    )
                    .mappings()
                    .first()
                )
                if not row:
                    raise failure(404, "EVENT_NOT_FOUND", "This event is not available.")
                return dict(row)
        except SQLAlchemyError:
            raise failure(
                503, "SCHEDULE_UNAVAILABLE", "Available times could not be loaded. Try again."
            ) from None


def get_schedule_repository():
    try:
        return ScheduleRepository(get_settings().database_url)
    except ValueError:
        raise failure(
            503, "SCHEDULE_UNAVAILABLE", "Availability storage is not available."
        ) from None
