import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from app.api.calendar import CalendarPreferences
from app.auth import HostIdentity, current_host
from app.config import Settings
from app.integrations.google import SCOPES, CalendarError, GoogleCalendar, TokenVault
from app.main import app
from app.services.calendar import CalendarService, get_calendar_service
from app.worker import CalendarWorker
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from requests import Request, Response
from requests_oauthlib import OAuth2Session


def settings():
    return Settings(
        google_client_id="fixture.apps.googleusercontent.com",
        google_client_secret="fixture",
        token_encryption_key=Fernet.generate_key().decode(),
    )


def adapter(handler):
    return GoogleCalendar(settings(), httpx.Client(transport=httpx.MockTransport(handler)))


def test_authorization_separate_scopes_offline_and_pkce():
    provider = adapter(lambda r: httpx.Response(500))
    url, verifier = provider.authorization("s" * 43)
    q = parse_qs(urlparse(url).query)
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert set(q["scope"][0].split()) == set(SCOPES)
    assert q["redirect_uri"] == ["http://127.0.0.1:8017/api/integrations/google/callback"]
    assert verifier and q["code_challenge_method"] == ["S256"]
    provider.close()


@pytest.mark.parametrize("extra", [False, True])
def test_exchange_accepts_all_required_scopes_with_previously_granted_extras(monkeypatch, extra):
    def response(session, method, url, **kwargs):
        assert url == "https://oauth2.googleapis.com/token"
        body = kwargs["data"]
        assert body["code_verifier"] == "v" * 64
        assert body["redirect_uri"] == "http://127.0.0.1:8017/api/integrations/google/callback"
        result = Response()
        result.status_code = 200
        result.request = Request("POST", url).prepare()
        result._content = json.dumps(
            {
                "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": " ".join(SCOPES) + (" openid" if extra else ""),
            }
        ).encode()
        return result

    monkeypatch.setattr(OAuth2Session, "request", response)
    provider = adapter(lambda r: httpx.Response(500))
    assert provider.exchange("synthetic-code", "s" * 43, "v" * 64) == "synthetic-refresh"
    provider.close()


@pytest.mark.parametrize("error", ["partial_scope", "missing_refresh", "invalid_client"])
def test_exchange_rejects_incomplete_consent_and_redacts_client_errors(monkeypatch, error):
    def response(*args, **kwargs):
        result = Response()
        result.status_code = 400 if error == "invalid_client" else 200
        result.request = Request("POST", "https://oauth2.googleapis.com/token").prepare()
        token = {
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": " ".join(SCOPES),
        }
        if error == "partial_scope":
            token["scope"] = SCOPES[0]
        elif error == "missing_refresh":
            del token["refresh_token"]
        else:
            token = {"error": "invalid_client", "error_description": "sensitive-provider-details"}
        result._content = json.dumps(token).encode()
        return result

    monkeypatch.setattr(OAuth2Session, "request", response)
    provider = adapter(lambda r: httpx.Response(500))
    with pytest.raises(CalendarError) as raised:
        provider.exchange("synthetic-code", "s" * 43, "v" * 64)
    assert raised.value.code == (
        "client_configuration" if error == "invalid_client" else "consent_incomplete"
    )
    assert "sensitive-provider-details" not in str(raised.value)
    provider.close()


def test_vault_tamper_and_host_binding():
    first, other = uuid4(), uuid4()
    vault = TokenVault(Fernet.generate_key().decode())
    ciphertext = vault.seal(first, "synthetic-refresh")
    assert (
        "synthetic-refresh" not in ciphertext
        and vault.open(first, ciphertext) == "synthetic-refresh"
    )
    for actor, value in [(other, ciphertext), (first, ciphertext[:-5] + "wrong"), (first, None)]:
        with pytest.raises(CalendarError):
            vault.open(actor, value)


@pytest.mark.parametrize(
    "value", [{"blocking_ids": ["same", "same"]}, {"revision": True}, {"user_id": "other"}]
)
def test_calendar_preferences_validation(value):
    with pytest.raises(ValidationError):
        CalendarPreferences(
            **({"revision": 1, "blocking_ids": [], "destination_id": "calendar"} | value)
        )


@pytest.mark.parametrize(
    "response",
    [
        {"calendars": {}},
        {"calendars": {"selected": {"errors": [{"reason": "notFound"}]}}},
        {
            "calendars": {
                "selected": {
                    "busy": [{"start": "2026-10-12T10:00:00", "end": "2026-10-12T11:00:00"}]
                }
            }
        },
    ],
)
def test_free_busy_fails_closed(response):
    provider = adapter(lambda r: httpx.Response(200, json=response))
    with pytest.raises(CalendarError):
        provider.free_busy(
            "token", ["selected"], datetime.now(UTC), datetime.now(UTC) + timedelta(days=1)
        )
    provider.close()


def test_free_busy_only_selected_utc_intervals():
    def handler(r):
        assert json.loads(r.content)["items"] == [{"id": "selected"}]
        return httpx.Response(
            200,
            json={
                "calendars": {
                    "selected": {
                        "busy": [
                            {
                                "start": "2026-10-12T10:00:00+05:30",
                                "end": "2026-10-12T11:00:00+05:30",
                            }
                        ]
                    }
                }
            },
        )

    provider = adapter(handler)
    busy = provider.free_busy(
        "token", ["selected"], datetime.now(UTC), datetime.now(UTC) + timedelta(days=1)
    )
    assert busy[0].start == datetime(2026, 10, 12, 4, 30, tzinfo=UTC)
    provider.close()


def booking():
    return {
        "id": uuid4(),
        "revision": 1,
        "start_at": datetime(2026, 10, 20, 10, tzinfo=UTC),
        "end_at": datetime(2026, 10, 20, 10, 30, tzinfo=UTC),
        "invitee_name": "Fixture",
        "snapshot": {"title": "Fixture event", "location": "Online", "host_timezone": "UTC"},
    }


def test_ambiguous_insert_recovers_one_event_and_meet():
    stored = None
    creates = 0

    def handler(r):
        nonlocal stored, creates
        if r.method == "GET":
            return httpx.Response(200, json=stored) if stored else httpx.Response(404)
        creates += 1
        stored = json.loads(r.content)
        assert "attendees" not in stored and r.url.params["sendUpdates"] == "none"
        assert stored["conferenceData"]["createRequest"]["requestId"] == stored["id"]
        stored["hangoutLink"] = "https://meet.google.com/abc-defg-hij"
        raise httpx.ReadTimeout("synthetic timeout", request=r)

    provider = adapter(handler)
    value = booking()
    with pytest.raises(CalendarError):
        provider.ensure_event("token", "calendar", value, True)
    first = provider.ensure_event("token", "calendar", value, True)
    assert provider.ensure_event("token", "calendar", value, True) == first
    assert first["meet_url"] == "https://meet.google.com/abc-defg-hij" and creates == 1
    assert all(c in "0123456789abcdefghijklmnopqrstuv" for c in first["event_id"])
    provider.close()


def test_pending_meet_only_polls_existing_event():
    stored = None
    creates = 0
    pending = True

    def handler(r):
        nonlocal stored, creates
        if r.method == "POST":
            creates += 1
            stored = json.loads(r.content)
        if stored is None:
            return httpx.Response(404)
        return httpx.Response(
            200,
            json=stored
            | ({} if pending else {"hangoutLink": "https://meet.google.com/abc-defg-hij"}),
        )

    provider = adapter(handler)
    value = booking()
    with pytest.raises(CalendarError) as error:
        provider.ensure_event("token", "calendar", value, True)
    assert error.value.code == "meet_pending"
    pending = False
    assert provider.ensure_event("token", "calendar", value, True)["meet_url"] and creates == 1
    provider.close()


def test_external_time_change_requires_attention():
    value = booking()
    body = {
        "start": {"dateTime": "2026-10-21T10:00:00Z"},
        "end": {"dateTime": "2026-10-21T10:30:00Z"},
        "extendedProperties": {
            "private": {"petitecalendarBooking": str(value["id"]), "petitecalendarRevision": "1"}
        },
    }
    provider = adapter(lambda r: httpx.Response(200, json=body))
    with pytest.raises(CalendarError) as error:
        provider.ensure_event("token", "calendar", value, False)
    assert error.value.code == "event_changed"
    provider.close()


def test_revoked_token_requires_reconnect():
    provider = adapter(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(CalendarError) as error:
        provider.access_token("synthetic-refresh")
    assert error.value.code == "reconnect_required"
    provider.close()


def test_destination_always_blocks_time():
    actor = uuid4()
    saved = []
    row = {
        "user_id": actor,
        "revision": 1,
        "generation": uuid4(),
        "status": "connected",
        "token_ciphertext": "unused",
        "blocking_ids": [],
        "destination_id": None,
        "create_meet": True,
    }
    repo = SimpleNamespace(read=lambda _: row, preferences=lambda *args: saved.append(args))
    provider = SimpleNamespace(
        calendars=lambda token: [
            SimpleNamespace(id="destination", writable=True, meet_supported=True)
        ]
    )
    service = CalendarService(repo, provider, settings())
    service._access = lambda _: "token"
    service.save(
        actor, CalendarPreferences(revision=1, blocking_ids=[], destination_id="destination")
    )
    assert saved[0][3] == ["destination"]


def test_api_auth_cookie_and_callback_sanitization():
    actor = uuid4()
    calls = []
    fake = SimpleNamespace(
        settings=settings(),
        status=lambda _: {"configured": True},
        start=lambda _: ("https://accounts.google.com/consent", "b" * 43),
        callback=lambda state, binding, code: calls.append((state, binding, code)) or "connected",
    )
    app.dependency_overrides[get_calendar_service] = lambda: fake
    try:
        client = TestClient(app)
        assert client.get("/api/me/integrations/google").status_code == 401
        app.dependency_overrides[current_host] = lambda: HostIdentity(actor, "")
        response = client.post("/api/me/integrations/google/connect")
        assert (
            "HttpOnly" in response.headers["set-cookie"]
            and "SameSite=lax" in response.headers["set-cookie"]
        )
        callback = client.get(
            "/api/integrations/google/callback?state=" + "s" * 43 + "&code=synthetic-code",
            follow_redirects=False,
        )
        assert callback.headers["location"] == "/app/integrations?calendar=connected"
        assert "synthetic-code" not in callback.headers["location"]
        assert callback.headers["cache-control"] == "no-store" and calls == [
            ("s" * 43, "b" * 43, "synthetic-code")
        ]
        assert (
            client.get("/api/integrations/google/callback?state=wrong", follow_redirects=False)
            .headers["location"]
            .endswith("failed")
        )
    finally:
        app.dependency_overrides.clear()


def test_worker_changed_account_does_not_create_an_event():
    value = booking()
    host = uuid4()
    job = {"user_id": host, "generation": uuid4(), "revision": 1}
    result = []
    worker = CalendarWorker.__new__(CalendarWorker)
    worker.claim = lambda host=None: job
    worker.load = lambda job: ({"generation": uuid4()}, value | {"status": "confirmed"})
    worker.finish = lambda job, **kw: result.append(kw)
    worker.deliver(job)
    assert result == [{"error": "connection_changed"}]
