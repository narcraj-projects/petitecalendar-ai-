from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from app.auth import failure
from app.config import get_settings
from app.db.profiles import Base, HostProfile, ProfileRepository


class EventType(Base):
    __tablename__ = "event_types"
    __table_args__ = {"schema": "app_private"}
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_private.host_profiles.user_id"))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(2000))
    slug: Mapped[str] = mapped_column(String(64))
    durations: Mapped[list] = mapped_column(JSONB)
    default_duration: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(160))
    notice_minutes: Mapped[int] = mapped_column(Integer)
    horizon_days: Mapped[int] = mapped_column(Integer)
    buffer_before: Mapped[int] = mapped_column(Integer)
    buffer_after: Mapped[int] = mapped_column(Integer)
    max_per_day: Mapped[int] = mapped_column(Integer)
    cancellation_hours: Mapped[int] = mapped_column(Integer)
    reschedule_hours: Mapped[int] = mapped_column(Integer)
    reschedule_requires_approval: Mapped[bool] = mapped_column(Boolean)
    allow_alternatives: Mapped[bool] = mapped_column(Boolean)
    published: Mapped[bool] = mapped_column(Boolean)
    revision: Mapped[int] = mapped_column(Integer)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now())


def event_dict(row):
    values = dict(row)
    return {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in values.items()
        if key not in {"created_at", "updated_at", "user_id"}
    }


class EventRepository(ProfileRepository):
    def list_events(self, actor):
        try:
            with self.engine.begin() as c:
                self._set_actor(c, actor)
                rows = c.execute(
                    select(EventType.__table__)
                    .where(EventType.user_id == actor)
                    .order_by(EventType.created_at.desc(), EventType.id)
                ).mappings()
                return [event_dict(row) for row in rows]
        except SQLAlchemyError:
            raise failure(
                503, "EVENT_UNAVAILABLE", "Event types could not be loaded. Try again."
            ) from None

    def save_event(self, actor, values, event_id=None, revision=None):
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
                if profile["username"] == "ananya" and values["slug"] == "career-strategy":
                    raise failure(
                        422, "RESERVED_ROUTE", "Choose another slug; this route is the demo."
                    )
                if event_id:
                    statement = (
                        EventType.__table__.update()
                        .where(
                            EventType.id == event_id,
                            EventType.user_id == actor,
                            EventType.revision == revision,
                        )
                        .values(**values, revision=revision + 1, updated_at=func.now())
                    )
                else:
                    statement = EventType.__table__.insert().values(
                        id=uuid4(), user_id=actor, **values, published=False, revision=1
                    )
                row = c.execute(statement.returning(EventType.__table__)).mappings().first()
                if not row:
                    own = c.execute(
                        select(EventType.id).where(
                            EventType.id == event_id, EventType.user_id == actor
                        )
                    ).first()
                    if own:
                        raise failure(
                            409, "STALE_EVENT", "This event changed. Reload before saving again."
                        )
                    raise failure(404, "EVENT_NOT_FOUND", "This event type is not available.")
                return event_dict(row)
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise failure(
                    409, "SLUG_TAKEN", "You already have an event with this slug."
                ) from None
            raise failure(
                503, "EVENT_UNAVAILABLE", "Event type could not be saved. Try again."
            ) from None
        except SQLAlchemyError:
            raise failure(
                503, "EVENT_UNAVAILABLE", "Event type could not be saved. Try again."
            ) from None

    def public_event(self, username, slug):
        from app.db.availability import Availability

        try:
            with self.engine.begin() as c:
                c.execute(text("SET LOCAL ROLE petitecalendar_public"))
                e, p = EventType.__table__, HostProfile.__table__
                row = (
                    c.execute(
                        select(e, p.c.display_name, p.c.timezone)
                        .join(p, e.c.user_id == p.c.user_id)
                        .where(p.c.username == username, e.c.slug == slug, e.c.published.is_(True))
                    )
                    .mappings()
                    .first()
                )
                if not row:
                    raise failure(404, "EVENT_NOT_FOUND", "This event is not available.")
                schedule = c.execute(
                    select(Availability.payload).where(Availability.user_id == row["user_id"])
                ).scalar()
                status = (
                    "ready"
                    if schedule and schedule["enabled"]
                    else ("paused" if schedule else "not_configured")
                )
                return {
                    key: row[key]
                    for key in (
                        "title",
                        "description",
                        "durations",
                        "default_duration",
                        "location",
                        "notice_minutes",
                        "horizon_days",
                        "buffer_before",
                        "buffer_after",
                        "cancellation_hours",
                        "reschedule_hours",
                        "reschedule_requires_approval",
                        "allow_alternatives",
                    )
                } | {
                    "host": {"name": row["display_name"], "timezone": row["timezone"]},
                    "username": username,
                    "slug": slug,
                    "availability_ready": status == "ready",
                    "availability_status": status,
                    "schedule_timezone": schedule["timezone"] if schedule else row["timezone"],
                    "mode": "published",
                }
        except SQLAlchemyError:
            raise failure(
                503, "EVENT_UNAVAILABLE", "This event could not be loaded. Try again."
            ) from None


def get_event_repository():
    try:
        return EventRepository(get_settings().database_url)
    except ValueError:
        raise failure(503, "EVENT_UNAVAILABLE", "Event storage is not available.") from None
