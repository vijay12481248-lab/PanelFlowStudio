"""
End-to-End Integration Test for PanelFlow Motion Director Foundation (Milestone 6).
Verifies complete pipeline from Approved Script + Visual Sources + Master Audio Timeline
to a fully validated VisualTimeline, JSON serialization, and preview frame rendering.
"""
import pytest
import json
from pathlib import Path
from PIL import Image

from engine.motion.director import MotionDirector
from engine.motion.preview import MotionPreviewGenerator
from engine.motion.models.input_contract import (
    MotionDirectorInput,
    VisualSource,
    MasterAudioTimeline,
    AudioInterval,
    MotionStyleProfile,
)
from engine.motion.models.camera import NormalizedRect, TargetResolution
from engine.motion.models.enums import (
    MotionPreset,
    MotionType,
    TimelineSourceType,
    WarningSeverity,
)
from engine.motion.models.overrides import ShotOverride, MotionOverrides
from engine.motion.models.timeline import VisualTimeline
from engine.story.models import (
    VideoScript,
    ScriptSegment,
    SegmentType,
    EmotionType,
    MotionIntent,
    SceneEntity,
    ProvenanceReference,
)


@pytest.fixture
def complex_motion_input(tmp_path: Path) -> MotionDirectorInput:
    """
    Creates a realistic 5-panel, 2-scene project with multiple characters,
    establishing shots, conversational dialogue exchanges, and action beats.
    """
    # 1. Five visual sources (panels)
    panels = []
    for i in range(1, 6):
        img_path = tmp_path / f"panel_{i:02d}.png"
        img = Image.new("RGB", (1920, 1080), color=(50 + i * 25, 70, 90 + i * 15))
        img.save(img_path)

        char_boxes = {}
        speech_boxes = []

        if i == 2:
            # Two-shot conversation panel
            char_boxes = {
                "char_alice": NormalizedRect(x=0.15, y=0.25, width=0.28, height=0.65),
                "char_bob": NormalizedRect(x=0.60, y=0.25, width=0.28, height=0.65),
            }
            speech_boxes = [
                NormalizedRect(x=0.20, y=0.08, width=0.25, height=0.15),
                NormalizedRect(x=0.55, y=0.08, width=0.25, height=0.15),
            ]
        elif i == 3:
            # Action shock panel
            char_boxes = {
                "char_alice": NormalizedRect(x=0.35, y=0.20, width=0.35, height=0.70),
            }
        elif i == 5:
            # Mystery closeup
            char_boxes = {
                "char_villain": NormalizedRect(x=0.40, y=0.15, width=0.30, height=0.70),
            }

        panels.append(
            VisualSource(
                asset_id=f"panel_{i:02d}",
                panel_id=f"p_{i:02d}",
                sequence_global=i,
                file_path=str(img_path),
                width=1920,
                height=1080,
                character_bounding_boxes=char_boxes,
                speech_balloon_boxes=speech_boxes,
            )
        )

    # 2. Scenes
    scene1 = SceneEntity(scene_id="sc_01", sequence=1, title="City Ruins - Confrontation", panel_start="p_01", panel_end="p_03")
    scene2 = SceneEntity(scene_id="sc_02", sequence=2, title="Ancient Chamber - Revelation", panel_start="p_04", panel_end="p_05")

    # 3. Script Segments
    segments = [
        # Scene 1 - Panel 1 (Establishing)
        ScriptSegment(
            segment_id="seg_01",
            scene_id="sc_01",
            sequence=1,
            type=SegmentType.NARRATOR,
            text="The shattered metropolis lay silent under the twin moons.",
            motion_intent=MotionIntent.ESTABLISHING,
            estimated_duration=3.5,
            source_evidence=ProvenanceReference(panel_ids=["p_01"]),
        ),
        # Scene 1 - Panel 2 (Dialogue: Alice -> Bob -> Alice)
        ScriptSegment(
            segment_id="seg_02",
            scene_id="sc_01",
            sequence=2,
            type=SegmentType.CHARACTER_DIALOGUE,
            speaker_character_id="char_alice",
            text="Did you really think you could escape with the prism?",
            emotion=EmotionType.DETERMINED,
            motion_intent=MotionIntent.CHARACTER_FOCUS,
            estimated_duration=3.0,
            source_evidence=ProvenanceReference(panel_ids=["p_02"]),
        ),
        ScriptSegment(
            segment_id="seg_03",
            scene_id="sc_01",
            sequence=3,
            type=SegmentType.CHARACTER_DIALOGUE,
            speaker_character_id="char_bob",
            text="Escape? I was never running from you, Alice.",
            emotion=EmotionType.CALM,
            motion_intent=MotionIntent.CHARACTER_FOCUS,
            estimated_duration=3.2,
            source_evidence=ProvenanceReference(panel_ids=["p_02"]),
        ),
        ScriptSegment(
            segment_id="seg_04",
            scene_id="sc_01",
            sequence=4,
            type=SegmentType.CHARACTER_DIALOGUE,
            speaker_character_id="char_alice",
            text="Then drop the weapon right now!",
            emotion=EmotionType.ANGRY,
            motion_intent=MotionIntent.CHARACTER_FOCUS,
            estimated_duration=2.5,
            source_evidence=ProvenanceReference(panel_ids=["p_02"]),
        ),
        # Scene 1 - Panel 3 (Action shock beat)
        ScriptSegment(
            segment_id="seg_05",
            scene_id="sc_01",
            sequence=5,
            type=SegmentType.NARRATOR,
            text="A sudden blinding pulse erupted from beneath their feet!",
            motion_intent=MotionIntent.IMPACT,
            estimated_duration=3.0,
            source_evidence=ProvenanceReference(panel_ids=["p_03"]),
        ),
        # Scene 2 - Panel 4 (Interior transition)
        ScriptSegment(
            segment_id="seg_06",
            scene_id="sc_02",
            sequence=6,
            type=SegmentType.NARRATOR,
            text="Deep below, within the vaulted sanctuary of the ancestors...",
            motion_intent=MotionIntent.ESTABLISHING,
            estimated_duration=4.0,
            source_evidence=ProvenanceReference(panel_ids=["p_04"]),
        ),
        # Scene 2 - Panel 5 (Villain reveal)
        ScriptSegment(
            segment_id="seg_07",
            scene_id="sc_02",
            sequence=7,
            type=SegmentType.CHARACTER_DIALOGUE,
            speaker_character_id="char_villain",
            text="Welcome to the end of your world.",
            emotion=EmotionType.TENSE,
            motion_intent=MotionIntent.REVEAL,
            estimated_duration=3.8,
            source_evidence=ProvenanceReference(panel_ids=["p_05"]),
        ),
    ]

    script = VideoScript(
        script_id="scr_e2e",
        project_id="proj_motion_e2e",
        segments=segments,
    )

    # 4. Master Audio Timeline (Exact seconds)
    audio_intervals = [
        AudioInterval(interval_id="iv_01", script_segment_id="seg_01", start_time=0.0, end_time=3.5, is_speech=True),
        AudioInterval(interval_id="iv_02", script_segment_id="seg_02", start_time=3.5, end_time=6.5, is_speech=True),
        AudioInterval(interval_id="iv_03", script_segment_id="seg_03", start_time=6.5, end_time=9.7, is_speech=True),
        AudioInterval(interval_id="iv_04", script_segment_id="seg_04", start_time=9.7, end_time=12.2, is_speech=True),
        AudioInterval(interval_id="iv_05", script_segment_id="seg_05", start_time=12.2, end_time=15.2, is_speech=True),
        AudioInterval(interval_id="iv_06", script_segment_id="seg_06", start_time=15.2, end_time=19.2, is_speech=True),
        AudioInterval(interval_id="iv_07", script_segment_id="seg_07", start_time=19.2, end_time=23.0, is_speech=True),
    ]

    master_timeline = MasterAudioTimeline(
        total_duration_sec=23.0,
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        intervals=audio_intervals,
    )

    return MotionDirectorInput(
        project_id="proj_motion_e2e",
        script=script,
        scenes=[scene1, scene2],
        master_audio_timeline=master_timeline,
        visual_sources=panels,
        target_resolution=TargetResolution.standard_1080p(),
        style_profile=MotionStyleProfile.cinematic(),
        seed=101,
    )


def test_motion_director_full_e2e_pipeline(complex_motion_input: MotionDirectorInput, tmp_path: Path):
    director = MotionDirector(cache_dir=tmp_path / "motion_cache")

    # 1. Plan Visual Timeline
    timeline = director.plan_visual_timeline(complex_motion_input)
    assert isinstance(timeline, VisualTimeline)
    assert len(timeline.scenes) == 2
    assert timeline.total_shots >= 5
    assert timeline.total_duration_sec == complex_motion_input.master_audio_timeline.total_duration_sec

    # 2. Verify Zero Timeline Gaps and Overlaps
    all_shots = timeline.all_shots()
    assert all_shots[0].start_time == 0.0
    for i in range(1, len(all_shots)):
        prev = all_shots[i - 1]
        curr = all_shots[i]
        assert abs(curr.start_time - prev.end_time) <= 0.05, f"Gap or overlap between {prev.shot_id} and {curr.shot_id}"

    # 3. Verify No ERROR Warnings
    error_warnings = [w for w in timeline.warnings if w.severity == WarningSeverity.ERROR]
    assert len(error_warnings) == 0, f"Found error warnings: {error_warnings}"

    # 4. Verify Conversational Panning on Multi-speaker Scene
    # Panel 2 shots should pan between Alice and Bob
    sc1_shots = timeline.scenes[0].shots
    panel2_shots = [s for s in sc1_shots if s.source_asset_id == "panel_02"]
    assert len(panel2_shots) >= 2
    # Verify motion types include FOCUS_PUSH or PAN moves
    panel2_motion_types = {s.motion_type for s in panel2_shots}
    assert any(m in panel2_motion_types for m in [MotionType.PAN_RIGHT, MotionType.PAN_LEFT, MotionType.FOCUS_PUSH, MotionType.DIALOGUE_HOLD])

    # 5. Verify Camera Safe Bounds Clamping
    for s in all_shots:
        vis_start = s.camera_start.visible_rect(16.0 / 9.0, 16.0 / 9.0)
        vis_end = s.camera_end.visible_rect(16.0 / 9.0, 16.0 / 9.0)
        assert 0.0 <= vis_start.x <= 1.0
        assert 0.0 <= vis_start.y <= 1.0
        assert vis_start.right <= 1.0001
        assert vis_start.bottom <= 1.0001
        assert 0.0 <= vis_end.x <= 1.0
        assert 0.0 <= vis_end.y <= 1.0
        assert vis_end.right <= 1.0001
        assert vis_end.bottom <= 1.0001

    # 6. JSON Serialization Roundtrip
    json_str = timeline.model_dump_json(indent=2)
    deserialized = VisualTimeline.model_validate_json(json_str)
    assert deserialized.timeline_id == timeline.timeline_id
    assert deserialized.hash == timeline.hash
    assert len(deserialized.all_shots()) == len(timeline.all_shots())
    assert deserialized.total_duration_sec == timeline.total_duration_sec

    # 7. Keyframe Frame Previews with PIL
    preview_gen = MotionPreviewGenerator()
    preview_dir = tmp_path / "previews"
    rendered_previews = preview_gen.export_timeline_keyframes(
        timeline=timeline,
        asset_images={},
        output_dir=preview_dir,
    )
    assert len(rendered_previews) == len(all_shots)
    for shot_id, img_file in rendered_previews.items():
        assert Path(img_file).exists()
        assert Path(img_file).stat().st_size > 500

    # 8. User Manual Override
    initial_hash = timeline.hash
    first_shot = all_shots[0]
    override = ShotOverride(
        shot_id=first_shot.shot_id,
        override_motion_type=MotionType.SLOW_ZOOM_OUT,
        locked=True,
    )
    overridden_timeline = director.apply_override_to_timeline(timeline, override)
    updated_first_shot = overridden_timeline.find_shot_by_id(first_shot.shot_id)
    assert updated_first_shot.motion_type == MotionType.SLOW_ZOOM_OUT
    assert updated_first_shot.locked is True
    assert overridden_timeline.hash != initial_hash

    # 9. Selective Scene Invalidation
    # Modify Scene 2 script and regenerate
    spliced_timeline = director.regenerate_scenes(
        input_data=complex_motion_input,
        existing_timeline=overridden_timeline,
        scene_ids_to_regenerate={"sc_02"},
    )
    # Scene 1 shots should remain identical to overridden state
    assert spliced_timeline.scenes[0].shots[0].motion_type == MotionType.SLOW_ZOOM_OUT
    assert spliced_timeline.scenes[0].shots[0].locked is True
    assert spliced_timeline.total_duration_sec == complex_motion_input.master_audio_timeline.total_duration_sec
