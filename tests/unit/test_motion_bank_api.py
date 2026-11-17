"""API integration tests for Motion Bank router endpoints."""
from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
import pytest
from starlette.testclient import TestClient

from engine.api.app import app
from engine.acquisition.rights.models import RightsStatus


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    # Every test gets its own bank so nothing is ever written to the owner's real Motion Bank.
    monkeypatch.setenv("PANELFLOW_MOTION_BANK_DIR", str(tmp_path / "bank"))
    return TestClient(app)


def test_motion_bank_status_endpoint(client: TestClient):
    """Verifies that the /api/motion_bank/status endpoint reports online status and manifest."""
    resp = client.get("/api/motion_bank/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "online"
    assert "dwpose_ready" in data
    assert "manifest" in data
    assert len(data["manifest"]) >= 2


def test_motion_bank_ingest_and_extract_flow(client: TestClient, tmp_path: Path):
    """Tests full API flow: ingest local video -> extract poses -> query motion library."""
    # Create sample synthetic test video
    test_video = tmp_path / "action_flow.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(test_video), fourcc, 24.0, (160, 120))
    for i in range(24):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        cv2.circle(frame, (80, 60), 10 + i, (255, 255, 255), -1)
        out.write(frame)
    out.release()

    # 1. Ingest via API
    ingest_payload = {
        "source": str(test_video),
        "title": "Martial Arts Kick Test",
        "rights": {
            "status": RightsStatus.USER_OWNED.value,
            "permission_notes": "Locally synthesized test footage",
        },
    }
    ingest_resp = client.post("/api/motion_bank/ingest", json=ingest_payload)
    assert ingest_resp.status_code == 200
    ingest_data = ingest_resp.json()
    local_path = ingest_data["local_path"]
    assert Path(local_path).exists()

    # 2. Extract poses into Motion Bank
    extract_payload = {
        "video_path": local_path,
        "action_title": "Spinning High Kick",
        "action_tags": ["kick", "martial_arts", "fight"],
        "action_summary": "A 360-degree rotation finishing with an extended right leg high kick",
        "start_sec": 0.0,
        "end_sec": 1.0,
        "synthetic": True,
    }
    extract_resp = client.post("/api/motion_bank/extract", json=extract_payload)
    assert extract_resp.status_code == 200
    motion_data = extract_resp.json()
    motion_id = motion_data["id"]
    assert motion_data["action_title"] == "Spinning High Kick"
    assert "kick" in motion_data["action_tags"]
    assert "synthetic" in motion_data["action_tags"]
    assert motion_data["metadata"]["synthetic"] is True
    assert str(tmp_path / "bank") in motion_data["keypoints_path"]

    # 3. Query motions list
    list_resp = client.get("/api/motion_bank/motions?tag=kick")
    assert list_resp.status_code == 200
    motions = list_resp.json()
    assert any(m["id"] == motion_id for m in motions)

    # 4. Search motions
    search_resp = client.get("/api/motion_bank/search?q=Spinning")
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert any(m["id"] == motion_id for m in results)


def test_motion_bank_guide_endpoints(client: TestClient, tmp_path: Path):
    """Tests Guide Model training and choreography generation endpoints."""
    # 1. Train guide model for 1 epoch
    # generating before any training is refused (an untrained model only makes noise)
    early = client.post("/api/motion_bank/guide/generate", json={"prompt": "x", "num_frames": 16})
    assert early.status_code == 409

    # an empty bank (or one holding only synthetic motions) cannot be trained on
    assert client.post("/api/motion_bank/guide/train", json={"num_epochs": 1}).status_code == 400
    _add_synthetic_motion(client, tmp_path)
    assert client.post("/api/motion_bank/guide/train", json={"num_epochs": 1}).status_code == 400
    train_resp = client.post(
        "/api/motion_bank/guide/train", json={"num_epochs": 1, "batch_size": 2, "include_synthetic": True}
    )
    assert train_resp.status_code == 200
    train_data = train_resp.json()
    assert train_data["status"] == "success"
    assert "checkpoint" in train_data

    # 2. Generate choreography from prompt
    gen_payload = {
        "prompt": "Samurai swift downward slash",
        "num_frames": 16,
        "fps": 24.0,
        "width": 320,
        "height": 240,
        "render_video": True,
    }
    gen_resp = client.post("/api/motion_bank/guide/generate", json=gen_payload)
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    assert gen_data["prompt"] == "Samurai swift downward slash"
    assert gen_data["frame_count"] == 16
    assert gen_data["control_video_path"] is not None
    assert Path(gen_data["control_video_path"]).exists()
    assert len(gen_data["poses"]) > 0


def _make_video(path: Path, frames: int = 24) -> Path:
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24.0, (160, 120))
    for i in range(frames):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        cv2.circle(frame, (80, 60), 10 + i, (255, 255, 255), -1)
        out.write(frame)
    out.release()
    return path


def _add_synthetic_motion(client: TestClient, tmp_path: Path) -> dict:
    video = _make_video(tmp_path / "synthetic_src.mp4")
    resp = client.post(
        "/api/motion_bank/extract",
        json={"video_path": str(video), "action_title": "Fake walk", "synthetic": True},
    )
    assert resp.status_code == 200
    return resp.json()


def test_extract_refuses_fake_skeleton_when_models_missing(client: TestClient, tmp_path: Path, monkeypatch):
    """Without the DWPose files, a normal extract is an error, never a silent mock skeleton."""
    from engine.api.routers import motion_bank as router

    monkeypatch.setattr(router._extractor, "is_ready", lambda: False)
    video = _make_video(tmp_path / "src.mp4")
    resp = client.post("/api/motion_bank/extract", json={"video_path": str(video), "action_title": "Kick"})
    assert resp.status_code == 503
    assert client.get("/api/motion_bank/motions").json() == []


def test_status_reports_counts_and_providers(client: TestClient, tmp_path: Path):
    _add_synthetic_motion(client, tmp_path)
    data = client.get("/api/motion_bank/status").json()
    assert data["motion_count"] == 1
    assert data["synthetic_count"] == 1
    assert "dwpose_providers" in data
