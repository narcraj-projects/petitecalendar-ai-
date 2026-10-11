"""Extra staging access barrier; normal application authorization still applies."""

import base64
import binascii
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings

COOKIE = "__Host-petcalendar-staging"
SESSION_SECONDS = 8 * 60 * 60


class StagingAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        settings = get_settings()
        if not settings.staging_private or request.url.path == "/api/health":
            return await call_next(request)

        def reject(status, code, message):
            headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
            if status == 401:
                headers["WWW-Authenticate"] = 'Basic realm="PetCalendar AI staging"'
            return JSONResponse(
                {"error": {"code": code, "message": message}}, status_code=status, headers=headers
            )

        try:
            if len(settings.staging_access_password) < 20 or not settings.app_base_url.startswith(
                "https://"
            ):
                raise ValueError
            cipher = Fernet(settings.token_encryption_key.encode())
        except (ValueError, TypeError):
            return reject(503, "STAGING_UNAVAILABLE", "Staging access is not configured.")

        marker = (
            b"staging-access:"
            + hashlib.sha256(settings.staging_access_password.encode()).hexdigest().encode()
        )
        token = request.cookies.get(COOKIE, "")
        try:
            if token and hmac.compare_digest(
                cipher.decrypt(token.encode(), ttl=SESSION_SECONDS), marker
            ):
                response = await call_next(request)
                response.headers["Cache-Control"] = "no-store"
                return response
        except (InvalidToken, ValueError):
            pass

        authorization = request.headers.get("authorization", "")
        try:
            scheme, credentials = authorization.split(" ", 1)
            if scheme.lower() != "basic":
                raise ValueError
            username, password = base64.b64decode(credentials, validate=True).decode().split(":", 1)
            accepted = hmac.compare_digest(username.encode(), b"staging") and hmac.compare_digest(
                password.encode(), settings.staging_access_password.encode()
            )
        except (ValueError, UnicodeError, binascii.Error):
            accepted = False
        if not accepted:
            return reject(401, "STAGING_ACCESS_REQUIRED", "Enter your staging access credentials.")

        # Do not pass gateway credentials to application routes. Supabase JWTs use this header.
        request.scope["headers"] = [
            (key, value)
            for key, value in request.scope["headers"]
            if key.lower() != b"authorization"
        ]
        response = await call_next(request)
        response.set_cookie(
            COOKIE,
            cipher.encrypt(marker).decode(),
            max_age=SESSION_SECONDS,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        return response
