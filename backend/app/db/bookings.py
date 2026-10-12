import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Column, DateTime, Integer, String, Uuid, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import failure
from app.config import get_settings
from app.db.availability import Availability, ScheduleRepository
from app.db.calendar import CalendarJob, CalendarRepository, GoogleConnection, connection_stamp
from app.db.email import EmailJob
from app.db.events import EventType
from app.db.profiles import Base, HostProfile, ProfileRepository
from app.domain.availability import Interval, Occupancy, get_available_slots
from app.integrations.google import TokenVault
from app.services.availability import schedule_rules


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = {"schema": "app_private"}
    id = Column(Uuid, primary_key=True)
    user_id = Column(Uuid, nullable=False)
    event_id = Column(Uuid, nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    blocked_start = Column(DateTime(timezone=True), nullable=False)
    blocked_end = Column(DateTime(timezone=True), nullable=False)
    duration = Column(Integer, nullable=False)
    invitee_name = Column(String(80), nullable=False)
    invitee_email = Column(String(254), nullable=False)
    invitee_timezone = Column(String(100), nullable=False)
    snapshot = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False)
    revision = Column(Integer, nullable=False)
    idempotency_key = Column(Uuid, nullable=False)
    request_hash = Column(String(64), nullable=False)
    capability_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class BookingOutbox(Base):
    __tablename__ = "booking_outbox"
    __table_args__ = {"schema": "app_private"}
    booking_id = Column(Uuid, primary_key=True)
    revision = Column(Integer, primary_key=True)
    event_type = Column(String(40), primary_key=True)
    user_id = Column(Uuid, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def booking_view(row):
    keys = (
        "start_at",
        "end_at",
        "duration",
        "invitee_name",
        "invitee_email",
        "invitee_timezone",
        "snapshot",
        "status",
        "revision",
        "created_at",
    )
    return {
        "id": str(row["id"]),
        **{k: row[k] for k in keys},
        "calendar_status": "not_connected",
        "email_status": "not_enabled",
        "updated_at": row.get("updated_at", row["created_at"]),
    }


def occupancy_from_rows(rows, event_id, timezone):
    zone = ZoneInfo(timezone)
    host_counts, event_counts, week_minutes = {}, {}, {}
    intervals = []
    for row in rows:
        day = row["start_at"].astimezone(zone).date()
        week = day - timedelta(days=day.weekday())
        host_counts[day] = host_counts.get(day, 0) + 1
        if row["event_id"] == event_id:
            event_counts[day] = event_counts.get(day, 0) + 1
        week_minutes[week] = week_minutes.get(week, 0) + row["duration"]
        intervals.append(Interval(row["blocked_start"], row["blocked_end"]))
    return Occupancy(
        reservations=tuple(intervals),
        event_counts=event_counts,
        host_counts=host_counts,
        week_minutes=week_minutes,
    )


class BookingRepository(ProfileRepository):
    def _views(self, c, rows):
        if not rows:
            return []
        jobs = (
            c.execute(
                select(
                    CalendarJob.booking_id,
                    CalendarJob.revision,
                    CalendarJob.status,
                    CalendarJob.meet_url,
                    CalendarJob.last_error,
                ).where(CalendarJob.booking_id.in_([r["id"] for r in rows]))
            )
            .mappings()
            .all()
        )
        lookup = {(j["booking_id"], j["revision"]): j for j in jobs}
        emails = (
            c.execute(
                select(EmailJob.booking_id, EmailJob.revision, EmailJob.status).where(
                    EmailJob.booking_id.in_([r["id"] for r in rows])
                )
            )
            .mappings()
            .all()
        )
        email_lookup = {(j["booking_id"], j["revision"]): j["status"] for j in emails}
        result = []
        for row in rows:
            value = booking_view(row)
            value["email_status"] = email_lookup.get((row["id"], row["revision"]), "not_enabled")
            job = lookup.get((row["id"], row["revision"]))
            if job:
                value.update(
                    calendar_status=job["status"],
                    meet_url=job["meet_url"],
                    calendar_error=job["last_error"],
                )
            value["change_request"] = self._change_view(c, row["id"])
            result.append(value)
        return result

    def _view(self, c, row):
        result = booking_view(row)
        job = (
            c.execute(
                select(CalendarJob.status, CalendarJob.meet_url, CalendarJob.last_error).where(
                    CalendarJob.booking_id == row["id"], CalendarJob.revision == row["revision"]
                )
            )
            .mappings()
            .first()
        )
        if job:
            result.update(
                calendar_status=job["status"],
                meet_url=job["meet_url"],
                calendar_error=job["last_error"],
            )
        result["email_status"] = (
            c.execute(
                select(EmailJob.status).where(
                    EmailJob.booking_id == row["id"], EmailJob.revision == row["revision"]
                )
            ).scalar_one_or_none()
            or "not_enabled"
        )
        result["change_request"] = self._change_view(c, row["id"])
        return result

    def _change_view(self, c, booking_id):
        from app.db.lifecycle import BookingChange

        row = (
            c.execute(
                select(
                    BookingChange.id,
                    BookingChange.booking_revision,
                    BookingChange.candidates,
                    BookingChange.timezone,
                    BookingChange.status,
                    BookingChange.created_at,
                )
                .where(BookingChange.booking_id == booking_id)
                .order_by(BookingChange.created_at.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def _scope(self, c, host=None, capability=""):
        c.execute(text("SET LOCAL ROLE petitecalendar_booking"))
        c.execute(
            text(
                "SELECT set_config('app.booking_host',:host,true), "
                "set_config('app.booking_capability',:cap,true)"
            ),
            {"host": str(host) if host else "", "cap": capability},
        )

    def _occupancy(self, c, host, event_id, timezone, start, end, exclude=None):
        # Include complete boundary weeks and adjacent buffered meetings.
        lower = datetime.combine(start - timedelta(days=8), datetime.min.time(), UTC)
        upper = datetime.combine(end + timedelta(days=9), datetime.min.time(), UTC)
        rows = (
            c.execute(
                select(Booking.__table__).where(
                    Booking.user_id == host,
                    Booking.status == "confirmed",
                    Booking.blocked_end > lower,
                    Booking.blocked_start < upper,
                )
            )
            .mappings()
            .all()
        )
        return occupancy_from_rows([r for r in rows if r["id"] != exclude], event_id, timezone)

    def occupancy(self, row, start, end):
        try:
            with self.engine.begin() as c:
                self._scope(c, row["user_id"])
                return self._occupancy(
                    c, row["user_id"], row["id"], row["payload"]["timezone"], start, end
                )
        except SQLAlchemyError:
            raise failure(
                503, "BOOKING_UNAVAILABLE", "Available times could not be loaded."
            ) from None

    def reserve(self, username, slug, body, now=None, calendar_service=None):
        now = now or datetime.now(UTC)
        values = body.model_dump(mode="json")
        fingerprint = digest(json.dumps({"route": [username, slug], **values}, sort_keys=True))
        try:
            with self.engine.begin() as c:
                self._scope(c, capability=digest(body.capability))
                previous = (
                    c.execute(
                        select(Booking.__table__).where(
                            Booking.idempotency_key == body.idempotency_key,
                            Booking.capability_hash == digest(body.capability),
                        )
                    )
                    .mappings()
                    .first()
                )
                if previous:
                    if previous["request_hash"] != fingerprint:
                        raise failure(
                            409, "IDEMPOTENCY_CONFLICT", "Retry with the original booking details."
                        )
                    return self._view(c, previous)
            resolver = ScheduleRepository(get_settings().database_url)
            resolver.engine = self.engine
            initial = resolver.public_schedule(username, slug)
            from app.services.calendar import CalendarService

            start = body.start.astimezone(UTC)
            day = start.astimezone(ZoneInfo(body.timezone)).date()
            lower = datetime.combine(day - timedelta(days=1), datetime.min.time(), UTC)
            upper = datetime.combine(day + timedelta(days=2), datetime.min.time(), UTC)
            if calendar_service:
                external = calendar_service.busy(initial["user_id"], lower, upper)
            else:
                calendar_repository = CalendarRepository(get_settings().database_url)
                calendar_repository.engine = self.engine
                with CalendarService(repository=calendar_repository) as service:
                    external = service.busy(initial["user_id"], lower, upper)
            with self.engine.begin() as c:
                self._scope(c, initial["user_id"])
                locked_profile = (
                    c.execute(
                        select(HostProfile.user_id, HostProfile.username, HostProfile.display_name)
                        .where(HostProfile.user_id == initial["user_id"])
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                previous = (
                    c.execute(
                        select(Booking.__table__).where(
                            Booking.idempotency_key == body.idempotency_key
                        )
                    )
                    .mappings()
                    .first()
                )
                if previous:
                    if previous["request_hash"] != fingerprint:
                        raise failure(
                            409, "IDEMPOTENCY_CONFLICT", "Retry with the original booking details."
                        )
                    return self._view(c, previous)
                connection = (
                    c.execute(
                        select(
                            GoogleConnection.user_id,
                            GoogleConnection.generation,
                            GoogleConnection.revision,
                            GoogleConnection.status,
                            GoogleConnection.destination_id,
                            GoogleConnection.create_meet,
                        ).where(GoogleConnection.user_id == initial["user_id"])
                    )
                    .mappings()
                    .first()
                )
                if connection_stamp(connection) != external.stamp:
                    raise failure(
                        409, "CALENDAR_CHANGED", "Calendar settings changed. Choose a time again."
                    )
                if locked_profile["username"] != username:
                    raise failure(
                        409, "SLOT_UNAVAILABLE", "The booking link changed. Reload this event."
                    )
                event = (
                    c.execute(
                        select(EventType.__table__).where(
                            EventType.id == initial["id"],
                            EventType.slug == slug,
                            EventType.published.is_(True),
                        )
                    )
                    .mappings()
                    .first()
                )
                schedule = c.execute(
                    select(Availability.payload).where(Availability.user_id == initial["user_id"])
                ).scalar_one_or_none()
                if not event or not schedule or not schedule["enabled"]:
                    raise failure(
                        409, "SLOT_UNAVAILABLE", "Scheduling changed. Choose another time."
                    )
                if body.duration not in event["durations"]:
                    raise failure(
                        409, "SLOT_UNAVAILABLE", "Duration options changed. Reload this event."
                    )
                rules = schedule_rules(schedule, event)
                occupied = self._occupancy(
                    c, initial["user_id"], event["id"], rules.timezone, day, day
                )
                occupied = replace(occupied, busy=external.busy)
                slots = get_available_slots(
                    rules,
                    occupied,
                    start_date=day,
                    end_date=day,
                    invitee_timezone=body.timezone,
                    duration_minutes=body.duration,
                    now=now,
                )
                slot = next((s for s in slots if s.start == start), None)
                if not slot:
                    raise failure(
                        409,
                        "SLOT_UNAVAILABLE",
                        "That time is no longer available. Choose another time.",
                    )
                snapshot = {
                    k: event[k]
                    for k in (
                        "title",
                        "location",
                        "buffer_before",
                        "buffer_after",
                        "cancellation_hours",
                        "reschedule_hours",
                        "reschedule_requires_approval",
                        "allow_alternatives",
                    )
                }
                snapshot.update(
                    host_name=locked_profile["display_name"],
                    host_timezone=rules.timezone,
                    event_revision=event["revision"],
                )
                row = (
                    c.execute(
                        Booking.__table__.insert()
                        .values(
                            id=uuid4(),
                            user_id=initial["user_id"],
                            event_id=event["id"],
                            start_at=slot.start,
                            end_at=slot.end,
                            blocked_start=slot.start - timedelta(minutes=event["buffer_before"]),
                            blocked_end=slot.end + timedelta(minutes=event["buffer_after"]),
                            duration=body.duration,
                            invitee_name=body.name,
                            invitee_email=body.email,
                            invitee_timezone=body.timezone,
                            snapshot=snapshot,
                            status="confirmed",
                            revision=1,
                            idempotency_key=body.idempotency_key,
                            request_hash=fingerprint,
                            capability_hash=digest(body.capability),
                            created_at=now,
                            updated_at=now,
                        )
                        .returning(Booking.__table__)
                    )
                    .mappings()
                    .one()
                )
                c.execute(
                    text("""INSERT INTO app_private.booking_outbox
                    (booking_id,user_id,revision,event_type)
                    VALUES (:id,:host,1,'booking_confirmed')"""),
                    {"id": row["id"], "host": initial["user_id"]},
                )
                if (
                    connection
                    and connection["status"] == "connected"
                    and connection["destination_id"]
                ):
                    c.execute(
                        CalendarJob.__table__.insert().values(
                            booking_id=row["id"],
                            revision=row["revision"],
                            user_id=initial["user_id"],
                            generation=connection["generation"],
                            destination_id=connection["destination_id"],
                            create_meet=connection["create_meet"],
                        )
                    )
                settings = get_settings()
                if settings.email_configured:
                    c.execute(
                        EmailJob.__table__.insert().values(
                            booking_id=row["id"],
                            revision=row["revision"],
                            user_id=row["user_id"],
                            capability_ciphertext=TokenVault(settings.token_encryption_key).seal(
                                row["user_id"], body.capability
                            ),
                        )
                    )
                return self._view(c, row)
        except IntegrityError:
            raise failure(
                409, "SLOT_UNAVAILABLE", "Booking details conflict. Refresh available times."
            ) from None
        except SQLAlchemyError:
            raise failure(
                503, "BOOKING_UNAVAILABLE", "Booking could not be verified. Retry the same request."
            ) from None

    def manage(self, booking_id, capability):
        try:
            with self.engine.begin() as c:
                hashed = digest(capability)
                self._scope(c, capability=hashed)
                row = (
                    c.execute(
                        select(Booking.__table__).where(
                            Booking.id == booking_id, Booking.capability_hash == hashed
                        )
                    )
                    .mappings()
                    .first()
                )
                if not row:
                    raise failure(404, "BOOKING_NOT_FOUND", "This private booking link is invalid.")
                return self._view(c, row)
        except SQLAlchemyError:
            raise failure(
                503, "BOOKING_UNAVAILABLE", "Booking could not be loaded. Try again."
            ) from None

    def dashboard(self, actor, start, end):
        try:
            with self.engine.begin() as c:
                self._set_actor(c, actor)
                schedule = c.execute(
                    select(Availability.payload).where(Availability.user_id == actor)
                ).scalar_one_or_none()
                profile_zone = (
                    c.execute(
                        select(HostProfile.timezone).where(HostProfile.user_id == actor)
                    ).scalar_one_or_none()
                    or "UTC"
                )
                zone = ZoneInfo(schedule["timezone"] if schedule else profile_zone)
                lower = datetime.combine(start, datetime.min.time(), zone)
                upper = datetime.combine(end, datetime.min.time(), zone)
                today = datetime.now(UTC).astimezone(zone).date()
                monday = today - timedelta(days=today.weekday())
                week_start = datetime.combine(monday, datetime.min.time(), zone)
                week_end = datetime.combine(monday + timedelta(days=7), datetime.min.time(), zone)
                week_rows = (
                    c.execute(
                        select(Booking.__table__).where(
                            Booking.user_id == actor,
                            Booking.status == "confirmed",
                            Booking.start_at >= week_start,
                            Booking.start_at < week_end,
                        )
                    )
                    .mappings()
                    .all()
                )
                rows = (
                    c.execute(
                        select(Booking.__table__)
                        .where(
                            Booking.user_id == actor,
                            Booking.start_at >= lower,
                            Booking.start_at < upper,
                        )
                        .order_by(Booking.start_at)
                        .limit(501)
                    )
                    .mappings()
                    .all()
                )
                return {
                    "week_bookings": [
                        {"start_at": r["start_at"], "duration": r["duration"]} for r in week_rows
                    ],
                    "week_start": monday.isoformat(),
                    "bookings": self._views(c, rows[:500]),
                    "truncated": len(rows) > 500,
                    "schedule": {
                        k: schedule[k] for k in ("timezone", "host_daily_cap", "weekly_cap_minutes")
                    }
                    if schedule
                    else None,
                }
        except SQLAlchemyError:
            raise failure(
                503, "BOOKING_UNAVAILABLE", "Bookings could not be loaded. Try again."
            ) from None


def get_booking_repository():
    try:
        return BookingRepository(get_settings().database_url)
    except ValueError:
        raise failure(503, "BOOKING_UNAVAILABLE", "Booking storage is not available.") from None
