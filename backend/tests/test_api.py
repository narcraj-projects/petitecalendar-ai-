from app.auth import failure
from app.main import app, public_repository
from fastapi.testclient import TestClient

client = TestClient(app)
PATH = "/api/public/events/ananya/career-strategy"


def test_event_is_explicit_demo_metadata():
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"
    assert response.json()["durations"] == [30, 45, 60]
    assert "payment" not in response.json()


def test_unknown_event_returns_structured_error():
    class EmptyRepository:
        def public_event(self, username, slug):
            raise failure(404, "EVENT_NOT_FOUND", "This event is not available.")

    app.dependency_overrides[public_repository] = lambda: EmptyRepository()
    try:
        response = client.get("/api/public/events/unknown/private")
    finally:
        app.dependency_overrides.pop(public_repository)
    assert response.status_code == 404
    assert response.json()["error"]["message"]


def test_date_range_and_timezone_errors():
    for params in [
        {"start_date": "bad", "end_date": "2026-10-13"},
        {"start_date": "2026-10-13", "end_date": "2026-10-12"},
        {"start_date": "2026-10-13", "end_date": "2027-10-13"},
        {"start_date": "2026-10-13", "end_date": "2026-10-13", "timezone": "invalid"},
        {"start_date": "2026-10-13", "end_date": "2026-10-13", "duration": 15},
    ]:
        response = client.get(PATH + "/slots", params=params)
        assert response.status_code == 422
        assert response.json()["error"]["message"]


def test_slots_are_utc_and_read_only():
    response = client.get(
        PATH + "/slots",
        params={
            "start_date": "2026-10-13",
            "end_date": "2026-10-13",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"
    assert all(slot["start"].endswith("+00:00") for slot in response.json()["slots"])
    rejected = client.post(PATH + "/slots")
    assert rejected.status_code == 405
    assert rejected.json()["error"]["message"]
