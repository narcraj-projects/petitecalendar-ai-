"""Read-only guest history, scoped to a server-verified inbox address."""

from datetime import UTC, datetime

from sqlalchemy import and_, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.auth import failure
from app.config import get_settings
from app.db.bookings import Booking
from app.db.calendar import CalendarJob
from app.db.email import EmailJob
from app.db.profiles import get_engine


class GuestHistoryRepository:
    def __init__(self, url):
        self.engine = get_engine(url)

    def history(self, identity, kind, offset=0, limit=25, now=None):
        now = now or datetime.now(UTC)
        try:
            with self.engine.begin() as c:
                c.execute(text("SET LOCAL ROLE petitecalendar_guest"))
                c.execute(
                    text("SELECT set_config('app.guest_email',:email,true)"),
                    {"email": identity.email},
                )
                query = select(
                    Booking.id,
                    Booking.start_at,
                    Booking.end_at,
                    Booking.duration,
                    Booking.invitee_name,
                    Booking.invitee_timezone,
                    Booking.snapshot,
                    Booking.status,
                    Booking.revision,
                    CalendarJob.status.label("calendar_status"),
                    CalendarJob.meet_url,
                    EmailJob.status.label("email_status"),
                ).outerjoin(
                    CalendarJob,
                    and_(
                        CalendarJob.booking_id == Booking.id,
                        CalendarJob.revision == Booking.revision,
                    ),
                )
                query = query.outerjoin(
                    EmailJob,
                    and_(EmailJob.booking_id == Booking.id, EmailJob.revision == Booking.revision),
                )
                query = query.where(func.lower(Booking.invitee_email) == identity.email)
                if kind == "cancelled":
                    query = query.where(Booking.status == "cancelled")
                else:
                    query = query.where(Booking.status == "confirmed")
                    query = query.where(
                        Booking.end_at > now if kind == "upcoming" else Booking.end_at <= now
                    )
                order = Booking.start_at.asc() if kind == "upcoming" else Booking.start_at.desc()
                rows = (
                    c.execute(query.order_by(order, Booking.id).offset(offset).limit(limit + 1))
                    .mappings()
                    .all()
                )
                bookings = []
                for row in rows[:limit]:
                    snapshot = row["snapshot"]
                    bookings.append(
                        {
                            "id": str(row["id"]),
                            "title": snapshot["title"],
                            "host_name": snapshot["host_name"],
                            "host_timezone": snapshot["host_timezone"],
                            "start_at": row["start_at"],
                            "end_at": row["end_at"],
                            "duration": row["duration"],
                            "invitee_timezone": row["invitee_timezone"],
                            "status": row["status"],
                            "location": snapshot["location"],
                            "meet_url": row["meet_url"] if row["status"] == "confirmed" else None,
                            "calendar_status": row["calendar_status"] or "not_connected",
                            "email_status": row["email_status"] or "not_enabled",
                        }
                    )
                return {
                    "bookings": bookings,
                    "has_more": len(rows) > limit,
                    "next_offset": offset + limit if len(rows) > limit else None,
                }
        except SQLAlchemyError:
            raise failure(
                503, "HISTORY_UNAVAILABLE", "Your booking history could not be loaded. Try again."
            ) from None


def get_guest_history_repository():
    settings = get_settings()
    if not settings.database_url:
        raise failure(503, "HISTORY_UNAVAILABLE", "Booking history is not available yet.")
    return GuestHistoryRepository(settings.database_url)
