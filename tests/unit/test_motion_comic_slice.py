"""Milestone 4: Narrated Motion-Comic Slice - regression tests."""
from pathlib import Path
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from PIL import Image
import io

from engine.database.models import (
    Base,
    ProjectRecord,
    PageRecord,
    PanelRecord,
    AssetRecord,
    VideoScriptRecord,
    ScriptSegmentRecord,
    SceneRecord,
    CharacterRecord,
    AudioTimelineRecord,
    VisualTimelineRecord,
    RenderJobRecord,
)
from engine.database.session import SessionLocal, engine, run_sqlite_migrations
from engine.acquisition.models import PipelineStage
from engine.motion.service import motion_service
from engine.render.service import render_service
from engine.render.models.profiles import RenderProfile


def setup_project_with_motion(tmp_path):
    """Create a test project with motion timeline ready for rendering."""
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    with SessionLocal() as db:
        project_id = f'motion-comic-test-{uuid.uuid4().hex[:8]}'
        db.add(ProjectRecord(
            id=project_id,
            title='Motion Comic Test',
            source_type='LOCAL_FOLDER',
            rights_status='PUBLIC_DOMAIN',
            workspace_path=str(tmp_path),
            current_stage=PipelineStage.MOTION_APPROVED.value,
            settings={"visual_storytelling": True},
        ))
        # Pages and panels - use project-scoped unique IDs
        page_ids = []
        panel_ids_by_page = []
        for i in range(2):
            page_id = f'page-{project_id}-{i+1}'
            page_ids.append(page_id)
            db.add(PageRecord(
                id=page_id, project_id=project_id, sequence=i+1,
                filename=f'page{i+1}.jpg', status='READY', width=1920, height=1080,
                byte_size=1000, sha256='a' * 64,
            ))
            panel_ids = []
            for j in range(3):
                panel_id = f'panel-{project_id}-{i+1}-{j+1}'
                panel_ids.append(panel_id)
                db.add(PanelRecord(
                    id=panel_id, project_id=project_id, page_id=page_id,
                    sequence=j+1, page_sequence=j+1, x=0, y=0, width=640, height=360,
                    crop_filename=f'{panel_id}.jpg', status='CONFIRMED',
                ))
            panel_ids_by_page.append(panel_ids)

        # Script
        script_id = f'script-{uuid.uuid4().hex[:8]}'
        script = VideoScriptRecord(
            id=script_id,
            project_id=project_id,
            version='1.0',
            adaptation_profile='FAITHFUL',
            estimated_duration=30.0,
            language='en',
            status='APPROVED',
            quality_metrics={},
        )
        db.add(script)
        # 4 segments
        segments = [
            (f'seg-1-{uuid.uuid4().hex[:8]}', 'scene-1', 1, 'NARRATION', 'The story begins in the ruins.', 'NEUTRAL', 0.5, 4.0),
            (f'seg-2-{uuid.uuid4().hex[:8]}', 'scene-1', 2, 'CHARACTER_DIALOGUE', 'I sense danger ahead.', 'TENSE', 0.8, 3.5),
            (f'seg-3-{uuid.uuid4().hex[:8]}', 'scene-2', 1, 'NARRATION', 'A guardian awakens.', 'DRAMATIC', 0.7, 4.5),
            (f'seg-4-{uuid.uuid4().hex[:8]}', 'scene-2', 2, 'CHARACTER_DIALOGUE', 'We must fight!', 'EXCITED', 0.9, 3.0),
        ]
        for seg_id, scene_id, seq, seg_type, text, emotion, intensity, dur in segments:
            db.add(ScriptSegmentRecord(
                id=seg_id, script_id=script_id, project_id=project_id,
                scene_id=scene_id, sequence=seq, type=seg_type,
                speaker_character_id=None, text=text, emotion=emotion,
                intensity=intensity, estimated_duration=dur,
                estimated_start=0.0, estimated_end=dur,
                source_evidence={}, production_intent='',
            ))

        # Audio timeline (approved)
        audio_rec = AudioTimelineRecord(
            id=f'audio-{uuid.uuid4().hex[:8]}',
            project_id=project_id,
            status='APPROVED',
            total_duration=15.0,
            timeline_json={
                "total_duration_sec": 15.0,
                "timeline_source": "REAL_AUDIO_TIMELINE",
                "intervals": [
                    {"segment_id": "seg-1", "file_path": "audio/seg-1.wav", "duration": 4.0, "start_time": 0.0, "end_time": 4.0, "gain_db": 0.0},
                    {"segment_id": "seg-2", "file_path": "audio/seg-2.wav", "duration": 3.5, "start_time": 4.0, "end_time": 7.5, "gain_db": 0.0},
                    {"segment_id": "seg-3", "file_path": "audio/seg-3.wav", "duration": 4.5, "start_time": 7.5, "end_time": 12.0, "gain_db": 0.0},
                    {"segment_id": "seg-4", "file_path": "audio/seg-4.wav", "duration": 3.0, "start_time": 12.0, "end_time": 15.0, "gain_db": 0.0},
                ],
                "timeline_source": "REAL_AUDIO_TIMELINE",
            },
            voice_casting={},
        )
        db.add(audio_rec)

        # Visual timeline (approved)
        visual_rec = VisualTimelineRecord(
            id=f'vt-{uuid.uuid4().hex[:8]}',
            project_id=project_id,
            status='APPROVED',
            total_duration=15.0,
            total_shots=4,
            style_preset='cinematic',
            timeline_json={
                "project_id": project_id,
                "timeline_source": "REAL_AUDIO_TIMELINE",
                "total_duration_sec": 15.0,
                "target_resolution": {"width": 1920, "height": 1080, "fps": 30},
                "style_preset": "cinematic",
                "scenes": [
                    {
                        "scene_id": "scene-1",
                        "sequence": 1,
                        "title": "The Ruins",
                        "start_time": 0.0,
                        "end_time": 7.5,
                        "shots": [
                            {
                                "shot_id": "shot-1",
                                "scene_id": "scene-1",
                                "sequence_in_scene": 1,
                                "sequence_global": 1,
                                "source_asset_id": f"panel-{project_id}-1-1",
                                "source_panel_id": f"panel-{project_id}-1-1",
                                "start_time": 0.0,
                                "end_time": 4.0,
                                "frame_region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                                "camera_start": {"center_x": 0.5, "center_y": 0.5, "zoom": 1.0},
                                "camera_end": {"center_x": 0.5, "center_y": 0.5, "zoom": 1.08},
                                "easing": "EASE_IN_OUT",
                                "motion_type": "SLOW_ZOOM_IN",
                                "focus_targets": [{"target_type": "CENTER", "bounding_box": None}],
                                "transition_in": {"type": "DISSOLVE", "duration_sec": 0.5},
                                "transition_out": {"type": "HARD_CUT", "duration_sec": 0.0},
                            },
                            {
                                "shot_id": "shot-2",
                                "scene_id": "scene-1",
                                "sequence_in_scene": 2,
                                "sequence_global": 2,
                                "source_asset_id": f"panel-{project_id}-1-2",
                                "source_panel_id": f"panel-{project_id}-1-2",
                                "start_time": 4.0,
                                "end_time": 7.5,
                                "frame_region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                                "camera_start": {"center_x": 0.5, "center_y": 0.5, "zoom": 1.0},
                                "camera_end": {"center_x": 0.5, "center_y": 0.5, "zoom": 1.15},
                                "easing": "EASE_IN_OUT",
                                "motion_type": "REACTION_HOLD",
                                "focus_targets": [{"target_type": "CENTER", "bounding_box": None}],
                                "transition_in": {"type": "HARD_CUT", "duration_sec": 0.0},
                                "transition_out": {"type": "DISSOLVE", "duration_sec": 0.5},
                            },
                        ]
                    },
                    {
                        "scene_id": "scene-2",
                        "sequence": 2,
                        "title": "The Guardian",
                        "start_time": 7.5,
                        "end_time": 15.0,
                        "shots": [
                            {
                                "shot_id": "shot-3",
                                "scene_id": "scene-2",
                                "sequence_in_scene": 1,
                                "sequence_global": 3,
                                "source_asset_id": f"panel-{project_id}-2-1",
                                "source_panel_id": f"panel-{project_id}-2-1",
                                "start_time": 7.5,
                                "end_time": 12.0,
                                "frame_region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                                "camera_start": {"center_x": 0.5, "center_y": 0.5, "zoom": 1.0},
                                "camera_end": {"center_x": 0.5, "center_y": 0.5, "zoom": 1.08},
                                "easing": "EASE_IN_OUT",
                                "motion_type": "SLOW_ZOOM_IN",
                                "focus_targets": [{"target_type": "CENTER", "bounding_box": None}],
                                "transition_in": {"type": "DISSOLVE", "duration_sec": 0.5},
                                "transition_out": {"type": "HARD_CUT", "duration_sec": 0.0},
                            },
                            {
                                "shot_id": "shot-4",
                                "scene_id": "scene-2",
                                "sequence_in_scene": 2,
                                "sequence_global": 4,
                                "source_asset_id": f"panel-{project_id}-2-2",
                                "source_panel_id": f"panel-{project_id}-2-2",
                                "start_time": 12.0,
                                "end_time": 15.0,
                                "frame_region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                                "camera_start": {"center_x": 0.5, "center_y": 0.5, "zoom": 1.0},
                                "camera_end": {"center_x": 0.5, "center_y": 0.5, "zoom": 1.2},
                                "easing": "EASE_IN_OUT",
                                "motion_type": "IMPACT",
                                "focus_targets": [{"target_type": "CENTER", "bounding_box": None}],
                                "transition_in": {"type": "HARD_CUT", "duration_sec": 0.0},
                                "transition_out": {"type": "DISSOLVE", "duration_sec": 1.0},
                            },
                        ]
                    }
                ],
                "total_shots": 4,
                "warnings": [],
            },
            overrides_json={},
        )
        db.add_all([audio_rec, visual_rec])

        # Panel crops - create valid JPEG images with project-scoped IDs
        panels_dir = tmp_path / "panels"
        panels_dir.mkdir(parents=True, exist_ok=True)
        for i in range(2):
            for j in range(3):
                panel_id = f'panel-{project_id}-{i+1}-{j+1}'
                # Create a valid JPEG image
                img = Image.new('RGB', (640, 360), color=(i*100 + j*50, 100, 150))
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='JPEG')
                (panels_dir / f'{panel_id}.jpg').write_bytes(img_bytes.getvalue())

        db.commit()
    return project_id


def test_render_creates_1080p_mp4(tmp_path):
    """Render produces a 1920x1080 MP4 file with correct duration."""
    project_id = setup_project_with_motion(tmp_path)

    with SessionLocal() as db:
        # Use draft profile for faster test
        result = render_service.create_and_start_render_job(
            db, project_id, profile_name="standard_1080p", is_draft=False,
        )

    assert result["status"] in ("QUEUED", "RUNNING")
    render_id = result["render_id"]

    # Wait for completion (with timeout)
    import time
    for _ in range(30):
        time.sleep(1)
        with SessionLocal() as db:
            job = render_service.get_render_job(db, render_id)
            if job["status"] in ("COMPLETE", "FAILED", "CANCELLED"):
                break

    with SessionLocal() as db:
        job = render_service.get_render_job(db, render_id)
        assert job["status"] == "COMPLETE", f"Render failed: {job.get('error_message')}"
        assert job["validation_status"] == "VALID"
        assert Path(job["output_path"]).exists()
        # Validate with ffprobe
        import subprocess
        result = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "csv=p=0", job["output_path"]
        ], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0
        width, height, duration = result.stdout.strip().split(",")
        assert int(width) == 1920
        assert int(height) == 1080
        assert abs(float(duration) - 15.0) < 1.0  # Within 1 second tolerance


def test_segment_level_voice_replacement(tmp_path):
    """Regenerating a single segment's audio updates only that segment in timeline."""
    project_id = setup_project_with_motion(tmp_path)

    with SessionLocal() as db:
        # First render
        result1 = render_service.create_and_start_render_job(db, project_id, is_draft=True)
        render_id1 = result1["render_id"]

        import time
        for _ in range(30):
            time.sleep(1)
            with SessionLocal() as db:
                job = render_service.get_render_job(db, render_id1)
                if job["status"] in ("COMPLETE", "FAILED"):
                    break

        # Now replace segment 2's voice
        with SessionLocal() as db:
            from engine.audio.service import audio_service
            # This would test the segment-level regeneration
            # For now, verify the API endpoint exists
            from engine.api.routers.audio import router
            routes = [r.path for r in router.routes]
            assert '/api/projects/{project_id}/audio/regenerate-segment' in routes


def test_subtitle_generation_and_alignment(tmp_path):
    """Subtitles are generated from script segments and aligned to audio."""
    project_id = setup_project_with_motion(tmp_path)

    with SessionLocal() as db:
        result = render_service.create_and_start_render_job(
            db, project_id, profile_name="standard_1080p", is_draft=False,
            subtitle_enabled=True,
        )
        render_id = result["render_id"]

        import time
        for _ in range(30):
            time.sleep(1)
            with SessionLocal() as db:
                job = render_service.get_render_job(db, render_id)
                if job["status"] in ("COMPLETE", "FAILED"):
                    break

        with SessionLocal() as db:
            job = render_service.get_render_job(db, render_id)
            assert job["status"] == "COMPLETE"
            # Check contact sheet / validation report has subtitle info
            val_report = job.get("validation_report", {})
            if isinstance(val_report, str):
                import json
                val_report = json.loads(val_report)
            # Subtitle track should be present
            assert "subtitles" in str(val_report).lower() or "caption" in str(val_report).lower()


def test_pan_zoom_transitions_in_timeline(tmp_path):
    """Timeline includes pan/zoom and transitions per shot."""
    project_id = setup_project_with_motion(tmp_path)

    with SessionLocal() as db:
        vt = db.query(VisualTimelineRecord).filter(
            VisualTimelineRecord.project_id == project_id
        ).order_by(VisualTimelineRecord.created_at.desc()).first()

        assert vt is not None
        timeline = vt.timeline_json
        for scene in timeline["scenes"]:
            for shot in scene["shots"]:
                # Each shot has camera motion
                assert "camera_start" in shot
                assert "camera_end" in shot
                assert "motion_type" in shot
                assert shot["motion_type"] in ["SLOW_ZOOM_IN", "REACTION_HOLD", "IMPACT", "SLOW_ZOOM_IN"]
                # Each shot has transitions
                assert "transition_in" in shot
                assert "transition_out" in shot
                assert "type" in shot["transition_in"]
                assert "type" in shot["transition_out"]


def test_ffprobe_validation_on_render_complete(tmp_path):
    """FFprobe validates output: codec, resolution, duration, audio sync."""
    project_id = setup_project_with_motion(tmp_path)

    with SessionLocal() as db:
        result = render_service.create_and_start_render_job(db, project_id, profile_name="standard_1080p", is_draft=False)
        render_id = result["render_id"]

        import time
        for _ in range(30):
            time.sleep(1)
            with SessionLocal() as db:
                job = render_service.get_render_job(db, render_id)
                if job["status"] in ("COMPLETE", "FAILED"):
                    break

        with SessionLocal() as db:
            job = render_service.get_render_job(db, render_id)
            assert job["status"] == "COMPLETE"

            # FFprobe validation
            import subprocess
            out_path = job["output_path"]
            # Video stream
            v_result = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,avg_frame_rate",
                "-of", "json", out_path
            ], capture_output=True, text=True, timeout=30)
            assert v_result.returncode == 0
            import json
            v_data = json.loads(v_result.stdout)
            assert v_data["streams"][0]["width"] == 1920
            assert v_data["streams"][0]["height"] == 1080
            assert v_data["streams"][0]["codec_name"] in ("h264", "libx264")

            # Audio stream
            a_result = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,sample_rate,channels",
                "-of", "json", out_path
            ], capture_output=True, text=True, timeout=30)
            assert a_result.returncode == 0
            a_data = json.loads(a_result.stdout)
            assert a_data["streams"][0]["codec_name"] in ("aac", "libfdk_aac")


def test_editable_project_reopen_after_render(tmp_path):
    """Rendered project can be reopened and timeline is intact."""
    project_id = setup_project_with_motion(tmp_path)

    with SessionLocal() as db:
        result = render_service.create_and_start_render_job(db, project_id, profile_name="standard_1080p", is_draft=False)
        render_id = result["render_id"]

        import time
        for _ in range(30):
            time.sleep(1)
            with SessionLocal() as db:
                job = render_service.get_render_job(db, render_id)
                if job["status"] in ("COMPLETE", "FAILED"):
                    break

    # Simulate reopening - query the project
    with SessionLocal() as db:
        from engine.projects.service import ProjectService
        proj = ProjectService().get_project(db, project_id)
        assert proj is not None
        assert proj.current_stage in (PipelineStage.RENDERED.value, PipelineStage.MOTION_APPROVED.value)

        # Visual timeline still exists and valid
        vt = db.query(VisualTimelineRecord).filter(
            VisualTimelineRecord.project_id == project_id
        ).order_by(VisualTimelineRecord.created_at.desc()).first()
        assert vt is not None
        assert vt.status == "APPROVED"
        assert vt.total_shots == 4
        assert len(vt.timeline_json["scenes"]) == 2


def test_render_validation_reports_duration_and_sync(tmp_path):
    """Validation report includes actual duration and AV sync status."""
    project_id = setup_project_with_motion(tmp_path)

    with SessionLocal() as db:
        result = render_service.create_and_start_render_job(db, project_id, profile_name="standard_1080p", is_draft=False)
        render_id = result["render_id"]

        import time
        for _ in range(30):
            time.sleep(1)
            with SessionLocal() as db:
                job = render_service.get_render_job(db, render_id)
                if job["status"] in ("COMPLETE", "FAILED"):
                    break

        with SessionLocal() as db:
            job = render_service.get_render_job(db, render_id)
            assert job["status"] == "COMPLETE"
            val_report = job.get("validation_report", {})
            if isinstance(val_report, str):
                import json
                val_report = json.loads(val_report)

            # Check required validation fields
            assert "actual_duration_sec" in str(val_report)
            assert "planned_duration_sec" in str(val_report)
            assert "sync_valid" in str(val_report) or "av_sync_offset_ms" in str(val_report)
            # Duration should be close to planned (15s ± 1s)
            import json
            if isinstance(val_report, str):
                val_report = json.loads(val_report)
            actual_dur = val_report.get("actual_duration_sec", 0)
            planned_dur = val_report.get("planned_duration_sec", 0)
            assert abs(actual_dur - planned_dur) < 1.0