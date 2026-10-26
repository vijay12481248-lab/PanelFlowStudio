import pytest
from engine.motion.planning.shot_planner import ShotPlanner
from engine.motion.models.input_contract import MotionDirectorInput, MasterAudioTimeline, AudioInterval, VisualSource
from engine.story.models import VideoScript, ScriptSegment, ProvenanceReference, SegmentType
from engine.story.models import MotionIntent
from engine.motion.models.camera import NormalizedRect
from engine.motion.models.enums import MotionType


def test_automatic_motion_plan_uses_measured_speech_beats_instead_of_equal_panel_durations():
    script = VideoScript(script_id='reference', project_id='p', segments=[ScriptSegment(
        segment_id='voice', scene_id='scene', type=SegmentType.NARRATOR,
        text='He raises the axe. She reacts.', source_evidence=ProvenanceReference(panel_ids=['axe', 'face']))])
    audio = MasterAudioTimeline(total_duration_sec=20, intervals=[AudioInterval(
        script_segment_id='voice', start_time=10, end_time=20, speech_cues=[
            {'text': 'He raises the axe.', 'panel_ids': ['axe'], 'start_sec': 0, 'end_sec': 7.2},
            {'text': 'She reacts.', 'panel_ids': ['face'], 'start_sec': 7.2, 'end_sec': 10},
        ], alignment_method='measured_beats')])
    plan = ShotPlanner().plan_timeline(MotionDirectorInput(project_id='p', script=script,
        visual_sources=[VisualSource(asset_id=pid, panel_id=pid) for pid in ['axe', 'face']], master_audio_timeline=audio))
    shots = plan.scenes[0].shots
    assert [(shot.start_time, shot.end_time) for shot in shots] == [(10, 17.2), (17.2, 20)]
    assert [shot.provenance['panel_ids'] for shot in shots] == [['axe'], ['face']]
    assert shots[1].caption_cues[0].text == 'She reacts.'


def test_explicit_reaction_crop_is_not_overridden_by_first_shot_establishing_rule():
    script = VideoScript(script_id='reference', project_id='p', segments=[ScriptSegment(
        segment_id='voice', scene_id='scene', type=SegmentType.NARRATOR,
        text='She freezes.', motion_intent=MotionIntent.REACTION_CLOSEUP,
        source_evidence=ProvenanceReference(panel_ids=['face']))])
    visual = VisualSource(asset_id='face', panel_id='face', character_bounding_boxes={
        'heroine': NormalizedRect(x=0.45, y=0.3, width=0.2, height=0.3)})
    audio = MasterAudioTimeline(total_duration_sec=3, intervals=[AudioInterval(script_segment_id='voice', start_time=0, end_time=3)])
    plan = ShotPlanner().plan_timeline(MotionDirectorInput(project_id='p', script=script, visual_sources=[visual], master_audio_timeline=audio))
    shot = plan.scenes[0].shots[0]
    assert shot.motion_type == MotionType.REACTION_HOLD
