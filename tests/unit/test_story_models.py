from engine.story.models import (
    NarrativeDocument,
    CharacterEntity,
    CharacterRole,
    CharacterStatus,
    LocationEntity,
    SpeakerAttributionEntity,
    SpeakerMethod,
    UtteranceEntity,
    UtteranceType,
    EmotionType,
    EventEntity,
    EventType,
    SceneEntity,
    BoundaryReason,
    StoryBeatEntity,
    DramaticFunction,
    ProvenanceReference,
    VideoScript,
    ScriptSegment,
    AdaptationProfile,
    SegmentType,
    MotionIntent,
)


def test_narrative_document_pydantic_schema():
    doc = NarrativeDocument(
        project_id="test_proj_01",
        version="1.0",
        language="en",
        characters=[
            CharacterEntity(
                character_id="char_001",
                display_name="Captain Sol",
                canonical_name="Solomon Vance",
                aliases=["Sol", "Captain"],
                description="Veteran starship commander.",
                visual_traits=["weathered face", "cybernetic left eye", "navy coat"],
                role=CharacterRole.PROTAGONIST,
                first_panel_id="pan_01",
                reference_panel_ids=["pan_01", "pan_05"],
                status=CharacterStatus.CONFIRMED,
            )
        ],
        locations=[
            LocationEntity(
                location_id="loc_001",
                name="Bridge of the Vanguard",
                canonical_name="Command Deck",
                description="Primary control hub of the dreadnought.",
                visual_cues=["holoscreens", "tactical console", "viewport"],
                panel_ids=["pan_01", "pan_02"],
                status=CharacterStatus.CONFIRMED,
            )
        ],
        scenes=[
            SceneEntity(
                scene_id="scene_001",
                sequence=1,
                title="Approaching the Rift",
                panel_start="pan_01",
                panel_end="pan_04",
                location_id="loc_001",
                character_ids=["char_001"],
                summary="Captain Sol assesses the anomaly unfolding beyond the forward viewport.",
                confidence=0.95,
                boundary_reason=BoundaryReason.LOCATION_CHANGE,
            )
        ],
        beats=[
            StoryBeatEntity(
                beat_id="beat_001",
                scene_id="scene_001",
                sequence=1,
                panel_ids=["pan_01", "pan_02"],
                event_ids=["evt_001"],
                summary="The ship drops out of hyperspace into uncharted space.",
                dramatic_function=DramaticFunction.INTRODUCTION,
                intensity=0.6,
                confidence=0.96,
                music_intent="MYSTERIOUS",
                sfx_intent="HYPERSPACE_EXIT",
            )
        ],
        events=[
            EventEntity(
                event_id="evt_001",
                event_type=EventType.ENTER,
                actor_character_id="char_001",
                location_id="loc_001",
                panel_ids=["pan_01"],
                description="The captain steps onto the bridge command dais.",
                confidence=0.95,
                evidence=ProvenanceReference(panel_ids=["pan_01"], confidence=0.95),
            )
        ],
        utterances=[
            UtteranceEntity(
                utterance_id="utt_001",
                text_region_id="tr_001",
                panel_id="pan_01",
                speaker_character_id="char_001",
                source_text="Status report on that energy surge.",
                corrected_text="Status report on that energy surge.",
                utterance_type=UtteranceType.DIALOGUE,
                emotion=EmotionType.DETERMINED,
                sequence=1,
                provenance=ProvenanceReference(panel_ids=["pan_01"], text_region_ids=["tr_001"]),
            )
        ],
    )

    # Validate serialization & deserialization round-trip
    dumped = doc.model_dump()
    assert dumped["project_id"] == "test_proj_01"
    assert len(dumped["characters"]) == 1
    assert dumped["characters"][0]["role"] == "PROTAGONIST"
    assert len(dumped["scenes"]) == 1
    assert len(dumped["utterances"]) == 1

    restored = NarrativeDocument.model_validate(dumped)
    assert restored.characters[0].display_name == "Captain Sol"
    assert restored.scenes[0].boundary_reason == BoundaryReason.LOCATION_CHANGE
