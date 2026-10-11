from dataclasses import replace

import pytest
from app.config import Settings
from app.staging import COOKIE, SESSION_SECONDS, StagingAccessMiddleware
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

PASSWORD = "synthetic-staging-password-for-tests"


@pytest.fixture
def gateway(monkeypatch):
    settings = Settings(
        staging_private=True,
        staging_access_password=PASSWORD,
        token_encryption_key=Fernet.generate_key().decode(),
        app_base_url="https://stage.example",
    )
    holder = [settings]
    monkeypatch.setattr("app.staging.get_settings", lambda: holder[0])
    app = FastAPI()
    app.add_middleware(StagingAccessMiddleware)

    @app.get("/{path:path}")
    def page(request: Request):
        return {"authorization": request.headers.get("authorization")}

    with TestClient(app, base_url="https://stage.example") as client:
        yield client, holder


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/assets/app.js",
        "/docs",
        "/api/me/profile",
        "/booking/private",
        "/api/integrations/google/callback",
    ],
)
def test_private_paths_require_access(gateway, path):
    client, _ = gateway
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["www-authenticate"].startswith("Basic")


def test_health_is_available_without_staging_access(gateway):
    client, _ = gateway
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/extra").status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"staging_access_password": ""},
        {"token_encryption_key": "invalid"},
        {"app_base_url": "http://stage.example"},
    ],
)
def test_configuration_fails_closed(gateway, changes):
    client, holder = gateway
    holder[0] = replace(holder[0], **changes)
    assert client.get("/", auth=("staging", PASSWORD)).status_code == 503


def test_access_cookie_preserves_application_bearer_auth(gateway):
    client, _ = gateway
    response = client.get("/", auth=("staging", PASSWORD))
    assert response.status_code == 200
    assert response.json()["authorization"] is None
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    response = client.get("/api/me/profile", headers={"Authorization": "Bearer synthetic-jwt"})
    assert response.status_code == 200
    assert response.json()["authorization"] == "Bearer synthetic-jwt"
    assert response.headers["cache-control"] == "no-store"


def test_tampered_and_expired_cookies_and_password_rotation(gateway):
    client, holder = gateway
    client.cookies.set(COOKIE, "tampered")
    assert client.get("/").status_code == 401
    client.cookies.clear()
    assert client.get("/", auth=("staging", PASSWORD)).status_code == 200
    token = client.cookies.get(COOKIE)
    cipher = Fernet(holder[0].token_encryption_key.encode())
    import time

    expired = cipher.encrypt_at_time(
        cipher.decrypt(token.encode()), int(time.time()) - SESSION_SECONDS - 1
    ).decode()
    client.cookies.clear()
    client.cookies.set(COOKIE, expired)
    assert client.get("/").status_code == 401
    client.cookies.clear()
    assert client.get("/", auth=("staging", PASSWORD)).status_code == 200
    holder[0] = replace(holder[0], staging_access_password="another-strong-staging-password")
    assert client.get("/").status_code == 401


@pytest.mark.parametrize("authorization", ["Basic !!!", "Basic dXNlcg==", "Bearer token"])
def test_invalid_credentials(gateway, authorization):
    client, _ = gateway
    assert client.get("/", headers={"Authorization": authorization}).status_code == 401
    assert client.get("/", auth=("staging", "wrong")).status_code == 401


def test_local_default_does_not_require_gateway(gateway):
    client, holder = gateway
    holder[0] = replace(holder[0], staging_private=False)
    assert client.get("/").status_code == 200
