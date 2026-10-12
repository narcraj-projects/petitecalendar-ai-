from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from app.auth import HostIdentity
from app.config import Settings
from app.db.guest_history import get_guest_history_repository
from app.guest_auth import GuestIdentity, GuestVerifier, current_guest
from app.main import app
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

USER, OTHER = uuid4(), uuid4()
SETTINGS = Settings(supabase_url="https://guest.example.com", publishable_key="public-fixture")


def verify_user(payload, identity=None, status=200):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    verifier = GuestVerifier(SETTINGS, client)
    result = verifier.verify("synthetic-token", identity or HostIdentity(USER, "guest@example.com"))
    return result, seen


def test_current_verified_provider_email_controls_identity():
    identity, requests = verify_user(
        {
            "id": str(USER),
            "email": "Guest@Example.com",
            "email_confirmed_at": "2026-10-12T00:00:00Z",
        }
    )
    assert identity == GuestIdentity(USER, "guest@example.com")
    assert requests[0].url.path == "/auth/v1/user"
    assert requests[0].headers["apikey"] == "public-fixture"


@pytest.mark.parametrize(
    "patch,expected",
    [
        ({"email_confirmed_at": None, "user_metadata": {"email_verified": True}}, 403),
        ({"email": "other@example.com"}, 401),
        ({"id": str(OTHER)}, 401),
        ({"email": "bad"}, 401),
    ],
)
def test_unverified_or_changed_email_and_subject_cannot_access_history(patch, expected):
    user = {"id": str(USER), "email": "guest@example.com", "email_confirmed_at": "2026-10-12"}
    with pytest.raises(HTTPException) as error:
        verify_user(user | patch)
    assert error.value.status_code == expected


@pytest.mark.parametrize("status,expected", [(401, 401), (403, 401), (429, 503), (500, 503)])
def test_provider_failures_do_not_return_history_or_raw_payloads(status, expected):
    with pytest.raises(HTTPException) as error:
        verify_user({"message": "sensitive-provider-body"}, status=status)
    assert error.value.status_code == expected
    assert "sensitive-provider-body" not in str(error.value)


def test_history_requires_auth_and_ignores_browser_supplied_email():
    client = TestClient(app)
    assert client.get("/api/guest/bookings?email=guest@example.com").status_code == 401
    calls = []

    def history(identity, kind, offset, limit):
        calls.append((identity, kind, offset, limit))
        return {"bookings": [], "has_more": False, "next_offset": None}

    app.dependency_overrides[current_guest] = lambda: GuestIdentity(USER, "verified@example.com")
    app.dependency_overrides[get_guest_history_repository] = lambda: SimpleNamespace(
        history=history
    )
    try:
        response = client.get(
            "/api/guest/bookings?kind=past&email=other@example.com&user_id=" + str(OTHER)
        )
        assert response.status_code == 200
        assert calls == [(GuestIdentity(USER, "verified@example.com"), "past", 0, 25)]
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        for query in ["kind=all", "offset=-1", "offset=10001", "limit=51", "limit=0"]:
            assert client.get("/api/guest/bookings?" + query).status_code == 422
        assert len(calls) == 1
    finally:
        app.dependency_overrides.clear()
