from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.bookings import BookingInput
from app.auth import HostIdentity, current_host
from app.db.invitations import get_invitation_repository

router = APIRouter(prefix="/api/me/event-types", tags=["event-sharing"])


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    recipients: list[str] = Field(min_length=1, max_length=10)
    idempotency_key: UUID

    @field_validator("recipients")
    @classmethod
    def contacts(cls, values):
        normalized = []
        for value in values:
            value = value.strip().lower()
            if len(value) > 254:
                raise ValueError("Email address is too long.")
            normalized.append(BookingInput.email_address(value))
        if len(set(normalized)) != len(normalized):
            raise ValueError("Enter each recipient only once.")
        return sorted(normalized)


@router.post("/{event_id}/invitations")
def invite(
    event_id: UUID,
    body: InvitationInput,
    actor: HostIdentity = Depends(current_host),
    repository=Depends(get_invitation_repository),
):
    return {"invitation": repository.queue(actor.user_id, event_id, body)}


@router.get("/{event_id}/invitations/{batch_id}")
def status(
    event_id: UUID,
    batch_id: UUID,
    actor: HostIdentity = Depends(current_host),
    repository=Depends(get_invitation_repository),
):
    return {"invitation": repository.status(actor.user_id, event_id, batch_id)}
