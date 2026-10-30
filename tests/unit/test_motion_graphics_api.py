"""
Unit tests for the Motion Graphics FastAPI endpoints.
"""

import base64
import pytest
from fastapi.testclient import TestClient
from engine.api.app import app


@pytest.fixture
def client():
    # Use headers matching LocalApiSecurityMiddleware development requirements if needed
    headers = {"X-PanelFlow-Control": "test"}
    with TestClient(app, base_url="http://127.0.0.1:8765", headers=headers) as c:
        yield c


def test_list_motion_presets_endpoint(client):
    res = client.get("/api/motion-graphics/presets")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 6
    ids = [p["id"] for p in data]
    assert "keynote_showcase" in ids
    assert "cyber_hud" in ids
    assert "scifi_containment" in ids
    assert "corporate_benchmark" in ids
    assert "kinetic_editorial" in ids
    assert "anime_battle_hud" in ids


def test_get_motion_preset_endpoint(client):
    res = client.get("/api/motion-graphics/presets/keynote_showcase")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "keynote_showcase"
    assert "default_props" in data
    assert data["default_props"]["headline"] == "SYNTHESIS ONE"

    # Non-existent preset returns 404
    res_404 = client.get("/api/motion-graphics/presets/invalid_preset_id")
    assert res_404.status_code == 404


def test_preview_motion_frame_endpoint(client):
    payload = {
        "preset_id": "cyber_hud",
        "timestamp": 1.5,
        "duration_sec": 6.0,
        "width": 640,
        "height": 360,
        "aspect_ratio": "16:9",
        "props": {
            "title": "NEURAL_MAINFRAME // TEST",
            "target_name": "TEST_SUBJECT",
        },
    }
    res = client.post("/api/motion-graphics/preview", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["preset_id"] == "cyber_hud"
    assert data["timestamp"] == 1.5
    assert data["width"] == 640
    assert data["height"] == 360
    assert "image_base64" in data
    assert len(data["image_base64"]) > 1000

    # Ensure it's valid base64 image data
    raw_bytes = base64.b64decode(data["image_base64"])
    assert raw_bytes[:2] == b"\xff\xd8"  # JPEG Magic bytes


def test_preview_vertical_aspect_ratio(client):
    payload = {
        "preset_id": "keynote_showcase",
        "timestamp": 2.0,
        "duration_sec": 4.0,
        "width": 360,
        "height": 640,
        "aspect_ratio": "9:16",
    }
    res = client.post("/api/motion-graphics/preview", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["width"] == 360
    assert data["height"] == 640
