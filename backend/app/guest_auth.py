"""Read the current, verified Supabase email before granting booking-history access."""

import re
from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import bearer, failure, verify_token
from app.config import Settings, get_settings


@dataclass(frozen=True)
class GuestIdentity:
    user_id: UUID
    email: str


class GuestVerifier:
    def __init__(self, settings, client=None):
        self.settings, self.client = settings, client

    def verify(self, token, identity):
        try:
            headers = {"Authorization": "Bearer " + token, "apikey": self.settings.publishable_key}
            if self.client:
                response = self.client.get(self.settings.issuer + "/user", headers=headers)
            else:
                with httpx.Client(timeout=httpx.Timeout(8, connect=3)) as client:
                    response = client.get(self.settings.issuer + "/user", headers=headers)
            if response.status_code in (401, 403):
                raise failure(401, "INVALID_SESSION", "Sign in again to view your bookings.")
            if response.status_code != 200:
                raise failure(
                    503, "AUTH_UNAVAILABLE", "Email verification is temporarily unavailable."
                )
            user = response.json()
            email = str(user.get("email") or "").strip().lower()
            if UUID(user["id"]) != identity.user_id or email != identity.email.strip().lower():
                raise failure(401, "INVALID_SESSION", "Your email changed. Sign in again.")
            # Never trust a browser input or user_metadata.email_verified.
            if not user.get("email_confirmed_at") or not re.fullmatch(
                r"[^\s@]+@[^\s@]+\.[^\s@]+", email
            ):
                raise failure(
                    403, "EMAIL_VERIFICATION_REQUIRED", "Verify your email using a sign-in link."
                )
            return GuestIdentity(identity.user_id, email)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise failure(
                503, "AUTH_UNAVAILABLE", "Email verification is temporarily unavailable."
            ) from None


def current_guest(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise failure(401, "SIGN_IN_REQUIRED", "Verify your email to view your booking history.")
    identity = verify_token(credentials.credentials, settings)
    return GuestVerifier(settings).verify(credentials.credentials, identity)
