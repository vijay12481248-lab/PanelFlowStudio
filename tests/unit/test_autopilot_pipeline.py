import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.database.models import NarrativeRecord, ProjectRecord, ScriptSegmentRecord, VideoScriptRecord
from engine.database.session import SessionLocal, init_db
from engine.pipeline.autopilot import AutoPilotRunner, get_autopilot_runner
from engine.story.models import NarrativeDocument, PanelObservationEntity


@pytest.fixture
def autopilot_project(tmp_path):
    init_db()
    project_id = str(uuid.uuid4())
    workspace = tmp_path / project_id
    workspace.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        project = ProjectRecord(
            id=project_id,
            title="AutoPilot Test Chronicle",
            source_type="local",
            workspace_path=str(workspace),
            source_metadata={"synopsis": "A test chronicle for end-to-end autonomous pipeline orchestration."},
            settings={},
            current_stage="NEW",
        )
        db.add(project)
        db.commit()

    yield project_id

    # Cleanup
    with SessionLocal() as db:
        p = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if p:
            db.delete(p)
            db.commit()


def test_autopilot_status_idle(autopilot_project):
    client = TestClient(app)
    response = client.get(f"/api/projects/{autopilot_project}/autopilot/status")
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == autopilot_project
    assert data["status"] == "IDLE"
    assert len(data["stages"]) == 9
    stage_ids = [s["id"] for s in data["stages"]]
    assert stage_ids == [
        "pages",
        "panels",
        "ocr",
        "story",
        "script",
        "audio",
        "motion",
        "render",
        "packaging",
    ]


def test_autopilot_cancel_when_idle(autopilot_project):
    client = TestClient(app)
    response = client.post(f"/api/projects/{autopilot_project}/autopilot/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["cancelled"] is True
    assert data["project_id"] == autopilot_project


@pytest.mark.asyncio
async def test_autopilot_runner_simulation(autopilot_project):
    runner = AutoPilotRunner(
        project_id=autopilot_project,
        options={
            "skip_existing_stages": True,
            "target_profile": "standard_1080p",
            "enable_thumbnails": False,
        },
    )

    # Patch stage executions to verify state machine flow and status progression
    with patch.object(runner, "_run_stage_pages", new_callable=AsyncMock) as m_pages, \
         patch.object(runner, "_run_stage_panels", new_callable=AsyncMock) as m_panels, \
         patch.object(runner, "_run_stage_ocr", new_callable=AsyncMock) as m_ocr, \
         patch.object(runner, "_run_stage_story", new_callable=AsyncMock) as m_story, \
         patch.object(runner, "_run_stage_script", new_callable=AsyncMock) as m_script, \
         patch.object(runner, "_run_stage_audio", new_callable=AsyncMock) as m_audio, \
         patch.object(runner, "_run_stage_motion", new_callable=AsyncMock) as m_motion, \
         patch.object(runner, "_run_stage_render", new_callable=AsyncMock) as m_render, \
         patch.object(runner, "_run_stage_packaging", new_callable=AsyncMock) as m_pkg, \
         patch.object(runner, "_persist_status"):

        await runner.execute()
        status = runner.snapshot()
        assert status.status == "COMPLETED"
        assert status.overall_progress == 1.0
        assert m_pages.called
        assert m_panels.called
        assert m_ocr.called
        assert m_story.called
        assert m_script.called
        assert m_audio.called
        assert m_motion.called
        assert m_render.called
        assert m_pkg.called
        assert len(status.logs) > 0


@pytest.mark.asyncio
async def test_autopilot_runner_cancellation(autopilot_project):
    runner = AutoPilotRunner(
        project_id=autopilot_project,
        options={"skip_existing_stages": False},
    )

    # Cancel before panels stage
    async def mock_panels(skip):
        runner.cancel()

    with patch.object(runner, "_run_stage_pages", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_panels", side_effect=mock_panels), \
         patch.object(runner, "_persist_status"):

        await runner.execute()
        assert runner.status == "CANCELLED"


@pytest.mark.asyncio
async def test_autopilot_audio_stage_synthesizes_and_attaches_bgm(autopilot_project):
    with SessionLocal() as db:
        p = db.query(ProjectRecord).filter(ProjectRecord.id == autopilot_project).first()
        workspace_path = p.workspace_path
        p.settings = {
            "story_editor_state": {
                "scenes": [
                    {"id": "scene_1", "start_time_sec": 0.0, "duration_sec": 4.0,
                     "layers": [{"source_panel_id": "panel_1"}]},
                    {"id": "scene_2", "start_time_sec": 4.0, "duration_sec": 4.0,
                     "layers": [{"source_panel_id": "panel_2"}]},
                ],
                "narration_clips": [
                    {"id": "c1", "text": "Maya reaches the gate.", "audio_url": None, "scene_id": "scene_1",
                     "status": "APPROVED", "review_status": "APPROVED"},
                    {"id": "c2", "text": "The gate opens.", "audio_url": None, "scene_id": "scene_2",
                     "status": "APPROVED", "review_status": "APPROVED"}
                ],
                "bgm_tracks": []
            }
        }
        narrative = NarrativeDocument(
            project_id=autopilot_project,
            observations=[
                PanelObservationEntity(panel_id="panel_1", sequence_global=1,
                                       visual_summary="Maya reaches the gate."),
                PanelObservationEntity(panel_id="panel_2", sequence_global=2,
                                       visual_summary="The gate opens."),
            ],
        )
        script = VideoScriptRecord(id="script_audio", project_id=autopilot_project, status="APPROVED")
        db.add(NarrativeRecord(id="narrative_audio", project_id=autopilot_project,
                               document=narrative.model_dump()))
        db.add(script)
        db.flush()
        db.add_all([
            ScriptSegmentRecord(
                id="segment_1", script_id=script.id, project_id=autopilot_project,
                scene_id="scene_1", sequence=1, type="NARRATOR", text="Maya reaches the gate.",
                source_evidence={"panel_ids": ["panel_1"]}, estimated_duration=1.0,
            ),
            ScriptSegmentRecord(
                id="segment_2", script_id=script.id, project_id=autopilot_project,
                scene_id="scene_2", sequence=2, type="NARRATOR", text="The gate opens.",
                source_evidence={"panel_ids": ["panel_2"]}, estimated_duration=1.0,
            ),
        ])
        db.commit()

    runner = AutoPilotRunner(project_id=autopilot_project, options={"skip_existing_stages": True})

    # Mock local synthesizer to avoid running actual model in unit test
    mock_wav = Path(workspace_path) / "audio" / "dialogue" / "mock_speech.wav"
    mock_wav.parent.mkdir(parents=True, exist_ok=True)
    import soundfile as sf
    import numpy as np
    sf.write(str(mock_wav), np.zeros(24000, dtype=np.float32), 24000)

    # Deliberately incorrect provider duration: timing must come from the WAV.
    batch_results = [{"id": cid, "success": True, "audio_path": str(mock_wav), "duration": 99}
                     for cid in ("c1", "c2")]
    with patch("engine.audio.synthesis.local_synthesizer.synthesize_batch", return_value=batch_results), \
         patch("engine.audio.service.audio_service.approve_audio"):
        await runner._run_stage_audio(skip_existing=True)

    stage = runner.get_stage("audio")
    assert stage.status == "COMPLETED"

    # Verify project settings were updated with narration clips and BGM
    with SessionLocal() as db:
        updated_p = db.query(ProjectRecord).filter(ProjectRecord.id == autopilot_project).first()
        se_state = updated_p.settings.get("story_editor_state", {})
        assert len(se_state.get("bgm_tracks", [])) > 0
        assert se_state["bgm_tracks"][0]["audio_url"] == "/assets/demo/crystal_resonance_bgm.mp3"
        assert len(se_state.get("narration_clips", [])) > 0
        assert se_state["narration_clips"][0]["status"] == "APPROVED"


        assert len(se_state["narration_clips"]) == 2
        assert se_state["narration_clips"][0]["duration_sec"] == 1.0
        assert se_state["scenes"][0]["duration_sec"] == pytest.approx(1.35)
        assert se_state["narration_clips"][1]["start_time_sec"] == pytest.approx(1.35)
