from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.db.guest_history import get_guest_history_repository
from app.guest_auth import GuestIdentity, current_guest

router = APIRouter(prefix="/api/guest", tags=["guest history"])


@router.get("/bookings")
def history(
    kind: Literal["upcoming", "past", "cancelled"] = "upcoming",
    offset: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=25, ge=1, le=50),
    identity: GuestIdentity = Depends(current_guest),
    repo=Depends(get_guest_history_repository),
):
    return repo.history(identity, kind, offset, limit)
