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
@pytest.mark.parametrize("concurrent_edit", [False, True])
async def test_autopilot_audio_stage_synthesizes_and_attaches_bgm(autopilot_project, concurrent_edit):
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
    def generate(*args, **kwargs):
        if concurrent_edit:
            with SessionLocal() as editing_db:
                edited = editing_db.get(ProjectRecord, autopilot_project)
                settings = json.loads(json.dumps(edited.settings))
                settings["story_editor_state"]["scenes"][0]["duration_sec"] = 7.0
                edited.settings = settings
                editing_db.commit()
        return batch_results
    with patch("engine.audio.synthesis.local_synthesizer.synthesize_batch", side_effect=generate), \
         patch("engine.audio.service.audio_service.approve_audio"):
        if concurrent_edit:
            with pytest.raises(ValueError, match="timeline changed during voice generation"):
                await runner._run_stage_audio(skip_existing=True)
            with SessionLocal() as checking_db:
                saved = checking_db.get(ProjectRecord, autopilot_project).settings["story_editor_state"]
                assert saved["scenes"][0]["duration_sec"] == 7.0
                assert saved["narration_clips"][0]["audio_url"] is None
            return
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
        assert se_state["scenes"][0]["duration_sec"] >= 1.0
        assert se_state["narration_clips"][1]["start_time_sec"] >= 1.0

@pytest.mark.asyncio
async def test_autopilot_stage_timeout_diagnostics(autopilot_project):
    import asyncio
    runner = AutoPilotRunner(
        project_id=autopilot_project,
        options={
            "stage_timeouts": {"panels": 0.05},
        },
    )

    async def slow_panels(skip):
        await asyncio.sleep(0.5)

    with patch.object(runner, "_run_stage_pages", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_panels", side_effect=slow_panels), \
         patch.object(runner, "_persist_status"):

        await runner.execute()
        assert runner.status == "FAILED"
        assert runner.error_details is not None
        assert runner.error_details.stage_id == "panels"
        assert runner.error_details.category == "TIMEOUT"
        assert len(runner.error_details.troubleshooting) > 0
        assert runner.get_stage("panels").status == "FAILED"


@pytest.mark.asyncio
async def test_autopilot_stage_error_diagnostics(autopilot_project):
    runner = AutoPilotRunner(project_id=autopilot_project)

    async def fail_ocr(skip):
        raise RuntimeError("EasyOCR model weights missing from disk")

    with patch.object(runner, "_run_stage_pages", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_panels", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_ocr", side_effect=fail_ocr), \
         patch.object(runner, "_persist_status"):

        await runner.execute()
        assert runner.status == "FAILED"
        assert runner.error_details is not None
        assert runner.error_details.stage_id == "ocr"
        assert runner.error_details.category == "OCR_ERROR"
        assert "EasyOCR model weights missing" in runner.error_details.message
        assert len(runner.error_details.troubleshooting) > 0
        assert runner.get_stage("ocr").status == "FAILED"


@pytest.mark.asyncio
async def test_autopilot_render_stage_stall_watchdog(autopilot_project):
    runner = AutoPilotRunner(
        project_id=autopilot_project,
        options={
            "render_stall_timeout_sec": 0.05,
            "stage_timeouts": {"render": 10.0},
        },
    )

    fake_job_dict = {"render_id": "job-test-123", "output_path": "/fake/test.mp4"}
    stagnant_info = {
        "status": "RUNNING",
        "progress": 0.1,
        "frames_done": 10,
        "frames_total": 100,
    }

    with patch("engine.render.service.render_service.create_and_start_render_job", return_value=fake_job_dict), \
         patch("engine.render.service.render_service.get_render_job", return_value=stagnant_info), \
         patch.object(runner, "_run_stage_pages", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_panels", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_ocr", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_story", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_script", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_audio", new_callable=AsyncMock), \
         patch.object(runner, "_run_stage_motion", new_callable=AsyncMock), \
         patch.object(runner, "_persist_status"):

        await runner.execute()
        assert runner.status == "FAILED"
        assert runner.error_details is not None
        assert runner.error_details.stage_id == "render"
        assert runner.error_details.category == "TIMEOUT"
        assert "stalled" in runner.error_details.message

@pytest.mark.asyncio
async def test_autopilot_does_not_fall_back_to_mock(autopilot_project):
    runner = AutoPilotRunner(autopilot_project, {})
    with patch('engine.llm.registry.llm_registry.get_active_provider', new_callable=AsyncMock, side_effect=RuntimeError('Model offline')), patch('engine.story.service.story_service.analyze_story_project') as analyze:
        with pytest.raises(RuntimeError, match='Model offline'):
            await runner._run_stage_story(False)
        analyze.assert_not_called()


@pytest.mark.asyncio
async def test_autopilot_rejects_saved_mock_story(autopilot_project):
    from types import SimpleNamespace
    with SessionLocal() as db:
        project = db.get(ProjectRecord, autopilot_project)
        project.settings = {'story_editor_state': {'scenes': [{'id': 'saved-scene'}]}}
        db.commit()
    runner = AutoPilotRunner(autopilot_project, {})
    with patch('engine.story.service.story_service.get_narrative', return_value=SimpleNamespace(analysis_metadata={'provider': 'mock_llm'})), patch('engine.story.service.story_service.confirm_story') as confirm:
        with pytest.raises(ValueError, match='mock provider'):
            await runner._run_stage_story(True)
        confirm.assert_not_called()


def test_legacy_script_enum_labels():
    from engine.story.models import EmotionType, MotionIntent
    assert EmotionType('MYSTERIOUS') == EmotionType.TENSE
    assert EmotionType('SUSPENSEFUL') == EmotionType.TENSE
    assert EmotionType('SERIOUS') == EmotionType.NEUTRAL
    assert MotionIntent('SLOW_PAN') == MotionIntent.PAN
    with pytest.raises(ValueError):
        MotionIntent('INVALID_MOTION')
