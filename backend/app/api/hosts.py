from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import HostIdentity, current_host
from app.config import Settings, get_settings
from app.db.profiles import get_profile_repository

router = APIRouter(prefix="/api", tags=["host"])
RESERVED = {
    "app",
    "api",
    "assets",
    "auth",
    "login",
    "onboarding",
    "booking",
    "docs",
    "admin",
    "support",
    "www",
}


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str = Field(min_length=2, max_length=80)
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("username")
    @classmethod
    def not_reserved(cls, value: str):
        if value in RESERVED:
            raise ValueError("Choose another booking username.")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid IANA timezone.") from None
        return value


@router.get("/auth/config")
def auth_config(settings: Settings = Depends(get_settings)):
    return {
        "configured": settings.auth_configured,
        "supabase_url": settings.supabase_url if settings.auth_configured else None,
        "publishable_key": settings.publishable_key if settings.auth_configured else None,
    }


@router.get("/me")
def me(identity: HostIdentity = Depends(current_host), repository=Depends(get_profile_repository)):
    return {"user_id": str(identity.user_id), "profile": repository.get(identity.user_id)}


@router.get("/me/booking-contact")
def booking_contact(
    identity: HostIdentity = Depends(current_host), repository=Depends(get_profile_repository)
):
    profile = repository.get(identity.user_id)
    return {"name": profile["display_name"] if profile else "", "email": identity.email}


@router.put("/me/profile")
def save_profile(
    profile: ProfileInput,
    identity: HostIdentity = Depends(current_host),
    repository=Depends(get_profile_repository),
):
    return {
        "user_id": str(identity.user_id),
        "profile": repository.save(identity.user_id, profile.model_dump()),
    }
