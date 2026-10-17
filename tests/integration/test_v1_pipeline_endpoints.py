import pytest
from pathlib import Path
import time
from PIL import Image
from fastapi.testclient import TestClient
from engine.api.app import app
from engine.config.settings import settings
from engine.database.session import init_db, SessionLocal
from engine.database.models import (
    Base,
    ProjectRecord,
    PageRecord,
    PanelRecord,
    VideoScriptRecord,
    ScriptSegmentRecord,
    AudioTimelineRecord,
    VisualTimelineRecord,
    RenderJobRecord,
)
from engine.acquisition.models.models import PipelineStage


@pytest.fixture(autouse=True)
def setup_api_env(tmp_path: Path, monkeypatch):
    from engine.database.session import engine
    test_ws = tmp_path / "workspaces"
    test_ws.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace_root", test_ws)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_system_provider_and_open_path(tmp_path: Path):
    client = TestClient(app)

    # 1. System providers
    resp = client.get("/api/system/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert "system_ready" in data
    provider_ids = [p["id"] for p in data["providers"]]
    assert "ffmpeg" in provider_ids
    assert "ffprobe" in provider_ids
    assert "ollama" in provider_ids
    assert "f5_tts" in provider_ids
    assert "ace_step" in provider_ids

    # 2. Open path
    sample_dir = tmp_path / "sample_folder"
    sample_dir.mkdir()
    sample_file = sample_dir / "test.txt"
    sample_file.write_text("hello", encoding="utf-8")

    # Path that doesn't exist
    resp_404 = client.post("/api/system/open-path", json={"path": str(tmp_path / "nonexistent")})
    assert resp_404.status_code == 404

    # Valid path (on headless/CI or test, should succeed or catch cleanly)
    resp_open = client.post("/api/system/open-path", json={"path": str(sample_dir)})
    assert resp_open.status_code in (200, 500)


def test_audio_motion_render_api_endpoints(tmp_path: Path):
    client = TestClient(app)

    # Setup project with approved script and source visual
    project_id = "test_e2e_proj"
    workspace = tmp_path / "workspaces" / project_id
    workspace.mkdir(parents=True, exist_ok=True)
    pages_dir = workspace / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (1000, 1000), color=(100, 150, 200))
    img_path = pages_dir / "page_01.jpg"
    img.save(img_path)

    with SessionLocal() as db:
        proj = ProjectRecord(
            id=project_id,
            title="E2E Integration Comic",
            source_type="LOCAL_FOLDER",
            rights_status="PUBLIC_DOMAIN",
            workspace_path=str(workspace),
            current_stage=PipelineStage.SCRIPT_APPROVED.value,
        )
        page = PageRecord(
            id="page_1",
            project_id=project_id,
            sequence=1,
            filename="page_01.jpg",
            width=1000,
            height=1000,
            byte_size=1024,
            sha256="abc",
            status="READY",
        )
        panel = PanelRecord(
            id="panel_1",
            project_id=project_id,
            page_id="page_1",
            sequence=1,
            page_sequence=1,
            x=0,
            y=0,
            width=1000,
            height=1000,
            crop_filename="page_01.jpg",
            status="APPROVED",
        )
        script = VideoScriptRecord(
            id="script_1",
            project_id=project_id,
            adaptation_profile="FAITHFUL",
            estimated_duration=4.5,
            status="APPROVED",
        )
        seg = ScriptSegmentRecord(
            id="seg_1",
            script_id="script_1",
            project_id=project_id,
            scene_id="scene_1",
            sequence=1,
            speaker_character_id="valerian",
            text="The shattered prism resonates once more.",
            emotion="AWE",
            intensity=0.8,
            faithfulness_status="SUPPORTED",
            estimated_duration=3.0,
        )
        db.add_all([proj, page, panel, script, seg])
        db.commit()

    # --- 1. Audio Timeline GET (initially 404) ---
    at_resp = client.get(f"/api/projects/{project_id}/audio/timeline")
    assert at_resp.status_code == 404

    # --- 2. Audio Generate ---
    gen_resp = client.post(
        f"/api/projects/{project_id}/audio/generate",
        json={"voice_casting": {"valerian": "marcus_male_deep"}},
    )
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    assert gen_data["status"] == "DRAFT"
    assert gen_data["total_duration"] > 0
    assert len(gen_data["timeline"]["intervals"]) >= 1

    # Audio Timeline GET should now be 200
    at_resp2 = client.get(f"/api/projects/{project_id}/audio/timeline")
    assert at_resp2.status_code == 200

    # Stream audio file endpoint
    iv = gen_data["timeline"]["intervals"][0]
    wav_file = iv["audio_file_uri"]
    stream_resp = client.get(f"/api/projects/{project_id}/audio/file", params={"path": wav_file})
    assert stream_resp.status_code == 200
    assert stream_resp.headers["content-type"] in ("audio/wav", "audio/x-wav")

    # Selective regenerate segment
    regen_resp = client.post(
        f"/api/projects/{project_id}/audio/regenerate-segment",
        json={"segment_id": "seg_1"},
    )
    assert regen_resp.status_code == 200
    assert regen_resp.json()["status"] == "REGENERATED"

    # Approve audio
    appr_audio_resp = client.post(f"/api/projects/{project_id}/audio/approve")
    assert appr_audio_resp.status_code == 200
    assert appr_audio_resp.json()["approved"] is True

    # --- 3. Motion Timeline GET (initially 404) ---
    mt_resp = client.get(f"/api/projects/{project_id}/motion/timeline")
    assert mt_resp.status_code == 404

    # Plan Motion Timeline
    plan_resp = client.post(
        f"/api/projects/{project_id}/motion/plan",
        json={"style_preset": "cinematic"},
    )
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert plan_data["status"] == "DRAFT"
    assert plan_data["total_shots"] >= 1

    # Overrides
    overrides_resp = client.post(
        f"/api/projects/{project_id}/motion/overrides",
        json={"overrides": {"shot_overrides": {}}},
    )
    assert overrides_resp.status_code == 200

    # Approve Motion
    appr_motion_resp = client.post(f"/api/projects/{project_id}/motion/approve")
    assert appr_motion_resp.status_code == 200
    assert appr_motion_resp.json()["approved"] is True

    # --- 4. Render Jobs ---
    render_start_resp = client.post(
        f"/api/projects/{project_id}/render/jobs",
        json={"profile_name": "draft_720p", "is_draft": True},
    )
    assert render_start_resp.status_code == 200
    render_job = render_start_resp.json()
    render_id = render_job["render_id"]
    assert render_job["status"] in ("QUEUED", "PREPARING", "COMPOSING", "ENCODING", "COMPLETE")

    # List renders
    list_renders_resp = client.get(f"/api/projects/{project_id}/render/jobs")
    assert list_renders_resp.status_code == 200
    assert len(list_renders_resp.json()) >= 1

    # Query specific render job
    get_render_resp = client.get(f"/api/projects/{project_id}/render/jobs/{render_id}")
    assert get_render_resp.status_code == 200
    assert get_render_resp.json()["render_id"] == render_id

    # Cancel render (if still active or completes gracefully)
    cancel_resp = client.post(f"/api/projects/{project_id}/render/jobs/{render_id}/cancel")
    assert cancel_resp.status_code == 200
