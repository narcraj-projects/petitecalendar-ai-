"""Assistant scope comes from verified authentication or a private booking capability."""

import hashlib
from collections import defaultdict, deque
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.bookings import BookingInput, private_capability
from app.auth import HostIdentity, current_host, failure
from app.services.assistant import get_assistant

router = APIRouter(tags=["assistant"])
_lock = Lock()
_calls = defaultdict(deque)
_global = deque()
_capacity = BoundedSemaphore(4)


class AssistantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[str] = Field(min_length=1, max_length=6)
    timezone: str = Field(max_length=100)
    duration: int = Field(default=30, ge=5, le=240, strict=True)
    target: Literal["event", "schedule"] = "event"
    event_id: UUID | None = None

    @field_validator("messages")
    @classmethod
    def bounded_messages(cls, values):
        if any(not 1 <= len(v.strip()) <= 1000 for v in values):
            raise ValueError("Use messages of at most 1000 characters.")
        return [v.strip() for v in values]

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        return BookingInput.zone(value)


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal: str = Field(min_length=64, max_length=24000)


def ask(service, request, body, **scope):
    # Bounded cost for this single-process preview; deployment needs shared limits.
    key = hashlib.sha256(
        str(scope.get("actor") or (request.client.host if request.client else "unknown")).encode()
    ).hexdigest()
    now = monotonic()
    with _lock:
        for k in list(_calls):
            while _calls[k] and _calls[k][0] <= now - 3600:
                _calls[k].popleft()
            if not _calls[k]:
                del _calls[k]
        while _global and _global[0] <= now - 3600:
            _global.popleft()
        if len(_global) >= 200 or len(_calls[key]) >= 20:
            raise failure(
                429,
                "AI_RATE_LIMIT",
                "The assistant limit was reached. Use manual controls and try later.",
            )
        _calls[key].append(now)
        _global.append(now)
    if not _capacity.acquire(blocking=False):
        raise failure(
            429, "AI_BUSY", "The assistant is busy. Use the calendar or try again shortly."
        )
    try:
        return service.propose(body, **scope)
    finally:
        _capacity.release()


@router.post("/api/me/assistant")
def host_assistant(
    body: AssistantInput,
    request: Request,
    identity: HostIdentity = Depends(current_host),
    service=Depends(get_assistant),
):
    if body.target == "event" and not body.event_id:
        raise failure(422, "EVENT_REQUIRED", "Select a saved event first.")
    return ask(service, request, body, actor=identity.user_id)


@router.post("/api/me/assistant/confirm")
def host_confirm(
    body: Confirmation,
    identity: HostIdentity = Depends(current_host),
    service=Depends(get_assistant),
):
    return service.confirm(body.proposal, actor=identity.user_id)


@router.post("/api/public/events/{username}/{slug}/assistant")
def public_assistant(
    username: str, slug: str, body: AssistantInput, request: Request, service=Depends(get_assistant)
):
    return ask(service, request, body, username=username, slug=slug)


@router.post("/api/bookings/{booking_id}/assistant")
def booking_assistant(
    booking_id: UUID,
    body: AssistantInput,
    request: Request,
    capability: str = Header(default="", alias="X-Booking-Capability"),
    service=Depends(get_assistant),
):
    return ask(
        service, request, body, booking_id=booking_id, capability=private_capability(capability)
    )


@router.post("/api/bookings/{booking_id}/assistant/confirm")
def booking_confirm(
    booking_id: UUID,
    body: Confirmation,
    capability: str = Header(default="", alias="X-Booking-Capability"),
    service=Depends(get_assistant),
):
    return service.confirm(
        body.proposal, booking_id=booking_id, capability=private_capability(capability)
    )


@router.post("/api/me/bookings/{booking_id}/assistant")
def host_booking_assistant(
    booking_id: UUID,
    body: AssistantInput,
    request: Request,
    identity: HostIdentity = Depends(current_host),
    service=Depends(get_assistant),
):
    return ask(service, request, body, booking_id=booking_id, actor=identity.user_id)


@router.post("/api/me/bookings/{booking_id}/assistant/confirm")
def host_booking_confirm(
    booking_id: UUID,
    body: Confirmation,
    identity: HostIdentity = Depends(current_host),
    service=Depends(get_assistant),
):
    return service.confirm(body.proposal, booking_id=booking_id, actor=identity.user_id)
