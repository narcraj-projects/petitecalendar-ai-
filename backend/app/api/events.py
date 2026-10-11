from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth import HostIdentity, current_host
from app.db.events import get_event_repository

router = APIRouter(prefix="/api/me/event-types", tags=["event-types"])


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    title: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=2000)
    slug: str = Field(min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
    durations: list[int] = Field(min_length=1, max_length=6)
    default_duration: int
    location: str = Field(default="Online conversation", min_length=1, max_length=160)
    notice_minutes: int = Field(default=720, ge=0, le=10080)
    horizon_days: int = Field(default=60, ge=1, le=365)
    buffer_before: int = Field(default=10, ge=0, le=240)
    buffer_after: int = Field(default=15, ge=0, le=240)
    max_per_day: int = Field(default=3, ge=1, le=50)
    cancellation_hours: int = Field(default=12, ge=0, le=720)
    reschedule_hours: int = Field(default=12, ge=0, le=720)
    reschedule_requires_approval: bool = False
    allow_alternatives: bool = True

    @model_validator(mode="after")
    def duration_rules(self):
        if len(set(self.durations)) != len(self.durations):
            raise ValueError("Duration options must be unique.")
        if any(value < 5 or value > 240 or value % 5 for value in self.durations):
            raise ValueError("Durations must be 5–240 minutes in five-minute increments.")
        if self.default_duration not in self.durations:
            raise ValueError("Choose a default from the duration options.")
        self.durations.sort()
        return self


class EventUpdate(EventInput):
    published: bool
    revision: int = Field(ge=1)


@router.get("")
def list_events(identity: HostIdentity = Depends(current_host), repo=Depends(get_event_repository)):
    return {"events": repo.list_events(identity.user_id)}


@router.post("", status_code=201)
def create_event(
    body: EventInput,
    identity: HostIdentity = Depends(current_host),
    repo=Depends(get_event_repository),
):
    return {"event": repo.save_event(identity.user_id, body.model_dump())}


@router.put("/{event_id}")
def update_event(
    event_id: UUID,
    body: EventUpdate,
    identity: HostIdentity = Depends(current_host),
    repo=Depends(get_event_repository),
):
    values = body.model_dump(exclude={"revision"})
    return {"event": repo.save_event(identity.user_id, values, event_id, body.revision)}
