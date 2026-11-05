import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from engine.api.routers import chronoflow


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(chronoflow.router)
    return TestClient(app)


def test_api_status(client):
    with patch.object(chronoflow.pipeline, "check_comfy_status") as mock_status:
        mock_status.return_value = {
            "connected": True,
            "gpu": "RTX 5060 Ti",
            "vram_free_gb": 12.0,
            "vram_total_gb": 16.0,
            "queue": {"busy": False},
        }
        res = client.get("/api/chronoflow/status")
        assert res.status_code == 200
        data = res.json()
        assert data["comfy"]["connected"] is True
        assert data["comfy"]["gpu"] == "RTX 5060 Ti"
        assert "models" in data


def test_api_characters_crud(client):
    # GET list
    res = client.get("/api/chronoflow/characters")
    assert res.status_code == 200
    assert "characters" in res.json()

    # POST new character
    new_char = {
        "id": "char_test_agent",
        "name": "Special Agent Whiskers",
        "role": "Detective",
        "image": "whiskers.png",
        "description": "Orange ginger tabby with sunglasses.",
    }
    post_res = client.post("/api/chronoflow/characters", json=new_char)
    assert post_res.status_code == 200
    assert post_res.json()["success"] is True

    # Verify added
    res2 = client.get("/api/chronoflow/characters")
    chars = res2.json()["characters"]
    matched = [c for c in chars if c["id"] == "char_test_agent"]
    assert len(matched) == 1
    assert matched[0]["name"] == "Special Agent Whiskers"

    # DELETE character
    del_res = client.delete("/api/chronoflow/characters/char_test_agent")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_api_ai_director_plan(client):
    payload = {
        "idea": "Cyberpunk runner escapes across neon rooftops",
        "duration": 15,
    }
    res = client.post("/api/chronoflow/ai_director/plan", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["scenes"]) == 3
    assert data["scenes"][0]["shot_index"] == 1
    assert "subject_definitions:" in data["scenes"][0]["prompt"] or "detailed_description:" in data["scenes"][0]["prompt"]


def test_api_jobs_and_sync(client):
    res = client.get("/api/chronoflow/jobs")
    assert res.status_code == 200
    assert "jobs" in res.json()

    sync_res = client.get("/api/chronoflow/sync?v=0")
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert "version" in sync_data
    assert "comfy" in sync_data


def test_api_gallery(client):
    res = client.get("/api/chronoflow/gallery")
    assert res.status_code == 200
    data = res.json()
    assert "masters" in data
    assert "chunks" in data
    assert "images" in data
    assert "stats" in data


def test_api_ui_route(client):
    res = client.get("/api/chronoflow/ui")
    assert res.status_code == 200
    assert "<!DOCTYPE html>" in res.text or "<html" in res.text

def test_full_app_chronoflow_ui_routes():
    from engine.api.app import create_app
    full_client = TestClient(create_app(allow_insecure=True))
    for endpoint in ["/chronoflow/ui", "/chronoflow", "/api/chronoflow/ui"]:
        r = full_client.get(endpoint)
        assert r.status_code == 200
        assert "<!DOCTYPE html>" in r.text or "<html" in r.text
