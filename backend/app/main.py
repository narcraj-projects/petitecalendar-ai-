from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api.assistant import router as assistant_router
from app.api.availability import router as availability_router
from app.api.bookings import router as bookings_router
from app.api.calendar import router as calendar_router
from app.api.events import router as events_router
from app.api.guest_history import router as guest_history_router
from app.api.hosts import router as hosts_router
from app.api.invitations import router as invitations_router
from app.db.availability import get_schedule_repository
from app.db.bookings import get_booking_repository
from app.db.events import get_event_repository
from app.demo import RULES, get_demo_occupancy
from app.domain.availability import get_available_slots
from app.services.availability import public_slots
from app.services.calendar import get_calendar_service
from app.staging import StagingAccessMiddleware

app = FastAPI(title="PetiteCalendar-ai", version="0.1.0")
app.add_middleware(StagingAccessMiddleware)
app.include_router(hosts_router)
app.include_router(events_router)
app.include_router(availability_router)
app.include_router(bookings_router)
app.include_router(calendar_router)
app.include_router(assistant_router)
app.include_router(invitations_router)
app.include_router(guest_history_router)


@app.middleware("http")
async def private_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith(
        (
            "/api/me",
            "/api/guest",
            "/api/auth",
            "/auth/",
            "/api/public/events",
            "/api/bookings",
            "/booking/",
            "/api/integrations",
        )
    ):
        response.headers["Cache-Control"] = "no-store"
    return response


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    message = "Check the date range, duration and timezone."
    if request.url.path == "/api/me/profile":
        message = "Check your display name, booking username and timezone."
    if request.url.path.startswith("/api/me/event-types"):
        message = "Check the event title, slug, durations and booking policies."
    if request.url.path == "/api/me/availability":
        message = (
            "Check timezone, ordered hours, overlapping windows, date overrides and meeting limits."
        )
    if request.url.path.endswith("/bookings") or request.url.path.startswith("/api/bookings"):
        message = "Check the selected time, timezone, name and email."
    if request.url.path.endswith("/actions") and "/bookings/" in request.url.path:
        message = "Check the action, selected times, timezone and saved booking revision."
    if "/integrations/google" in request.url.path:
        message = "Check your calendar selection and saved revision."
    if "/assistant" in request.url.path:
        message = "Check your request, timezone and selected event."
    if "/invitations" in request.url.path:
        message = "Enter 1-10 unique email addresses and review the published event."
    return error_response(422, "INVALID_INPUT", message)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return error_response(exc.status_code, exc.detail["code"], exc.detail["message"])
    return error_response(exc.status_code, "REQUEST_FAILED", str(exc.detail))


def check_event(username: str, slug: str) -> None:
    if (username, slug) != ("ananya", "career-strategy"):
        raise HTTPException(404, "This event is not available.")


def check_zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Choose a valid IANA timezone.") from None


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "demo", "functionality": "public-availability"}


def public_repository(username: str, slug: str):
    if (username, slug) == ("ananya", "career-strategy"):
        return None
    return get_event_repository()


@app.get("/api/public/events/{username}/{slug}")
def event(username: str, slug: str, repository=Depends(public_repository)):
    if (username, slug) != ("ananya", "career-strategy"):
        return repository.public_event(username, slug)
    return {
        "username": username,
        "slug": slug,
        "title": "Career strategy call",
        "description": (
            "Bring your CV and the roles you're weighing. We'll leave with a 90-day plan."
        ),
        "host": {
            "name": "Ananya Rao",
            "role": "Product & career coach",
            "timezone": RULES.timezone,
        },
        "durations": [30, 45, 60],
        "default_duration": 45,
        "mode": "demo",
        "now": datetime.now(UTC).isoformat(),
        "notice_hours": RULES.notice_minutes // 60,
        "horizon_days": RULES.horizon_days,
    }


@app.get("/api/public/events/{username}/{slug}/slots")
def slots(
    username: str,
    slug: str,
    start_date: date,
    end_date: date,
    duration: int = Query(45, ge=1, le=240),
    timezone: str = "Asia/Kolkata",
    calendar_service=Depends(get_calendar_service),
):
    zone = check_zone(timezone)
    if end_date < start_date or (end_date - start_date).days > 41:
        raise HTTPException(422, "Request between 1 and 42 days.")
    if start_date.year < 2 or end_date.year > 9998:
        raise HTTPException(422, "Dates are outside the supported range.")
    if (username, slug) != ("ananya", "career-strategy"):
        row = get_schedule_repository().public_schedule(username, slug)
        if duration not in row["durations"]:
            raise HTTPException(422, "Choose one of this event’s duration options.")
        occupied = (
            get_booking_repository().occupancy(row, start_date, end_date)
            if row["payload"]
            else None
        )
        external = (
            calendar_service.busy(
                row["user_id"],
                datetime.combine(start_date - timedelta(days=1), time.min, UTC),
                datetime.combine(end_date + timedelta(days=2), time.min, UTC),
            )
            if row["payload"] and row["payload"]["enabled"]
            else None
        )
        result = public_slots(
            row,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
            duration=duration,
            now=datetime.now(UTC),
            occupancy=replace(occupied, busy=external.busy) if external else occupied,
        )
        result["calendar_status"] = (
            "connected"
            if external and external.stamp and external.stamp[2] == "connected"
            else "not_connected"
        )
        return result
    if duration not in (30, 45, 60):
        raise HTTPException(422, "Choose 30, 45 or 60 minutes.")
    try:
        result = get_available_slots(
            RULES,
            get_demo_occupancy(start_date, end_date),
            start_date=start_date,
            end_date=end_date,
            invitee_timezone=timezone,
            duration_minutes=duration,
            now=datetime.now(UTC),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {
        "mode": "demo",
        "timezone": timezone,
        "host_timezone": RULES.timezone,
        "duration": duration,
        "slots": [
            {
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
                "date": slot.start.astimezone(zone).date().isoformat(),
            }
            for slot in result
        ],
    }


DIST = Path(__file__).resolve().parents[2] / "frontend/dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    @app.get("/ananya/career-strategy")
    @app.get("/login")
    @app.get("/auth/callback")
    @app.get("/onboarding")
    @app.get("/app")
    @app.get("/app/profile")
    @app.get("/app/event-types")
    @app.get("/app/event-types/{event_id}")
    @app.get("/app/availability")
    @app.get("/app/bookings")
    @app.get("/app/integrations")
    @app.get("/guest/bookings")
    @app.get("/booking/{booking_id}")
    def frontend():
        return FileResponse(DIST / "index.html")

    @app.get("/{username}/{slug}")
    def published_frontend(username: str, slug: str):
        if username in {"api", "assets", "auth", "app"}:
            raise HTTPException(404, "Page not found.")
        return FileResponse(DIST / "index.html")
