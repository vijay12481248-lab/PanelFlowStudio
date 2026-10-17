from engine.story.models import (
    NarrativeDocument,
    CharacterEntity,
    CharacterRole,
    VideoScript,
    ScriptSegment,
    SegmentType,
    ProvenanceReference,
    PanelObservationEntity,
    UtteranceEntity,
    UtteranceType,
)
from engine.story.script.validator import script_validator


def test_faithfulness_validator_grounded_script():
    narrative = NarrativeDocument(
        project_id="test_faith_01",
        characters=[CharacterEntity(character_id="char_01", display_name="Hero", role=CharacterRole.PROTAGONIST)],
        observations=[PanelObservationEntity(panel_id="p1", sequence_global=1)],
        utterances=[
            UtteranceEntity(
                utterance_id="u1",
                text_region_id="tr1",
                panel_id="p1",
                speaker_character_id="char_01",
                corrected_text="I must venture forward.",
                utterance_type=UtteranceType.DIALOGUE,
            )
        ],
    )

    valid_script = VideoScript(
        script_id="sc_01",
        project_id="test_faith_01",
        segments=[
            ScriptSegment(
                segment_id="s1",
                scene_id="sc1",
                sequence=1,
                type=SegmentType.CHARACTER_DIALOGUE,
                speaker_character_id="char_01",
                text="I must venture forward.",
                source_evidence=ProvenanceReference(panel_ids=["p1"], text_region_ids=["tr1"], confidence=0.95),
            )
        ],
    )

    report = script_validator.validate(valid_script, narrative)
    assert report.passed is True
    assert report.unsupported_segments == 0
    assert report.supported_segments == 1
    assert report.coverage_score == 1.0


def test_faithfulness_validator_detects_unsupported_statement():
    narrative = NarrativeDocument(
        project_id="test_faith_02",
        characters=[CharacterEntity(character_id="char_01", display_name="Hero", role=CharacterRole.PROTAGONIST)],
        observations=[PanelObservationEntity(panel_id="p1", sequence_global=1)],
        utterances=[
            UtteranceEntity(
                utterance_id="u1",
                text_region_id="tr1",
                panel_id="p1",
                speaker_character_id="char_01",
                corrected_text="I must venture forward.",
                utterance_type=UtteranceType.DIALOGUE,
            )
        ],
    )

    hallucinated_script = VideoScript(
        script_id="sc_02",
        project_id="test_faith_02",
        segments=[
            ScriptSegment(
                segment_id="s_bad",
                scene_id="sc1",
                sequence=1,
                type=SegmentType.CHARACTER_DIALOGUE,
                speaker_character_id="char_unseen",
                text="The secret dark lord betrayed the ancient kingdom 100 years ago!",
                source_evidence=ProvenanceReference(panel_ids=[], text_region_ids=[]),  # zero evidence
            )
        ],
    )

    report = script_validator.validate(hallucinated_script, narrative)
    assert report.passed is False
    assert report.unsupported_segments == 1
    assert len(report.issues) == 1
    assert report.issues[0]["status"] == "UNSUPPORTED"
