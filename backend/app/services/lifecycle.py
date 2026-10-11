"""Atomic booking lifecycle shared by the UI and future agent tools."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import failure
from app.config import get_settings
from app.db.availability import Availability
from app.db.bookings import Booking, digest
from app.db.calendar import CalendarJob, GoogleConnection, connection_stamp
from app.db.email import EmailJob
from app.db.events import EventType
from app.db.lifecycle import BookingAction, BookingChange, lock_booking
from app.db.profiles import HostProfile
from app.integrations.google import TokenVault, calendar_event_id
from app.services.availability import public_slots


def require_action(booking, operation, now, host=False):
    if booking["status"] != "confirmed":
        raise failure(409, "BOOKING_CANCELLED", "This booking is already cancelled.")
    cutoff = 0 if host else booking["snapshot"][operation + "_hours"]
    if now >= booking["start_at"] - timedelta(hours=cutoff):
        raise failure(409, "POLICY_DEADLINE", "The deadline for this action has passed.")


class LifecycleService:
    def __init__(self, repository, calendar_service):
        self.repo = repository
        self.calendar = calendar_service

    def _read(self, c, booking_id, capability, actor):
        if actor:
            self.repo._set_actor(c, actor)
            query = select(Booking.__table__).where(
                Booking.id == booking_id, Booking.user_id == actor
            )
        else:
            self.repo._scope(c, capability=digest(capability))
            query = select(Booking.__table__).where(
                Booking.id == booking_id, Booking.capability_hash == digest(capability)
            )
        row = c.execute(query).mappings().first()
        if not row:
            raise failure(404, "BOOKING_NOT_FOUND", "This booking is unavailable.")
        self.repo._scope(c, row["user_id"], digest(capability) if capability else "")
        return dict(row)

    def _inputs(self, c, row):
        event = (
            c.execute(select(EventType.__table__).where(EventType.id == row["event_id"]))
            .mappings()
            .one()
        )
        schedule = c.execute(
            select(Availability.payload).where(Availability.user_id == row["user_id"])
        ).scalar_one_or_none()
        # Preserve this booking's duration and buffer contract, even after the editor changes.
        return dict(event) | {
            "durations": [row["duration"]],
            "buffer_before": row["snapshot"]["buffer_before"],
            "buffer_after": row["snapshot"]["buffer_after"],
            "payload": schedule,
        }

    def _external(self, c, row, start, end):
        jobs = (
            c.execute(select(CalendarJob.__table__).where(CalendarJob.booking_id == row["id"]))
            .mappings()
            .all()
        )
        excluded = [
            dict(j) | {"event_id": calendar_event_id(row["id"], j["revision"])} for j in jobs
        ]
        return self.calendar.busy_excluding(row["user_id"], start, end, row["id"], excluded)

    def slots(self, booking_id, capability, start, end, timezone, actor=None, now=None):
        now = now or datetime.now(UTC)
        try:
            with self.repo.engine.begin() as c:
                row = self._read(c, booking_id, capability, actor)
                require_action(row, "reschedule", now, bool(actor))
                inputs = self._inputs(c, row)
                occupied = self.repo._occupancy(
                    c,
                    row["user_id"],
                    row["event_id"],
                    inputs["payload"]["timezone"] if inputs["payload"] else "UTC",
                    start,
                    end,
                    row["id"],
                )
                external = self._external(
                    c,
                    row,
                    datetime.combine(start - timedelta(days=1), datetime.min.time(), UTC),
                    datetime.combine(end + timedelta(days=2), datetime.min.time(), UTC),
                )
            from dataclasses import replace

            report = public_slots(
                inputs,
                start_date=start,
                end_date=end,
                timezone=timezone,
                duration=row["duration"],
                now=now,
                occupancy=replace(occupied, busy=external.busy),
            )
            # Selecting the same instant is not a reschedule.
            report["slots"] = [
                s for s in report["slots"] if datetime.fromisoformat(s["start"]) != row["start_at"]
            ]
            report["calendar_status"] = "connected" if external.stamp else "not_connected"
            return report
        except SQLAlchemyError:
            raise failure(
                503, "BOOKING_UNAVAILABLE", "Available times could not be loaded."
            ) from None

    def _queue(self, c, row, event_type, capability):
        c.execute(
            text("""INSERT INTO app_private.booking_outbox(booking_id,user_id,revision,event_type)
            VALUES (:id,:host,:revision,:event)"""),
            {
                "id": row["id"],
                "host": row["user_id"],
                "revision": row["revision"],
                "event": event_type,
            },
        )
        previous = (
            c.execute(
                select(CalendarJob.__table__)
                .where(CalendarJob.booking_id == row["id"])
                .order_by(CalendarJob.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        connection = (
            c.execute(
                select(
                    GoogleConnection.user_id,
                    GoogleConnection.generation,
                    GoogleConnection.status,
                    GoogleConnection.destination_id,
                    GoogleConnection.create_meet,
                ).where(GoogleConnection.user_id == row["user_id"])
            )
            .mappings()
            .first()
        )
        # Keep the original account and destination; changing settings must not orphan old events.
        target = previous or (
            connection
            if connection and connection["status"] == "connected" and connection["destination_id"]
            else None
        )
        if target:
            c.execute(
                CalendarJob.__table__.insert().values(
                    booking_id=row["id"],
                    revision=row["revision"],
                    user_id=row["user_id"],
                    generation=target["generation"],
                    destination_id=target["destination_id"],
                    create_meet=target["create_meet"],
                    operation="cancel" if row["status"] == "cancelled" else "upsert",
                )
            )
        settings = get_settings()
        if settings.email_configured:
            c.execute(
                EmailJob.__table__.insert().values(
                    booking_id=row["id"],
                    revision=row["revision"],
                    user_id=row["user_id"],
                    event_type=event_type,
                    capability_ciphertext=TokenVault(settings.token_encryption_key).seal(
                        row["user_id"], capability or ""
                    ),
                )
            )

    def act(self, booking_id, body, capability="", actor=None, now=None):
        injected_now = now is not None
        now = now or datetime.now(UTC)
        fingerprint = digest(
            json.dumps(
                {
                    "booking": str(booking_id),
                    "actor": str(actor) if actor else digest(capability),
                    **body.model_dump(mode="json"),
                },
                sort_keys=True,
            )
        )
        try:
            # Read-only provider calls happen before the host lock.
            with self.repo.engine.begin() as c:
                initial = self._read(c, booking_id, capability, actor)
                replay = c.execute(
                    select(BookingAction.request_hash).where(
                        BookingAction.id == body.idempotency_key
                    )
                ).scalar_one_or_none()
                if replay:
                    if replay != fingerprint:
                        raise failure(409, "IDEMPOTENCY_CONFLICT", "Retry the original action.")
                    return {"booking": self.repo._view(c, initial)}
                request = (
                    c.execute(
                        select(BookingChange.__table__).where(
                            BookingChange.booking_id == booking_id,
                            BookingChange.status == "pending",
                        )
                    )
                    .mappings()
                    .first()
                )
                candidates = body.candidates
                timezone = body.timezone or initial["invitee_timezone"]
                if body.action == "approve":
                    if not actor or not request or body.request_id != request["id"]:
                        raise failure(
                            409,
                            "REQUEST_CHANGED",
                            "This change request is unavailable. Refresh bookings.",
                        )
                    if (
                        len(candidates) != 1
                        or candidates[0].isoformat() not in request["candidates"]
                    ):
                        # Normalize timezone offsets; candidates are stored in UTC.
                        if (
                            len(candidates) != 1
                            or candidates[0].astimezone(UTC).isoformat()
                            not in request["candidates"]
                        ):
                            raise failure(422, "INVALID_INPUT", "Choose a requested alternative.")
                    timezone = request["timezone"]
                external = None
                if body.action in ("reschedule", "approve"):
                    if not candidates:
                        raise failure(422, "INVALID_INPUT", "Choose a new time.")
                    lower = min(candidates).astimezone(UTC) - timedelta(days=1)
                    upper = max(candidates).astimezone(UTC) + timedelta(days=2)
                    external = self._external(c, initial, lower, upper)
            with self.repo.engine.begin() as c:
                row = self._read(c, booking_id, capability, actor)
                c.execute(
                    select(HostProfile.user_id)
                    .where(HostProfile.user_id == row["user_id"])
                    .with_for_update()
                ).one()
                lock_booking(c, booking_id)
                if not injected_now:
                    now = datetime.now(UTC)
                row = dict(
                    c.execute(select(Booking.__table__).where(Booking.id == booking_id))
                    .mappings()
                    .one()
                )
                replay = c.execute(
                    select(BookingAction.request_hash).where(
                        BookingAction.id == body.idempotency_key
                    )
                ).scalar_one_or_none()
                if replay:
                    if replay != fingerprint:
                        raise failure(409, "IDEMPOTENCY_CONFLICT", "Retry the original action.")
                    return {"booking": self.repo._view(c, row)}
                if row["revision"] != body.revision:
                    raise failure(
                        409, "BOOKING_CHANGED", "Booking changed. Refresh before reviewing again."
                    )
                pending = (
                    c.execute(
                        select(BookingChange.__table__).where(
                            BookingChange.booking_id == booking_id,
                            BookingChange.status == "pending",
                        )
                    )
                    .mappings()
                    .first()
                )
                if body.action in ("approve", "decline", "withdraw"):
                    if (
                        not pending
                        or pending["id"] != body.request_id
                        or pending["booking_revision"] != row["revision"]
                    ):
                        raise failure(
                            409,
                            "REQUEST_CHANGED",
                            "This request changed. Refresh before reviewing again.",
                        )
                    if body.action != "withdraw" and not actor:
                        raise failure(403, "HOST_REQUIRED", "The host must review this request.")
                    if actor and body.action == "approve" and pending["capability_ciphertext"]:
                        capability = TokenVault(get_settings().token_encryption_key).open(
                            row["user_id"], pending["capability_ciphertext"]
                        )
                if body.action in ("withdraw", "decline"):
                    c.execute(
                        update(BookingChange)
                        .where(BookingChange.id == pending["id"])
                        .values(
                            status="withdrawn" if body.action == "withdraw" else "declined",
                            capability_ciphertext=None,
                        )
                    )
                elif body.action == "cancel":
                    require_action(row, "cancellation", now, bool(actor))
                    row = dict(
                        c.execute(
                            update(Booking)
                            .where(Booking.id == booking_id)
                            .values(
                                status="cancelled", revision=row["revision"] + 1, updated_at=now
                            )
                            .returning(Booking.__table__)
                        )
                        .mappings()
                        .one()
                    )
                    self._queue(c, row, "booking_cancelled", capability)
                    c.execute(
                        update(BookingChange)
                        .where(
                            BookingChange.booking_id == booking_id,
                            BookingChange.status == "pending",
                        )
                        .values(status="superseded", capability_ciphertext=None)
                    )
                else:
                    require_action(row, "reschedule", now, bool(actor))
                    if pending and body.action != "approve":
                        raise failure(
                            409,
                            "REQUEST_PENDING",
                            "Withdraw the pending request before choosing new times.",
                        )
                    inputs = self._inputs(c, row)
                    connection = (
                        c.execute(
                            select(
                                GoogleConnection.user_id,
                                GoogleConnection.generation,
                                GoogleConnection.revision,
                                GoogleConnection.status,
                                GoogleConnection.destination_id,
                                GoogleConnection.create_meet,
                            ).where(GoogleConnection.user_id == row["user_id"])
                        )
                        .mappings()
                        .first()
                    )
                    if connection_stamp(connection) != external.stamp:
                        raise failure(
                            409,
                            "CALENDAR_CHANGED",
                            "Calendar settings changed. Choose a time again.",
                        )
                    approval = not actor and row["snapshot"]["reschedule_requires_approval"]
                    max_choices = 3 if approval and row["snapshot"]["allow_alternatives"] else 1
                    if len(candidates) > max_choices:
                        raise failure(
                            422, "INVALID_INPUT", "Too many alternative times for this booking."
                        )
                    for start in candidates:
                        start = start.astimezone(UTC)
                        if start == row["start_at"]:
                            raise failure(422, "INVALID_INPUT", "Choose a different meeting time.")
                        day = start.astimezone(ZoneInfo(timezone)).date()
                        schedule = inputs["payload"]
                        occupied = self.repo._occupancy(
                            c,
                            row["user_id"],
                            row["event_id"],
                            schedule["timezone"] if schedule else "UTC",
                            day,
                            day,
                            row["id"],
                        )
                        from dataclasses import replace

                        report = public_slots(
                            inputs,
                            start_date=day,
                            end_date=day,
                            timezone=timezone,
                            duration=row["duration"],
                            now=now,
                            occupancy=replace(occupied, busy=external.busy),
                        )
                        if not any(
                            datetime.fromisoformat(s["start"]) == start for s in report["slots"]
                        ):
                            raise failure(
                                409,
                                "SLOT_UNAVAILABLE",
                                "That time is no longer available. "
                                "Your original booking is unchanged.",
                            )
                    if approval:
                        settings = get_settings()
                        c.execute(
                            BookingChange.__table__.insert().values(
                                id=uuid4(),
                                booking_id=booking_id,
                                user_id=row["user_id"],
                                booking_revision=row["revision"],
                                candidates=[s.astimezone(UTC).isoformat() for s in candidates],
                                timezone=timezone,
                                capability_ciphertext=TokenVault(
                                    settings.token_encryption_key
                                ).seal(row["user_id"], capability)
                                if settings.email_configured
                                else None,
                            )
                        )
                    else:
                        start = candidates[0].astimezone(UTC)
                        end = start + timedelta(minutes=row["duration"])
                        row = dict(
                            c.execute(
                                update(Booking)
                                .where(Booking.id == booking_id)
                                .values(
                                    start_at=start,
                                    end_at=end,
                                    blocked_start=start
                                    - timedelta(minutes=row["snapshot"]["buffer_before"]),
                                    blocked_end=end
                                    + timedelta(minutes=row["snapshot"]["buffer_after"]),
                                    invitee_timezone=timezone,
                                    revision=row["revision"] + 1,
                                    updated_at=now,
                                )
                                .returning(Booking.__table__)
                            )
                            .mappings()
                            .one()
                        )
                        self._queue(c, row, "booking_rescheduled", capability)
                        if pending:
                            c.execute(
                                update(BookingChange)
                                .where(BookingChange.id == pending["id"])
                                .values(status="approved", capability_ciphertext=None)
                            )
                c.execute(
                    BookingAction.__table__.insert().values(
                        id=body.idempotency_key,
                        booking_id=booking_id,
                        user_id=row["user_id"],
                        request_hash=fingerprint,
                    )
                )
                return {"booking": self.repo._view(c, row)}
        except IntegrityError:
            raise failure(
                409,
                "ACTION_CONFLICT",
                "The action conflicted with another change. Refresh your booking.",
            ) from None
        except SQLAlchemyError:
            raise failure(
                503,
                "BOOKING_UNAVAILABLE",
                "The action could not be verified. Retry the same request.",
            ) from None
