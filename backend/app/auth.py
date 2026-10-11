"""Verify Supabase-issued identities before any host request."""

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from starlette.exceptions import HTTPException

from app.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class HostIdentity:
    user_id: UUID
    email: str


def failure(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


@lru_cache(maxsize=4)
def get_jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(issuer + "/.well-known/jwks.json", lifespan=300, timeout=5)


def verify_token(token: str, settings: Settings) -> HostIdentity:
    if not settings.auth_configured:
        raise failure(503, "AUTH_UNAVAILABLE", "Host sign-in is not available yet.")
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in ("ES256", "RS256") or not header.get("kid"):
            raise jwt.InvalidTokenError()
        key = get_jwks_client(settings.issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["ES256", "RS256"],
            issuer=settings.issuer,
            audience="authenticated",
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
            raise jwt.InvalidTokenError()
        identity = HostIdentity(UUID(claims["sub"]), str(claims.get("email", "")))
    except jwt.PyJWKClientConnectionError:
        raise failure(
            503, "AUTH_UNAVAILABLE", "Sign-in verification is temporarily unavailable."
        ) from None
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise failure(
            401, "INVALID_SESSION", "Your session is invalid or expired. Sign in again."
        ) from None
    return identity


def current_host(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> HostIdentity:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise failure(401, "SIGN_IN_REQUIRED", "Sign in to manage your host profile.")
    return verify_token(credentials.credentials, settings)
