import pytest
import json
from unittest.mock import MagicMock
from pathlib import Path

from engine.story.alignment import (
    NarrationFrameAlignmentService,
    CameraMotionConfig,
    StoryboardPanelRef,
    StoryboardSegment,
    StoryboardDocument,
    StoryboardSegmentUpdate,
)
from engine.database.models import (
    ProjectRecord,
    PanelRecord,
    VideoScriptRecord,
    ScriptSegmentRecord,
    AudioTimelineRecord,
)


def test_camera_motion_determination():
    """Verify camera movement heuristics based on role, emotion, and intensity."""
    svc = NarrationFrameAlignmentService()

    # Reaction close-up
    m1 = svc._determine_camera_motion("REACTION_CLOSEUP", "NEUTRAL", 0.5)
    assert m1.type == "REACTION_CLOSEUP"

    # High intensity reaction
    m2 = svc._determine_camera_motion("NARRATION_FOCUS", "NEUTRAL", 0.85)
    assert m2.type == "REACTION_CLOSEUP"

    # Action / anger impact
    m3 = svc._determine_camera_motion("ACTION", "ANGRY", 0.7)
    assert m3.type == "IMPACT"
    assert m3.easing == "EASE_OUT"

    # Establishing shot
    m4 = svc._determine_camera_motion("ESTABLISHING", "CALM", 0.3)
    assert m4.type == "SLOW_PUSH"
    assert m4.easing == "EASE_IN_OUT"


def test_panel_scoring():
    """Verify semantic scoring favors evidence panels, wide establishing shots, and emotional closeups."""
    svc = NarrationFrameAlignmentService()

    panel_wide = MagicMock(spec=PanelRecord)
    panel_wide.id = "p_wide"
    panel_wide.width = 1920
    panel_wide.height = 1080
    panel_wide.panel_type = "STANDARD"

    panel_portrait = MagicMock(spec=PanelRecord)
    panel_portrait.id = "p_portrait"
    panel_portrait.width = 800
    panel_portrait.height = 1200
    panel_portrait.panel_type = "STANDARD"

    # Segment with evidence pointing to p_portrait
    segment = MagicMock(spec=ScriptSegmentRecord)
    segment.intensity = 0.8
    segment.source_evidence = {"panel_ids": ["p_portrait"]}

    # Score wide panel at start (first) vs later
    score_first = svc._score_panel(panel_wide, segment, is_first=True, is_last=False)
    score_later = svc._score_panel(panel_wide, segment, is_first=False, is_last=False)
    assert score_first > score_later

    # Score portrait panel linked to evidence
    score_portrait = svc._score_panel(panel_portrait, segment, is_first=False, is_last=False)
    assert score_portrait > 4.0  # Base (1.0) + evidence (3.0) + intensity/portrait (1.5)


def test_align_script_to_frames_audio_locking(tmp_path):
    """Verify that shot duration locks directly to authoritative neural audio timeline length."""
    svc = NarrationFrameAlignmentService()

    project = MagicMock(spec=ProjectRecord)
    project.id = "proj_test_01"
    project.workspace_path = str(tmp_path)

    panel1 = MagicMock(spec=PanelRecord)
    panel1.id = "pan_01"
    panel1.sequence = 0
    panel1.reading_order = 0
    panel1.width = 1200
    panel1.height = 800
    panel1.x = 0
    panel1.y = 0
    panel1.normalized_x = 0.0
    panel1.normalized_y = 0.0
    panel1.normalized_width = 1.0
    panel1.normalized_height = 0.5
    panel1.crop_filename = "crop_01.jpg"
    panel1.panel_type = "STANDARD"

    panel2 = MagicMock(spec=PanelRecord)
    panel2.id = "pan_02"
    panel2.sequence = 1
    panel2.reading_order = 1
    panel2.width = 1200
    panel2.height = 800
    panel2.x = 0
    panel2.y = 800
    panel2.normalized_x = 0.0
    panel2.normalized_y = 0.5
    panel2.normalized_width = 1.0
    panel2.normalized_height = 0.5
    panel2.crop_filename = "crop_02.jpg"
    panel2.panel_type = "STANDARD"

    script = MagicMock(spec=VideoScriptRecord)
    script.id = "script_01"

    segment1 = MagicMock(spec=ScriptSegmentRecord)
    segment1.id = "seg_01"
    segment1.scene_id = "scene_01"
    segment1.sequence = 0
    segment1.text = "In the heart of the sacred mountains, an ancient power stirs once more."
    segment1.emotion = "TENSE"
    segment1.intensity = 0.75
    segment1.source_evidence = {"panel_ids": ["pan_01", "pan_02"]}
    segment1.manual_override = False
    segment1.estimated_duration = 3.0
    segment1.music_intent = "TENSE"
    segment1.sfx_intent = "NONE"

    # Authoritative audio timeline with measured audio duration (6.2 seconds)
    audio_record = MagicMock(spec=AudioTimelineRecord)
    audio_record.duration = 6.2
    audio_record.timeline_json = {
        "clips": [
            {
                "segment_id": "seg_01",
                "duration": 6.2,
                "file_path": "/workspace/audio/seg_01.wav",
            }
        ]
    }

    db = MagicMock()
    def mock_query(model):
        m = MagicMock()
        if model == ProjectRecord:
            m.filter.return_value.first.return_value = project
        elif model == VideoScriptRecord:
            m.filter.return_value.first.return_value = script
            m.filter.return_value.filter.return_value.first.return_value = script
            m.filter.return_value.order_by.return_value.first.return_value = script
        elif model == AudioTimelineRecord:
            m.filter.return_value.order_by.return_value.first.return_value = audio_record
        elif model == ScriptSegmentRecord:
            m.filter.return_value.order_by.return_value.all.return_value = [segment1]
        elif model == PanelRecord:
            m.filter.return_value.order_by.return_value.all.return_value = [panel1, panel2]
        return m
    db.query.side_effect = mock_query

    doc = svc.align_script_to_frames(db, "proj_test_01", "script_01")

    assert doc.project_id == "proj_test_01"
    assert len(doc.segments) == 1
    seg = doc.segments[0]
    # Authoritative duration must match audio timeline (6.2s)
    assert seg.measured_duration_sec == pytest.approx(6.2, rel=1e-2)
    assert seg.audio_clip_path == "/workspace/audio/seg_01.wav"
    assert seg.music_cue.get("ducking_gain_db") == -14.0  # intensity 0.75 < 0.8 gets -14.0dB

    # Panels duration must sum up to the total measured duration
    total_panel_duration = sum(p.sub_duration_sec for p in seg.supporting_panels)
    assert total_panel_duration == pytest.approx(6.2, rel=1e-2)


def test_align_script_preserves_manual_overrides(tmp_path):
    """Verify that user edits with manual_override=True are strictly preserved during realignments."""
    svc = NarrationFrameAlignmentService()

    project = MagicMock(spec=ProjectRecord)
    project.id = "proj_test_02"
    project.workspace_path = str(tmp_path)

    # Pre-create a storyboard.json on disk with a manual override
    story_dir = tmp_path / "story"
    story_dir.mkdir(parents=True, exist_ok=True)

    manual_seg = StoryboardSegment(
        segment_id="seg_custom_01",
        scene_id="scene_01",
        sequence=0,
        text="[USER EDITED] An ancient patriarch ascends to heaven in thunder.",
        emotion="TRIUMPHANT",
        intensity=0.95,
        measured_duration_sec=7.5,
        supporting_panels=[
            StoryboardPanelRef(
                panel_id="pan_99",
                reading_order=0,
                role="ACTION",
                sub_duration_sec=7.5,
                camera_motion=CameraMotionConfig(type="IMPACT", start_zoom=1.0, end_zoom=1.2),
            )
        ],
        music_cue={"intent": "EPIC", "ducking_gain_db": -18.0},
        manual_override=True,
    )

    existing_doc = StoryboardDocument(
        project_id="proj_test_02",
        script_id="script_02",
        total_duration_sec=7.5,
        segments=[manual_seg],
    )
    (story_dir / "storyboard.json").write_text(json.dumps(existing_doc.model_dump()))

    # Now run realign
    script = MagicMock(spec=VideoScriptRecord)
    script.id = "script_02"

    seg_from_db = MagicMock(spec=ScriptSegmentRecord)
    seg_from_db.id = "seg_custom_01"
    seg_from_db.scene_id = "scene_01"
    seg_from_db.sequence = 0
    seg_from_db.text = "Original non-overridden database text"
    seg_from_db.emotion = "NEUTRAL"
    seg_from_db.intensity = 0.5
    seg_from_db.source_evidence = {}
    seg_from_db.manual_override = False
    seg_from_db.estimated_duration = 3.0
    seg_from_db.music_intent = "CALM"
    seg_from_db.sfx_intent = "NONE"

    panel1 = MagicMock(spec=PanelRecord)
    panel1.id = "pan_01"
    panel1.sequence = 0
    panel1.reading_order = 0
    panel1.width = 1000
    panel1.height = 1000
    panel1.x = 0
    panel1.y = 0
    panel1.normalized_x = 0.0
    panel1.normalized_y = 0.0
    panel1.normalized_width = 1.0
    panel1.normalized_height = 1.0
    panel1.crop_filename = "p1.jpg"
    panel1.panel_type = "STANDARD"

    db = MagicMock()
    def mock_query(model):
        m = MagicMock()
        if model == ProjectRecord:
            m.filter.return_value.first.return_value = project
        elif model == VideoScriptRecord:
            m.filter.return_value.first.return_value = script
            m.filter.return_value.filter.return_value.first.return_value = script
            m.filter.return_value.order_by.return_value.first.return_value = script
        elif model == AudioTimelineRecord:
            m.filter.return_value.order_by.return_value.first.return_value = None
        elif model == ScriptSegmentRecord:
            m.filter.return_value.order_by.return_value.all.return_value = [seg_from_db]
        elif model == PanelRecord:
            m.filter.return_value.order_by.return_value.all.return_value = [panel1]
        return m
    db.query.side_effect = mock_query

    realigned_doc = svc.align_script_to_frames(db, "proj_test_02", "script_02", force_realign=True)

    # Manual override segment must NOT be replaced with DB's text
    assert len(realigned_doc.segments) == 1
    preserved = realigned_doc.segments[0]
    assert preserved.manual_override is True
    assert preserved.text == "[USER EDITED] An ancient patriarch ascends to heaven in thunder."
    assert preserved.emotion == "TRIUMPHANT"
    assert preserved.intensity == 0.95
    assert preserved.supporting_panels[0].panel_id == "pan_99"
