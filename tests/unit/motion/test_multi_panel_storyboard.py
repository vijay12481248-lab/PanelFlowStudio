from engine.motion.director import MotionDirector
from engine.motion.models.input_contract import MotionDirectorInput, VisualSource, MasterAudioTimeline, AudioInterval, MotionStyleProfile
from engine.story.models import VideoScript, ScriptSegment, ProvenanceReference, SegmentType, MotionIntent


def test_narration_shows_every_referenced_panel_inside_measured_audio():
    segment = ScriptSegment(segment_id="voice", scene_id="scene", type=SegmentType.NARRATOR,
                            text="The guard watches as the traveler approaches.",
                            source_evidence=ProvenanceReference(panel_ids=["p1", "p2", "p3"]))
    timeline = MotionDirector().plan_visual_timeline(MotionDirectorInput(
        project_id="project", script=VideoScript(script_id="script", project_id="project", segments=[segment]),
        visual_sources=[VisualSource(asset_id=pid, panel_id=pid, width=800, height=600) for pid in ["p1", "p2", "p3"]],
        master_audio_timeline=MasterAudioTimeline(total_duration_sec=10, intervals=[
            AudioInterval(script_segment_id="voice", start_time=0.5, end_time=9.5),
        ]),
    ))
    shots = timeline.all_shots()
    assert [s.source_panel_id for s in shots] == ["p1", "p2", "p3"]
    assert shots[0].start_time == 0.5
    assert shots[-1].end_time == 9.5
    assert all(a.end_time == b.start_time for a, b in zip(shots, shots[1:]))


def test_explicit_static_and_pan_limits_are_respected():
    for intent in (MotionIntent.STATIC, MotionIntent.PAN):
        segments = [ScriptSegment(segment_id=str(i), scene_id="scene", sequence=i,
                    motion_intent=intent, source_evidence=ProvenanceReference(panel_ids=["p"])) for i in (1, 2)]
        timeline = MotionDirector().plan_visual_timeline(MotionDirectorInput(
            project_id="p", script=VideoScript(script_id="s", project_id="p", segments=segments),
            visual_sources=[VisualSource(asset_id="p", panel_id="p", width=800, height=600)],
            style_profile=MotionStyleProfile(max_zoom=1.08, max_pan_distance=0.08, effect_intensity=0),
            master_audio_timeline=MasterAudioTimeline(total_duration_sec=8, intervals=[
                AudioInterval(script_segment_id=str(i), start_time=(i - 1) * 4, end_time=i * 4) for i in (1, 2)]),
        ))
        for shot in timeline.all_shots():
            assert shot.camera_end.zoom <= 1.08
            if intent == MotionIntent.STATIC:
                assert shot.camera_start == shot.camera_end
