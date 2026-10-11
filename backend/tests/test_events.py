from uuid import UUID, uuid4

import pytest
from app.api.events import EventInput
from app.auth import HostIdentity, current_host, failure
from app.db.events import get_event_repository
from app.main import app, public_repository
from fastapi.testclient import TestClient

ACTOR = UUID("11111111-1111-4111-8111-111111111111")
PAYLOAD = {
    "title": "Strategy call",
    "slug": "strategy-call",
    "durations": [30, 45, 60],
    "default_duration": 45,
}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "changes",
    [
        {"durations": []},
        {"durations": [30, 30]},
        {"durations": [7]},
        {"durations": [250]},
        {"durations": [True]},
        {"durations": ["30"]},
        {"default_duration": 15},
        {"slug": "Bad--slug"},
        {"slug": "x"},
        {"title": "x"},
        {"notice_minutes": -1},
        {"buffer_after": 241},
        {"horizon_days": 0},
        {"max_per_day": 0},
        {"reschedule_hours": 721},
        {"user_id": str(uuid4())},
        {"published": True},
    ],
)
def test_invalid_creation_is_rejected(changes):
    app.dependency_overrides[current_host] = lambda: HostIdentity(ACTOR, "")
    app.dependency_overrides[get_event_repository] = lambda: object()
    response = TestClient(app).post("/api/me/event-types", json=PAYLOAD | changes)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_routes_use_verified_actor_and_revision():
    calls = []

    class Repo:
        def list_events(self, actor):
            calls.append(actor)
            return []

        def save_event(self, actor, values, event_id=None, revision=None):
            calls.append((actor, values, event_id, revision))
            return {"id": str(event_id or uuid4()), **values, "revision": 1}

    app.dependency_overrides[current_host] = lambda: HostIdentity(ACTOR, "")
    app.dependency_overrides[get_event_repository] = lambda: Repo()
    client = TestClient(app)
    assert client.get("/api/me/event-types?user_id=other").json() == {"events": []}
    created = client.post("/api/me/event-types", json=PAYLOAD)
    assert created.status_code == 201
    event_id = created.json()["event"]["id"]
    result = client.put(
        "/api/me/event-types/" + event_id, json=PAYLOAD | {"published": True, "revision": 1}
    )
    assert result.status_code == 200
    assert calls[0] == ACTOR
    assert calls[1][0] == ACTOR and "published" not in calls[1][1]
    assert calls[2][2:] == (UUID(event_id), 1)


def test_event_authentication_and_unknown_id():
    client = TestClient(app)
    assert client.get("/api/me/event-types").status_code == 401
    assert client.post("/api/me/event-types", json=PAYLOAD).status_code == 401
    assert (
        client.put(
            "/api/me/event-types/" + str(uuid4()), json=PAYLOAD | {"revision": 1, "published": True}
        ).status_code
        == 401
    )


def test_unpublished_public_route_returns_not_found():
    class Repo:
        def public_event(self, *_):
            raise failure(404, "EVENT_NOT_FOUND", "This event is not available.")

    app.dependency_overrides[public_repository] = lambda: Repo()
    response = TestClient(app).get("/api/public/events/test/draft")
    assert response.status_code == 404


def test_duration_normalization():
    assert EventInput(**(PAYLOAD | {"durations": [60, 30, 45]})).durations == [30, 45, 60]
