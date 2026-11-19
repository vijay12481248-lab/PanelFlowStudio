"""Unit tests for Phase 6: REST API endpoints, ComfyUI ArtEngine auto-repair hook, and Job Manager operations."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine.api.app import app
from engine.api.routers.inspector import (
    _visual_inspection_operation,
    _visual_repair_operation,
    get_image_inspector,
    get_image_repair,
    get_temporal_inspector,
    get_video_repair,
)
from engine.comfyui.art import ArtEngine, ArtImage
from engine.inspector.repair import RepairResult
from engine.inspector.schema import (
    DefectRecord,
    QualityDecision,
    TemporalDefectRecord,
    VideoQualityDecision,
)


def _create_synthetic_png(file_path: Path, width: int = 120, height: int = 120) -> Path:
    img = np.full((height, width, 3), (128, 128, 128), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    file_path.write_bytes(buf.tobytes())
    return file_path


def _create_synthetic_video(file_path: Path, frames: int = 24) -> Path:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(file_path), fourcc, 24.0, (120, 120))
    for _ in range(frames):
        frame = np.full((120, 120, 3), (120, 120, 120), dtype=np.uint8)
        out.write(frame)
    out.release()
    return file_path


@pytest.fixture
def client():
    # Allow insecure for local unit testing
    with patch("engine.api.app.insecure_local_api_enabled", return_value=True):
        yield TestClient(app)


def test_inspector_health_endpoint(client):
    """GET /api/inspector/health returns licensing clearance, zero VRAM notice, and model readiness."""
    res = client.get("/api/inspector/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "models" in data
    assert data["licensing"]["commercial_cleared"] is True
    assert "0 MB" in data["vram_usage"]


def test_inspect_image_endpoint(client, tmp_path):
    """POST /api/inspector/image evaluates image and returns canonical QualityDecision."""
    img_p = _create_synthetic_png(tmp_path / "test_portrait.png")

    res = client.post(
        "/api/inspector/image",
        json={
            "image_path": str(img_p),
            "character_count": 1,
            "prompt": "anime girl with smile",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "overall_score" in data
    assert data["status"] in ("PASS", "RETRY", "MANUAL_REVIEW")
    assert "clean" in data
    assert isinstance(data["defects"], list)


def test_inspect_video_endpoint(client, tmp_path):
    """POST /api/inspector/video evaluates video and returns canonical VideoQualityDecision."""
    vid_p = _create_synthetic_video(tmp_path / "test_clip.mp4")

    res = client.post(
        "/api/inspector/video",
        json={
            "video_path": str(vid_p),
            "sample_fps": 2.0,
            "max_frames": 100,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "overall_score" in data
    assert data["status"] in ("PASS", "RETRY", "MANUAL_REVIEW")
    assert data["total_frames"] == 24
    assert data["shots_detected"] >= 1


def test_repair_image_endpoint(client, tmp_path):
    """POST /api/inspector/repair/image invokes ImageRepairEngine and returns versioned repaired asset."""
    img_p = _create_synthetic_png(tmp_path / "defective_art.png")
    repaired_p = tmp_path / "repaired_art.png"
    _create_synthetic_png(repaired_p)

    mock_result = RepairResult(
        repaired_png=repaired_p.read_bytes(),
        revalidated_decision=QualityDecision(overall_score=94.0, status="PASS", clean=True, defects=[]),
        attempts=1,
        actions_taken=["inpaint_pass_1_extra_hands"],
        success=True,
        repaired_image_path=repaired_p,
        original_image_path=img_p,
        strategy_used="inpaint",
        original_score=60.0,
        final_score=94.0,
        score_improvement=34.0,
    )

    with patch.object(get_image_repair(), "repair_image", return_value=mock_result):
        res = client.post(
            "/api/inspector/repair/image",
            json={
                "image_path": str(img_p),
                "prompt": "refined portrait",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["score_improvement"] == 34.0
        assert data["revalidated_decision"]["status"] == "PASS"
        assert Path(data["repaired_image_path"]).is_file()


def test_repair_video_endpoint(client, tmp_path):
    """POST /api/inspector/repair/video invokes VideoRepairEngine and returns repaired video path and revalidation."""
    vid_p = _create_synthetic_video(tmp_path / "defective_video.mp4")
    repaired_p = tmp_path / "repaired_video.mp4"
    _create_synthetic_video(repaired_p)

    reval_dec = VideoQualityDecision(
        overall_score=92.0,
        status="PASS",
        clean=True,
        defects=[],
        duration_sec=1.0,
        total_frames=24,
    )
    mock_meta = {"actions_applied": ["optical_flow_interpolation_1_frames"], "score_improvement": 20.0}

    with patch.object(get_video_repair(), "repair_video", return_value=(repaired_p, reval_dec, mock_meta)):
        res = client.post(
            "/api/inspector/repair/video",
            json={
                "video_path": str(vid_p),
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["repaired_video_path"] == str(repaired_p)
        assert data["revalidated_decision"]["status"] == "PASS"
        assert "optical_flow_interpolation" in str(data["metadata"]["actions_applied"])


def test_job_manager_inspection_and_repair_operations(tmp_path):
    """Job Manager operation factories execute inspection and auto-repair with progress updates."""
    img_p = _create_synthetic_png(tmp_path / "job_target.png")
    repaired_p = tmp_path / "job_repaired.png"
    _create_synthetic_png(repaired_p)

    progress_log = []

    def mock_progress(pct: float, msg: str):
        progress_log.append((pct, msg))

    # 1. Inspection Operation
    inspect_op = _visual_inspection_operation(
        project_id="proj_01",
        job_input={"target_path": str(img_p), "is_video": False, "prompt": "knight"},
    )
    res_inspect = inspect_op(input_data={}, progress=mock_progress, is_cancelled=lambda: False)
    assert "decision" in res_inspect
    assert len(progress_log) >= 2

    # 2. Repair Operation
    progress_log.clear()
    mock_repair_res = RepairResult(
        repaired_png=repaired_p.read_bytes(),
        revalidated_decision=QualityDecision(overall_score=90.0, status="PASS", clean=True, defects=[]),
        attempts=1,
        actions_taken=["inpaint_pass_1"],
        success=True,
        repaired_image_path=repaired_p,
        original_image_path=img_p,
        score_improvement=25.0,
    )
    with patch.object(get_image_repair(), "repair_image", return_value=mock_repair_res):
        repair_op = _visual_repair_operation(
            project_id="proj_01",
            job_input={"target_path": str(img_p), "is_video": False, "prompt": "knight"},
        )
        res_repair = repair_op(input_data={}, progress=mock_progress, is_cancelled=lambda: False)
        assert res_repair["success"] is True
        assert res_repair["decision"]["status"] == "PASS"


def test_art_engine_generate_auto_repair_hook(tmp_path):
    """ArtEngine.generate with auto_repair=True catches defects and returns auto-corrected ArtImage."""
    raw_img = _create_synthetic_png(tmp_path / "raw.png").read_bytes()
    repaired_img = _create_synthetic_png(tmp_path / "repaired.png").read_bytes()

    engine = ArtEngine()
    engine.require_ready = MagicMock()
    mock_workflow = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 0}},
        "3": {"class_type": "SaveImage", "inputs": {"filename_prefix": ""}},
    }
    engine.registry.load = MagicMock(return_value=(mock_workflow, "sha123"))
    engine.registry.metadata = MagicMock(return_value={
        "patch_slots": {
            "prompt": {"node_id": "1", "input": "text", "class_type": "CLIPTextEncode"},
            "seed": {"node_id": "2", "input": "seed", "class_type": "KSampler"},
            "filename_prefix": {"node_id": "3", "input": "filename_prefix", "class_type": "SaveImage"},
        },
        "dimension_policy": {"mode": "exact", "min": 64, "max": 2048, "multiple_of": 8},
        "model_files": [],
    })
    engine.run = MagicMock(return_value=(raw_img, "prompt_99", {}))

    initial_defect_decision = QualityDecision(
        overall_score=50.0,
        status="RETRY",
        clean=False,
        defects=[DefectRecord(category="extra_hands", bbox=(0.2, 0.2, 0.4, 0.4))],
    )
    repaired_decision = QualityDecision(
        overall_score=95.0,
        status="PASS",
        clean=True,
        defects=[],
    )

    with patch("engine.inspector.image_inspector.ImageInspector.inspect", return_value=initial_defect_decision):
        with patch(
            "engine.inspector.repair.ImageRepairEngine.repair_image",
            return_value=RepairResult(
                repaired_png=repaired_img,
                revalidated_decision=repaired_decision,
                attempts=1,
                actions_taken=["inpaint_extra_hands"],
                success=True,
                score_improvement=45.0,
            ),
        ):
            art = engine.generate(
                prompt="girl in garden",
                width=120,
                height=120,
                auto_repair=True,
            )

            assert art.png == repaired_img
            assert art.decision.status == "PASS"
            assert art.decision.overall_score == 95.0
