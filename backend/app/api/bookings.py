import re
from datetime import date, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.auth import HostIdentity, current_host, failure
from app.db.bookings import get_booking_repository
from app.services.calendar import get_calendar_service
from app.services.icalendar import calendar_file

router = APIRouter(tags=["bookings"])


class BookingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    start: AwareDatetime
    duration: int = Field(ge=5, le=240, strict=True)
    timezone: str = Field(max_length=100)
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    idempotency_key: UUID
    capability: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose an IANA timezone.") from None
        return value

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("start")
    @classmethod
    def supported_start(cls, value):
        if not 3 <= value.year <= 9997:
            raise ValueError("Unsupported date.")
        return value


class LifecycleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["cancel", "reschedule", "approve", "decline", "withdraw"]
    revision: int = Field(ge=1, strict=True)
    idempotency_key: UUID
    candidates: list[AwareDatetime] = Field(default_factory=list, max_length=3)
    timezone: str | None = Field(default=None, max_length=100)
    request_id: UUID | None = None

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        return BookingInput.zone(value) if value is not None else value

    @field_validator("candidates")
    @classmethod
    def bounded_dates(cls, values):
        if any(not 3 <= v.year <= 9997 for v in values) or len(set(values)) != len(values):
            raise ValueError("Choose distinct supported dates.")
        if values and max(values) - min(values) > timedelta(days=62):
            raise ValueError("Choose alternatives within 62 days.")
        return values


def private_capability(value):
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise failure(404, "BOOKING_NOT_FOUND", "This private booking link is invalid.")
    return value


def lifecycle(repo, calendar_service):
    from app.services.lifecycle import LifecycleService

    return LifecycleService(repo, calendar_service)


@router.post("/api/bookings/{booking_id}/actions")
def booking_action(
    booking_id: UUID,
    body: LifecycleInput,
    capability: str = Header(default="", alias="X-Booking-Capability"),
    repo=Depends(get_booking_repository),
    calendar_service=Depends(get_calendar_service),
):
    return lifecycle(repo, calendar_service).act(booking_id, body, private_capability(capability))


@router.post("/api/me/bookings/{booking_id}/actions")
def host_booking_action(
    booking_id: UUID,
    body: LifecycleInput,
    identity: HostIdentity = Depends(current_host),
    repo=Depends(get_booking_repository),
    calendar_service=Depends(get_calendar_service),
):
    return lifecycle(repo, calendar_service).act(booking_id, body, actor=identity.user_id)


@router.get("/api/bookings/{booking_id}/slots")
def reschedule_slots(
    booking_id: UUID,
    start_date: date,
    end_date: date,
    timezone: str,
    capability: str = Header(default="", alias="X-Booking-Capability"),
    repo=Depends(get_booking_repository),
    calendar_service=Depends(get_calendar_service),
):
    if (
        not timedelta(0) <= end_date - start_date <= timedelta(days=62)
        or start_date.year < 3
        or end_date.year > 9997
    ):
        raise failure(422, "INVALID_INPUT", "Choose up to 62 days.")
    try:
        BookingInput.zone(timezone)
    except ValueError:
        raise failure(422, "INVALID_INPUT", "Choose an IANA timezone.") from None
    return lifecycle(repo, calendar_service).slots(
        booking_id, private_capability(capability), start_date, end_date, timezone
    )


@router.get("/api/me/bookings/{booking_id}/slots")
def host_reschedule_slots(
    booking_id: UUID,
    start_date: date,
    end_date: date,
    timezone: str,
    identity: HostIdentity = Depends(current_host),
    repo=Depends(get_booking_repository),
    calendar_service=Depends(get_calendar_service),
):
    if (
        not timedelta(0) <= end_date - start_date <= timedelta(days=62)
        or start_date.year < 3
        or end_date.year > 9997
    ):
        raise failure(422, "INVALID_INPUT", "Choose up to 62 days.")
    try:
        BookingInput.zone(timezone)
    except ValueError:
        raise failure(422, "INVALID_INPUT", "Choose an IANA timezone.") from None
    return lifecycle(repo, calendar_service).slots(
        booking_id, "", start_date, end_date, timezone, actor=identity.user_id
    )


@router.post("/api/public/events/{username}/{slug}/bookings", status_code=201)
def reserve(
    username: str,
    slug: str,
    body: BookingInput,
    repo=Depends(get_booking_repository),
    calendar_service=Depends(get_calendar_service),
):
    if (username, slug) == ("ananya", "career-strategy"):
        raise failure(409, "DEMO_ONLY", "The demo does not create bookings.")
    return {"booking": repo.reserve(username, slug, body, calendar_service=calendar_service)}


@router.get("/api/bookings/{booking_id}")
def manage(
    booking_id: UUID,
    capability: str = Header(default="", alias="X-Booking-Capability"),
    repo=Depends(get_booking_repository),
):
    if not re.fullmatch(r"[a-f0-9]{64}", capability):
        raise failure(404, "BOOKING_NOT_FOUND", "This private booking link is invalid.")
    return {"booking": repo.manage(booking_id, capability)}


@router.get("/api/me/bookings")
def dashboard(
    start: date,
    end: date,
    identity: HostIdentity = Depends(current_host),
    repo=Depends(get_booking_repository),
):
    if not timedelta(0) < end - start <= timedelta(days=93) or start.year < 3 or end.year > 9997:
        raise failure(422, "INVALID_INPUT", "Choose a date range of up to 93 days.")
    return repo.dashboard(identity.user_id, start, end)


@router.get("/api/bookings/{booking_id}/calendar.ics")
def download_calendar(
    booking_id: UUID,
    capability: str = Header(default="", alias="X-Booking-Capability"),
    repo=Depends(get_booking_repository),
):
    if not re.fullmatch(r"[a-f0-9]{64}", capability):
        raise failure(404, "BOOKING_NOT_FOUND", "This private booking link is invalid.")
    booking = repo.manage(booking_id, capability)
    return Response(
        calendar_file(booking),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="booking-{booking_id}.ics"',
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
        },
    )
