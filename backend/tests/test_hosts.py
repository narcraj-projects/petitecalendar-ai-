from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import jwt
import pytest
from app import auth
from app.auth import HostIdentity, current_host, verify_token
from app.config import Settings, get_settings
from app.db.profiles import get_profile_repository
from app.main import app
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

USER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
SETTINGS = Settings("https://example.supabase.co", "sb_publishable_test", "private-database-url")
KEY = ec.generate_private_key(ec.SECP256R1())


def token(**overrides):
    now = datetime.now(UTC)
    claims = dict(
        sub=str(USER),
        iss=SETTINGS.issuer,
        aud="authenticated",
        role="authenticated",
        iat=now,
        exp=now + timedelta(minutes=5),
    )
    claims.update(overrides)
    return jwt.encode(claims, KEY, algorithm="ES256", headers={"kid": "test-key"})


@pytest.fixture(autouse=True)
def clean_dependencies():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def trusted_key(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=KEY.public_key())
        ),
    )


def test_signed_identity(trusted_key):
    assert verify_token(token(), SETTINGS).user_id == USER


def test_booking_contact_requires_verified_session_and_uses_only_own_profile():
    client = TestClient(app)
    assert client.get("/api/me/booking-contact").status_code == 401
    calls = []

    class Repo:
        def get(self, actor):
            calls.append(actor)
            return {"display_name": "Signed fixture"}

    app.dependency_overrides[current_host] = lambda: HostIdentity(USER, "signed@example.com")
    app.dependency_overrides[get_profile_repository] = lambda: Repo()
    response = client.get("/api/me/booking-contact?user_id=" + str(OTHER))
    assert response.json() == {"name": "Signed fixture", "email": "signed@example.com"}
    assert calls == [USER] and response.headers["cache-control"] == "no-store"


def test_booking_contact_never_invents_missing_profile_name():
    app.dependency_overrides[current_host] = lambda: HostIdentity(USER, "signed@example.com")
    app.dependency_overrides[get_profile_repository] = lambda: SimpleNamespace(get=lambda _: None)
    assert TestClient(app).get("/api/me/booking-contact").json() == {
        "name": "",
        "email": "signed@example.com",
    }


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "invalid"},
        {"aud": "other"},
        {"iss": "https://hostile.test"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"role": "service_role"},
        {"is_anonymous": True},
        {"iat": datetime.now(UTC) + timedelta(hours=1)},
    ],
)
def test_invalid_claims(trusted_key, claims):
    with pytest.raises(HTTPException) as error:
        verify_token(token(**claims), SETTINGS)
    assert error.value.status_code == 401


def test_wrong_signature(trusted_key):
    other_key = ec.generate_private_key(ec.SECP256R1())
    claims = jwt.decode(token(), options={"verify_signature": False})
    bad = jwt.encode(claims, other_key, algorithm="ES256", headers={"kid": "test-key"})
    with pytest.raises(HTTPException):
        verify_token(bad, SETTINGS)


def test_untrusted_algorithm(trusted_key):
    with pytest.raises(HTTPException):
        verify_token(jwt.encode({"sub": str(USER)}, "x" * 32, algorithm="HS256"), SETTINGS)


def test_missing_required_claim(trusted_key):
    claims = jwt.decode(token(), options={"verify_signature": False})
    del claims["exp"]
    with pytest.raises(HTTPException):
        verify_token(
            jwt.encode(claims, KEY, algorithm="ES256", headers={"kid": "test-key"}), SETTINGS
        )


def test_auth_service_unavailable(monkeypatch):
    def unavailable(_):
        raise jwt.PyJWKClientConnectionError("redacted")

    monkeypatch.setattr(auth, "get_jwks_client", unavailable)
    with pytest.raises(HTTPException) as error:
        verify_token(token(), SETTINGS)
    assert error.value.status_code == 503


class Repository:
    def __init__(self):
        self.actors = []
        self.profiles = {OTHER: {"display_name": "Other host"}}

    def get(self, actor):
        self.actors.append(actor)
        return self.profiles.get(actor)

    def save(self, actor, values):
        self.actors.append(actor)
        self.profiles[actor] = values
        return values


def test_profile_identity_cannot_be_supplied_by_client():
    repo = Repository()
    app.dependency_overrides[current_host] = lambda: HostIdentity(USER, "")
    app.dependency_overrides[get_profile_repository] = lambda: repo
    client = TestClient(app)
    assert client.get("/api/me?user_id=" + str(OTHER)).json()["profile"] is None
    values = {"display_name": "Test Host", "username": "test-host", "timezone": "Asia/Kolkata"}
    assert client.put("/api/me/profile", json={**values, "user_id": str(OTHER)}).status_code == 422
    assert client.put("/api/me/profile", json=values).status_code == 200
    assert repo.actors == [USER, USER]
    assert repo.profiles[OTHER] == {"display_name": "Other host"}


@pytest.mark.parametrize(
    "values",
    [
        {"username": "app"},
        {"username": "UPPER"},
        {"username": "bad--name"},
        {"username": "ab"},
        {"username": "abc-"},
        {"display_name": "x"},
        {"timezone": "Mars/Unknown"},
    ],
)
def test_invalid_profile_is_not_saved(values):
    repo = Repository()
    app.dependency_overrides[current_host] = lambda: HostIdentity(USER, "")
    app.dependency_overrides[get_profile_repository] = lambda: repo
    payload = dict(display_name="Test Host", username="test-host", timezone="UTC")
    payload.update(values)
    assert TestClient(app).put("/api/me/profile", json=payload).status_code == 422
    assert not repo.actors


def test_unauthenticated_requests_and_public_config():
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    client = TestClient(app)
    assert client.get("/api/me").status_code == 401
    assert client.put("/api/me/profile", json={}).status_code == 401
    assert "private-database-url" not in client.get("/api/auth/config").text


def test_username_conflict_has_structured_error():
    repo = Repository()

    def conflict(*_):
        raise auth.failure(409, "USERNAME_TAKEN", "That booking username is already taken.")

    repo.save = conflict
    app.dependency_overrides[current_host] = lambda: HostIdentity(USER, "")
    app.dependency_overrides[get_profile_repository] = lambda: repo
    response = TestClient(app).put(
        "/api/me/profile",
        json={"display_name": "Test Host", "username": "test-host", "timezone": "UTC"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USERNAME_TAKEN"
