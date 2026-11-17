import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import anatomy
from engine.original.anatomy import store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "checks_path", lambda: tmp_path / "c.jsonl")
    app = FastAPI()
    app.include_router(anatomy.router)
    return TestClient(app)


def test_stats_shape_when_nothing_was_checked(client):
    assert client.get("/api/original/anatomy/stats").json() == {"checked": 0, "by_model": {}, "owner_flags": 0, "flagged": []}


def test_flagging_a_missed_mistake_shows_up_in_the_stats(client):
    r = client.post("/api/original/anatomy/flag", json={"picture": "hug.png", "model": "hidream_i1_fast", "note": "four arms"})
    assert r.status_code == 200
    s = client.get("/api/original/anatomy/stats").json()
    assert s["owner_flags"] == 1 and s["flagged"][0]["note"] == "four arms"


def test_a_blank_note_is_refused(client):
    assert client.post("/api/original/anatomy/flag", json={"picture": "hug.png", "note": "   "}).status_code == 400
    assert client.post("/api/original/anatomy/flag", json={"picture": "hug.png", "note": ""}).status_code == 422
