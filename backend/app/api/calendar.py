import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.exceptions import HTTPException

from app.auth import HostIdentity, current_host
from app.integrations.google import CalendarError
from app.services.calendar import get_calendar_service

router = APIRouter(tags=["google-calendar"])
COOKIE = "pc_google_calendar"
CALLBACK = "/api/integrations/google/callback"
FAILURES = {
    "invalid_state": "consent_expired",
    "consent_expired": "consent_expired",
    "consent_incomplete": "consent_incomplete",
    "client_configuration": "client_configuration",
    "authorization_failed": "authorization_failed",
    "calendar_access_failed": "calendar_access_failed",
    "calendar_unavailable": "calendar_access_failed",
    "reconnect_required": "authorization_failed",
}
logger = logging.getLogger(__name__)


class CalendarPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=1)
    blocking_ids: list[str] = Field(max_length=20)
    destination_id: str = Field(min_length=1, max_length=1024)
    create_meet: bool = True

    @model_validator(mode="after")
    def valid_ids(self):
        if len(set(self.blocking_ids)) != len(self.blocking_ids) or any(
            not i or len(i) > 1024 for i in self.blocking_ids
        ):
            raise ValueError("Choose unique calendar identifiers.")
        return self


class ConnectionRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=1)


@router.get("/api/me/integrations/google")
def status(identity: HostIdentity = Depends(current_host), service=Depends(get_calendar_service)):
    return service.status(identity.user_id)


@router.post("/api/me/integrations/google/connect")
def connect(
    response: Response,
    identity: HostIdentity = Depends(current_host),
    service=Depends(get_calendar_service),
):
    url, binding = service.start(identity.user_id)
    response.set_cookie(
        COOKIE,
        binding,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=service.settings.app_base_url.startswith("https://"),
        path=CALLBACK,
    )
    return {"authorization_url": url}


@router.get(CALLBACK)
def callback(
    request: Request,
    state: str = "",
    code: str = "",
    error: str = "",
    service=Depends(get_calendar_service),
):
    result = "failed"
    binding = request.cookies.get(COOKIE, "")
    if (
        re.fullmatch(r"[A-Za-z0-9_-]{40,64}", state)
        and re.fullmatch(r"[A-Za-z0-9_-]{40,64}", binding)
        and len(code) <= 4096
    ):
        try:
            result = service.callback(state, binding, "" if error else code)
        except CalendarError as error:
            result = FAILURES.get(error.code, "failed")
        except HTTPException:
            result = "storage_unavailable"
    if result not in ("connected", "denied"):
        # Only fixed categories: no tokens, codes, identities or provider payloads.
        logger.warning("Calendar consent failed: %s", result)
    response = RedirectResponse("/app/integrations?calendar=" + result, status_code=303)
    response.delete_cookie(COOKIE, path=CALLBACK)
    return response


@router.put("/api/me/integrations/google")
def preferences(
    body: CalendarPreferences,
    identity: HostIdentity = Depends(current_host),
    service=Depends(get_calendar_service),
):
    return service.save(identity.user_id, body)


@router.post("/api/me/integrations/google/disconnect")
def disconnect(
    body: ConnectionRevision,
    identity: HostIdentity = Depends(current_host),
    service=Depends(get_calendar_service),
):
    return service.disconnect(identity.user_id, body.revision)


@router.post("/api/me/bookings/{booking_id}/calendar/retry")
def retry(
    booking_id: UUID,
    identity: HostIdentity = Depends(current_host),
    service=Depends(get_calendar_service),
):
    service.repository.retry(identity.user_id, booking_id)
    return {"status": "queued"}
