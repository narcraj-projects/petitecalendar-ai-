"""Typed scheduling tools, scoped proposals and explicit confirmations."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.api.availability import ScheduleInput, WeeklyHours
from app.api.bookings import BookingInput, LifecycleInput
from app.api.events import EventUpdate
from app.auth import failure
from app.config import get_settings
from app.db.availability import get_schedule_repository
from app.db.bookings import get_booking_repository
from app.db.events import get_event_repository
from app.integrations.openai import OpenAIScheduler
from app.services.calendar import get_calendar_service
from app.services.lifecycle import LifecycleService, require_action


class Tool(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Clarify(Tool):
    question: str = Field(min_length=3, max_length=240)


class FindTimes(Tool):
    start_date: str
    end_date: str
    timezone: str
    duration: int = Field(ge=5, le=240)
    window_start: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    window_end: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

    @model_validator(mode="after")
    def bounds(self):
        a, b = date.fromisoformat(self.start_date), date.fromisoformat(self.end_date)
        if not 3 <= a.year <= b.year <= 9997 or not 0 <= (b - a).days <= 13:
            raise ValueError("Use at most 14 days.")
        BookingInput.zone(self.timezone)
        if self.window_end <= self.window_start:
            raise ValueError("End must follow start.")
        return self


class EventPatch(Tool):
    durations: list[int] | None = Field(max_length=6)
    default_duration: int | None
    notice_minutes: int | None
    horizon_days: int | None
    buffer_before: int | None
    buffer_after: int | None
    max_per_day: int | None
    cancellation_hours: int | None
    reschedule_hours: int | None
    reschedule_requires_approval: bool | None
    allow_alternatives: bool | None


class SchedulePatch(Tool):
    timezone: str | None
    weekly: list[WeeklyHours] | None = Field(max_length=21)
    focus: list[WeeklyHours] | None = Field(max_length=21)
    increment_minutes: int | None
    host_daily_cap: int | None
    weekly_cap_minutes: int | None
    prefer_cluster: bool | None


class Empty(Tool):
    pass


TOOLS = {
    "clarify": (Clarify, "Ask one scheduling clarification; do not take action."),
    "find_times": (
        FindTimes,
        "Search live available times over at most 14 days; window is in the requested timezone.",
    ),
    "draft_event_settings": (
        EventPatch,
        "Propose a patch to the selected existing event; null leaves a field unchanged.",
    ),
    "draft_schedule": (
        SchedulePatch,
        "Propose saved hours, focus or caps; null leaves unchanged. "
        "Weekly windows replace all weekly hours.",
    ),
    "cancel_booking": (
        Empty,
        "Propose cancelling only this booking; explicit confirmation is still required.",
    ),
    "explain_policy": (Empty, "Explain this booking's saved cancellation and reschedule rules."),
}


class Proposals:
    def __init__(self, key):
        try:
            self.fernet = Fernet(key.encode())
        except (ValueError, TypeError):
            raise failure(
                503, "AI_UNAVAILABLE", "Assistant confirmation is not configured."
            ) from None

    def seal(self, scope, action, arguments, now=None):
        expiry = (now or datetime.now(UTC)) + timedelta(minutes=15)
        value = {
            "scope": scope,
            "action": action,
            "arguments": arguments,
            "expires": expiry.isoformat(),
        }
        return self.fernet.encrypt(json.dumps(value).encode()).decode(), expiry.isoformat()

    def open(self, scope, token, now=None):
        try:
            value = json.loads(self.fernet.decrypt(token.encode()))
            if value["scope"] != scope or datetime.fromisoformat(value["expires"]) <= (
                now or datetime.now(UTC)
            ):
                raise ValueError()
            return value
        except (InvalidToken, ValueError, KeyError, TypeError, AttributeError):
            raise failure(
                409,
                "STALE_PROPOSAL",
                "This proposal expired or is invalid. Ask for a fresh proposal.",
            ) from None


def scope_for(actor=None, booking_id=None, capability=""):
    return (
        "host:" + str(actor)
        if actor
        else "booking:" + str(booking_id) + ":" + hashlib.sha256(capability.encode()).hexdigest()
    )


class Assistant:
    def __init__(
        self,
        settings=None,
        provider=None,
        events=None,
        schedules=None,
        bookings=None,
        calendar=None,
    ):
        self.settings = settings or get_settings()
        self.provider = provider or OpenAIScheduler(self.settings)
        self.events, self.schedules, self.bookings, self.calendar = (
            events,
            schedules,
            bookings,
            calendar,
        )

    def event_repo(self):
        return self.events or get_event_repository()

    def schedule_repo(self):
        return self.schedules or get_schedule_repository()

    def lifecycle(self):
        return LifecycleService(self.bookings or get_booking_repository(), self.calendar_adapter())

    def calendar_adapter(self):
        if self.calendar is None:
            raise failure(503, "CALENDAR_UNAVAILABLE", "Availability checks are unavailable.")
        return self.calendar

    def owned_event(self, actor, event_id):
        found = next(
            (e for e in self.event_repo().list_events(actor) if e["id"] == str(event_id)), None
        )
        if not found:
            raise failure(404, "EVENT_NOT_FOUND", "Select one of your own saved event types.")
        return found

    def booking(self, booking_id, capability, actor):
        service = self.lifecycle()
        with service.repo.engine.begin() as c:
            return service._read(c, booking_id, capability, actor)

    def propose(self, body, actor=None, username=None, slug=None, booking_id=None, capability=""):
        now = datetime.now(UTC)
        context = {
            "today": now.astimezone(ZoneInfo(body.timezone)).date().isoformat(),
            "timezone": body.timezone,
            "duration": body.duration,
            "default_search": {
                "start_date": now.astimezone(ZoneInfo(body.timezone)).date().isoformat(),
                "end_date": (
                    now.astimezone(ZoneInfo(body.timezone)).date() + timedelta(days=6)
                ).isoformat(),
                "window_start": "00:00",
                "window_end": "23:59",
            },
        }
        names = ["clarify"]
        event = schedule = booking = None
        if booking_id:
            booking = self.booking(booking_id, capability, actor)
            names += ["find_times", "cancel_booking", "explain_policy"]
            context.update(
                duration=booking["duration"],
                booking_start=booking["start_at"].isoformat(),
                saved_policy={
                    k: booking["snapshot"][k]
                    for k in (
                        "cancellation_hours",
                        "reschedule_hours",
                        "reschedule_requires_approval",
                        "allow_alternatives",
                    )
                },
            )
        elif actor:
            if body.target == "schedule":
                schedule = self.schedule_repo().load(actor)
                if not schedule:
                    raise failure(
                        409,
                        "SCHEDULE_REQUIRED",
                        "Save your initial availability before using the assistant.",
                    )
                context["settings"] = {k: schedule[k] for k in SchedulePatch.model_fields}
                names += ["draft_schedule"]
            else:
                event = self.owned_event(actor, body.event_id)
                context["settings"] = {k: event[k] for k in EventPatch.model_fields}
                names += ["draft_event_settings"]
        else:
            event = self.event_repo().public_event(username, slug)
            context.update(
                durations=event["durations"], duration=body.duration or event["default_duration"]
            )
            names += ["find_times"]
        name, args = self.provider.interpret(body.messages, context, {n: TOOLS[n] for n in names})
        # Defense in depth for provider doubles and future adapters.
        if name not in names:
            raise failure(503, "AI_UNAVAILABLE", "The assistant requested an unavailable action.")
        if name == "clarify":
            return {"kind": "clarification", "message": args.question}
        if name == "find_times":
            a, b = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
            if booking:
                if args.duration != booking["duration"]:
                    raise failure(
                        422, "SAVED_DURATION", "Rescheduling preserves your booked duration."
                    )
                result = self.lifecycle().slots(
                    booking_id, capability, a, b, args.timezone, actor=actor
                )
            else:
                from app.main import slots

                result = slots(
                    username,
                    slug,
                    a,
                    b,
                    args.duration,
                    args.timezone,
                    self.calendar_adapter(),
                )
            zone = ZoneInfo(args.timezone)
            selected = [
                s
                for s in result["slots"]
                if args.window_start
                <= datetime.fromisoformat(s["start"]).astimezone(zone).strftime("%H:%M")
                < args.window_end
            ]
            return {
                "kind": "slots",
                "slots": selected[:8],
                "timezone": args.timezone,
                "duration": args.duration,
                "host_timezone": result.get("host_timezone")
                or (booking["snapshot"]["host_timezone"] if booking else event["host"]["timezone"]),
                "message": "Suggested times are available now, but are not reserved."
                if selected
                else "No times match this request. Try a wider window or use the calendar.",
                "expires_at": (now + timedelta(minutes=15)).isoformat(),
            }
        if name == "explain_policy":
            snap = booking["snapshot"]
            return {
                "kind": "policy",
                "message": f"Cancel until {snap['cancellation_hours']} hours before the meeting. "
                f"Reschedule until {snap['reschedule_hours']} hours before. "
                + (
                    "The host must approve; your original time stays reserved until approval."
                    if snap["reschedule_requires_approval"]
                    else "A confirmed reschedule replaces your original time."
                ),
            }
        scope = scope_for(actor, booking_id, capability)
        if name == "cancel_booking":
            require_action(booking, "cancellation", datetime.now(UTC), bool(actor))
            arguments = {
                "booking_id": str(booking_id),
                "body": {
                    "action": "cancel",
                    "revision": booking["revision"],
                    "idempotency_key": str(uuid4()),
                },
            }
            action = "cancel"
            diff = [{"field": "status", "before": "confirmed", "after": "cancelled"}]
        else:
            patch = args.model_dump(exclude_none=True)
            original = event if event else schedule
            try:
                if event:
                    validated = EventUpdate.model_validate(
                        {k: v for k, v in (event | patch).items() if k != "id"}
                    )
                    values = validated.model_dump(exclude={"revision"})
                    action = "event"
                    arguments = {
                        "event_id": str(body.event_id),
                        "revision": event["revision"],
                        "values": values,
                    }
                else:
                    validated = ScheduleInput.model_validate(schedule | patch)
                    values = validated.model_dump(mode="json", exclude={"revision"})
                    action = "schedule"
                    arguments = {"revision": schedule["revision"], "values": values}
            except ValidationError:
                raise failure(
                    422,
                    "INVALID_DRAFT",
                    "The proposed settings are invalid. Check durations, hours and limits.",
                ) from None
            diff = [
                {"field": k, "before": original[k], "after": values[k]}
                for k in patch
                if original[k] != values[k]
            ]
            if not diff:
                return {
                    "kind": "clarification",
                    "message": "Those settings already match. What would you like to change?",
                }
        token, expiry = Proposals(self.settings.token_encryption_key).seal(scope, action, arguments)
        result = {
            "kind": "proposal",
            "action": action,
            "diff": diff,
            "proposal": token,
            "expires_at": expiry,
            "message": "Review these changes before applying them. "
            "Availability will be recalculated after saving.",
        }
        if booking:
            result["booking_review"] = {
                "start": booking["start_at"].isoformat(),
                "timezone": booking["invitee_timezone"],
                "host_timezone": booking["snapshot"]["host_timezone"],
                "duration": booking["duration"],
            }
            result["message"] = (
                "Confirm cancellation to release this time and queue calendar removal "
                "and the cancellation email."
            )
        return result

    def confirm(self, token, actor=None, booking_id=None, capability=""):
        value = Proposals(self.settings.token_encryption_key).open(
            scope_for(actor, booking_id, capability), token
        )
        args, action = value["arguments"], value["action"]
        if action == "cancel" and str(booking_id) == args["booking_id"]:
            return self.lifecycle().act(
                booking_id, LifecycleInput.model_validate(args["body"]), capability, actor=actor
            )
        if not actor or booking_id:
            raise failure(409, "INVALID_PROPOSAL", "This proposal cannot be applied here.")
        if action == "event":
            old = self.owned_event(actor, UUID(args["event_id"]))
            if old["revision"] == args["revision"] + 1 and all(
                old[k] == v for k, v in args["values"].items()
            ):
                return {"event": old}  # Exact retry after a lost response, no second write.
            return {
                "event": self.event_repo().save_event(
                    actor, args["values"], UUID(args["event_id"]), args["revision"]
                )
            }
        if action == "schedule":
            old = self.schedule_repo().load(actor)
            if (
                old
                and old["revision"] == args["revision"] + 1
                and all(old[k] == v for k, v in args["values"].items())
            ):
                return {"schedule": old}
            return {"schedule": self.schedule_repo().save(actor, args["values"], args["revision"])}
        raise failure(409, "INVALID_PROPOSAL", "This proposal cannot be applied here.")


def get_assistant(calendar=Depends(get_calendar_service)):
    return Assistant(calendar=calendar)
