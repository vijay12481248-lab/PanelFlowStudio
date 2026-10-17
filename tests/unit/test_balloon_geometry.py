from engine.story.models import CharacterEntity, CharacterRole, CharacterStatus, SpeakerMethod
from engine.story.balloon_geometry import resolve_speaker_by_geometry


def test_resolve_narration_and_caption_geometry():
    regions = [
        {"id": "tr_nar_01", "region_type": "NARRATION", "x": 10, "y": 10, "width": 300, "height": 80},
        {"id": "tr_cap_02", "region_type": "CAPTION", "x": 10, "y": 400, "width": 250, "height": 60},
    ]
    chars = [
        CharacterEntity(
            character_id="char_hero",
            display_name="Hero",
            role=CharacterRole.PROTAGONIST,
            status=CharacterStatus.CONFIRMED,
        )
    ]

    attributions = resolve_speaker_by_geometry(
        panel_id="pan_001",
        text_regions=regions,
        characters_in_panel=chars,
    )

    assert len(attributions) == 2
    assert attributions[0].speaker_character_id == "NARRATOR"
    assert attributions[0].reason_code == "NARRATION_BOX"
    assert attributions[0].confidence >= 0.99
    assert attributions[1].speaker_character_id == "NARRATOR"


def test_resolve_solitary_character_geometry():
    regions = [
        {"id": "tr_spk_01", "region_type": "SPEECH", "x": 50, "y": 50, "width": 200, "height": 100},
    ]
    chars = [
        CharacterEntity(
            character_id="char_solo",
            display_name="Lone Wanderer",
            role=CharacterRole.PROTAGONIST,
            status=CharacterStatus.CONFIRMED,
        )
    ]

    attributions = resolve_speaker_by_geometry(
        panel_id="pan_002",
        text_regions=regions,
        characters_in_panel=chars,
    )

    assert len(attributions) == 1
    assert attributions[0].speaker_character_id == "char_solo"
    assert attributions[0].reason_code == "SOLITARY_CHARACTER"
    assert attributions[0].confidence == 0.95
    assert attributions[0].method == SpeakerMethod.BALLOON_GEOMETRY


def test_resolve_dialogue_alternation_geometry():
    regions = [
        {"id": "tr_dlg_01", "region_type": "SPEECH", "x": 40, "y": 40, "width": 150, "height": 80},
    ]
    chars = [
        CharacterEntity(character_id="char_a", display_name="Alice", role=CharacterRole.PROTAGONIST),
        CharacterEntity(character_id="char_b", display_name="Bob", role=CharacterRole.SUPPORTING),
    ]

    # If Alice just spoke previously, Bob is attributed by sequential context alternation
    attributions = resolve_speaker_by_geometry(
        panel_id="pan_003",
        text_regions=regions,
        characters_in_panel=chars,
        previous_speaker_id="char_a",
    )

    assert len(attributions) == 1
    assert attributions[0].speaker_character_id == "char_b"
    assert attributions[0].reason_code == "SEQUENTIAL_CONTEXT"
