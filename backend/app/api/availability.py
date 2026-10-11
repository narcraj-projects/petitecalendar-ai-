from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.auth import HostIdentity, current_host
from app.db.availability import get_schedule_repository

router = APIRouter(prefix="/api/me/availability", tags=["availability"])


class Hours(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    end: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

    @model_validator(mode="after")
    def ordered(self):
        if time.fromisoformat(self.start) >= time.fromisoformat(self.end):
            raise ValueError("Hours must end after they start within the same day.")
        return self


class WeeklyHours(Hours):
    weekday: int = Field(ge=0, le=6, strict=True)


class Override(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    windows: list[Hours] = Field(max_length=3)


def validate_overlaps(windows):
    ordered = sorted(windows, key=lambda w: w.start)
    if any(a.end > b.start for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Working windows must not overlap.")


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, strict=True)
    timezone: str = Field(max_length=100)
    enabled: bool = Field(strict=True)
    weekly: list[WeeklyHours] = Field(max_length=21)
    overrides: list[Override] = Field(max_length=90)
    focus: list[WeeklyHours] = Field(max_length=21)
    increment_minutes: int = Field(ge=5, le=60, strict=True)
    host_daily_cap: int = Field(ge=1, le=50, strict=True)
    weekly_cap_minutes: int = Field(ge=0, le=10080, strict=True)
    prefer_cluster: bool = Field(strict=True)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose an IANA timezone.") from None
        return value

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.increment_minutes not in (5, 10, 15, 20, 30, 60):
            raise ValueError("Choose a supported slot increment.")
        for rows in (self.weekly, self.focus):
            for weekday in range(7):
                selected = [w for w in rows if w.weekday == weekday]
                if len(selected) > 3:
                    raise ValueError("Use at most three windows per day.")
                validate_overlaps(selected)
        if len({o.date for o in self.overrides}) != len(self.overrides):
            raise ValueError("Use one override per date.")
        for override in self.overrides:
            validate_overlaps(override.windows)
        return self


@router.get("")
def load_schedule(
    identity: HostIdentity = Depends(current_host), repo=Depends(get_schedule_repository)
):
    return {"schedule": repo.load(identity.user_id)}


@router.put("")
def save_schedule(
    body: ScheduleInput,
    identity: HostIdentity = Depends(current_host),
    repo=Depends(get_schedule_repository),
):
    return {
        "schedule": repo.save(
            identity.user_id, body.model_dump(mode="json", exclude={"revision"}), body.revision
        )
    }
