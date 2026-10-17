from engine.story.models import (
    NarrativeDocument,
    CharacterEntity,
    CharacterRole,
    CharacterStatus,
    LocationEntity,
    SceneEntity,
    StoryBeatEntity,
    UtteranceEntity,
    UtteranceType,
    EmotionType,
    AdaptationProfile,
    SegmentType,
    ProvenanceReference,
    DramaticFunction,
    BoundaryReason,
)
from engine.story.script.adapter import script_adapter


def build_sample_narrative() -> NarrativeDocument:
    return NarrativeDocument(
        project_id="test_script_proj",
        version="1.0",
        language="en",
        characters=[
            CharacterEntity(
                character_id="char_pilot",
                display_name="Maya",
                role=CharacterRole.PROTAGONIST,
                status=CharacterStatus.CONFIRMED,
            )
        ],
        scenes=[
            SceneEntity(
                scene_id="scene_01",
                sequence=1,
                title="Descent to the Surface",
                panel_start="pan_01",
                panel_end="pan_02",
                character_ids=["char_pilot"],
                summary="Maya maneuvers through turbulent atmospheric entry.",
                boundary_reason=BoundaryReason.LOCATION_CHANGE,
            )
        ],
        beats=[
            StoryBeatEntity(
                beat_id="beat_01",
                scene_id="scene_01",
                sequence=1,
                panel_ids=["pan_01", "pan_02"],
                summary="Severe atmospheric turbulence threatens the descent craft.",
                dramatic_function=DramaticFunction.CONFLICT,
                importance="HIGH",
                intensity=0.8,
                music_intent="TENSE",
                sfx_intent="RUMBLE",
            )
        ],
        utterances=[
            UtteranceEntity(
                utterance_id="utt_01",
                text_region_id="tr_01",
                panel_id="pan_01",
                speaker_character_id="char_pilot",
                source_text="Brace for impact! Thrusters failing!",
                corrected_text="Brace for impact! Thrusters failing!",
                utterance_type=UtteranceType.DIALOGUE,
                emotion=EmotionType.ANGRY,
                intensity=0.9,
                sequence=1,
                provenance=ProvenanceReference(panel_ids=["pan_01"], text_region_ids=["tr_01"]),
            )
        ],
    )


def test_script_adapter_faithful_profile():
    narrative = build_sample_narrative()
    script = script_adapter.adapt(narrative, profile=AdaptationProfile.FAITHFUL)

    assert script.project_id == "test_script_proj"
    assert script.adaptation_profile == AdaptationProfile.FAITHFUL
    assert len(script.segments) >= 2  # dialogue + pause
    assert script.estimated_duration > 0.0

    # Ensure dialogue is preserved verbatim
    dlg_seg = next(s for s in script.segments if s.type == SegmentType.CHARACTER_DIALOGUE)
    assert dlg_seg.text == "Brace for impact! Thrusters failing!"
    assert dlg_seg.speaker_character_id == "char_pilot"
    assert dlg_seg.source_evidence.panel_ids == ["pan_01"]
    assert dlg_seg.source_evidence.text_region_ids == ["tr_01"]


def test_script_adapter_dramatic_narration_profile():
    narrative = build_sample_narrative()
    script = script_adapter.adapt(narrative, profile=AdaptationProfile.DRAMATIC_NARRATION)

    assert script.adaptation_profile == AdaptationProfile.DRAMATIC_NARRATION
    narrator_segs = [s for s in script.segments if s.type == SegmentType.NARRATOR]
    assert len(narrator_segs) >= 1
    # Check that narrator lines cite scene/beat evidence
    assert len(narrator_segs[0].source_evidence.panel_ids) >= 1
