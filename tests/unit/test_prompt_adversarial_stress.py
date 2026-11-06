"""Empirical Adversarial Stress Tests for Centralized Prompt Architecture & Compilers.

Authored by M3 Challenger 1 to stress-test:
1. Zero-character scenes: No hallucinated characters, "There are no people in the picture.",
   no false hand anatomy assertions, proper negative prompt.
2. Multi-character (>2 characters) scenes: Safe truncation to primary two characters,
   horizontal spatial partitioning, 1344x768 widescreen allocation, no crash on unregistered IDs.
3. Rare / unmapped / adversarial action verbs & inputs: Emojis, empty strings, 10,000-char strings,
   unknown camera angles, unknown shot sizes, unknown genres fallback.
4. simplify=True fallback: Proper ordering of emphasis clause, omission of kinematic and margin
   decorations, handling of empty/none emphasis, attempt >= 2 routing.
5. Video kinematics & resolution: Snapping to multiples of 32, fallback on rare camera directions,
   6-heading schema resilience with empty/malformed inputs.
"""

from __future__ import annotations

import pytest

from engine.original import shotspec as ss
from engine.original.models import (
    Bible,
    Character,
    Location,
    OriginalStory,
    Panel,
    Premise,
    Scene,
)
from engine.original.prompt import (
    CAMERA_KINEMATICS,
    GENRE_STYLE_PRESETS,
    MINIMAX_H3_NEGATIVE,
    MOTION_PACING,
    QWEN_IMAGE_21_BASE_NEGATIVE,
    RIGGING_NEGATIVE,
    UNIVERSAL_NEGATIVE_PROMPT,
    UNIVERSAL_VIDEO_NEGATIVE_PROMPT,
    VIDEO_BOKEH_DIRECTIVE,
    CameraOptics,
    CharacterIdentityToken,
    CompiledPrompt,
    CompositionGuardrails,
    DirectorialPromptSpec,
    LightingPhysics,
    PromptCompiler,
    StyleAnchor,
    TargetModel,
    build_directorial_prompt,
    compile_image_prompt,
    compile_sdxl_tag_prompt,
    compile_video_prompt,
    resolve_video_dimensions,
)
from tests.unit.test_original_story import full_bible


def make_test_story(genre: str = "bedtime") -> OriginalStory:
    """Create a test story with the specified genre in premise."""
    bible = full_bible()
    bible.premise.genre = genre
    return OriginalStory(bible=bible, scenes=[], panels=[])


# ==============================================================================
# 1. Zero-Character Scenes Stress Testing
# ==============================================================================

def test_zero_character_qwen_image_prompt():
    """Verify compile_image_prompt when no characters are in the frame."""
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(
        shot="wide",
        camera="eye_level",
        setting="an empty ancient library with dust motes and tall mahogany shelves",
        lighting="soft morning sunlight",
        mood="mysterious",
        key_visuals=["glowing tome on a stone pedestal"],
        characters=[],
    )

    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic", target=TargetModel.QWEN_IMAGE_21)
    pos, neg = compiled

    # 1. Must explicitly state that no people are in the picture
    assert "There are no people in the picture." in pos

    # 2. Must not hallucinate characters from the bible
    assert "Mira" not in pos
    assert "Pip" not in pos
    assert "a little girl" not in pos
    assert "a bird" not in pos

    # 3. Must not assert hand anatomy guardrails when no humans are present
    assert "Hands drawn with natural human anatomy" not in pos
    assert "five distinct separated fingers" not in pos

    # 4. Must not have spatial partitioning prefixes
    assert "On the left:" not in pos
    assert "On the right:" not in pos

    # 5. Dimensions for 0 characters on wide shot must be landscape (1344, 768)
    assert compiled.dimensions == (1344, 768)


def test_zero_character_simplify_mode():
    """Verify compile_image_prompt in simplify mode with 0 characters."""
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(
        shot="medium",
        setting="empty meadow",
        key_visuals=["sunflower field"],
        characters=[],
    )

    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic", simplify=True)
    pos, neg = compiled

    assert "There are no people in the picture." in pos
    assert "Hands drawn" not in pos
    assert "Mira" not in pos


def test_zero_character_sdxl_tag_prompt():
    """Verify compile_sdxl_tag_prompt emits 'no humans' when characters are absent."""
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(
        shot="wide",
        setting="empty mountain range",
        characters=[],
    )

    compiled = PromptCompiler.compile_sdxl_tag_prompt(story, spec, "attic")
    assert "no humans" in compiled.positive
    assert "solo" not in compiled.positive
    assert "2others" not in compiled.positive


def test_zero_character_directorial_prompt_spec():
    """Verify DirectorialPromptSpec builders correctly handle empty characters."""
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(shot="wide", characters=[])
    d_spec = DirectorialPromptSpec.from_shotspec(story, spec, "attic")
    assert len(d_spec.characters) == 0

    panel = Panel(
        id="p_empty",
        scene_id="s1",
        shot="wide",
        angle="eye_level",
        location_id="attic",
        character_ids=[],
        action="Empty attic room under moonlight",
        caption="",
    )
    p_spec = DirectorialPromptSpec.from_panel(story, panel)
    assert len(p_spec.characters) == 0


# ==============================================================================
# 2. Multi-Character (>2 characters) Scenes Stress Testing
# ==============================================================================

def test_multi_character_truncation_to_primary_two():
    """Verify that scenes with >2 characters are safely truncated to exactly 2 characters."""
    story = make_test_story("bedtime")
    # Add a 3rd and 4th character to bible
    story.bible.characters.append(
        Character(id="garrick", name="Garrick", role="mentor", species="human", gender="male", age_group="elder", look="grey beard, brown cloak", personality="wise")
    )
    story.bible.characters.append(
        Character(id="luna", name="Luna", role="companion", species="cat", gender="female", age_group="adult", look="silver fur", personality="aloof")
    )

    spec = ss.ShotSpec(
        shot="wide",
        camera="eye_level",
        characters=[
            ss.CharPose(id="mira", side="left", action="reading map"),
            ss.CharPose(id="pip", side="right", action="perched"),
            ss.CharPose(id="garrick", side="center", action="pointing"),
            ss.CharPose(id="luna", side="center", action="sleeping"),
        ],
    )

    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
    pos, neg = compiled

    # Primary two characters (mira and pip) must be present
    assert "On the left:" in pos
    assert "On the right:" in pos
    # Truncated characters (garrick and luna) must not be rendered as extra active subjects
    assert "Garrick" not in pos
    assert "Luna" not in pos
    assert "an old man with a wrinkled face" not in pos

    # Spatial separation contract must be injected
    assert "Clear horizontal separation between characters, distinct individual identities, zero feature blending." in pos

    # Dimensions for 2 characters must be widescreen (1344, 768)
    assert compiled.dimensions == (1344, 768)
    assert compiled.metadata["characters_count"] == 2


def test_multi_character_unregistered_id_handling():
    """Verify that unrecognized character IDs are dropped cleanly without raising KeyError."""
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(
        shot="medium",
        characters=[
            ss.CharPose(id="ghost_character_999", action="floating"),
            ss.CharPose(id="mira", side="center", action="smiling"),
            ss.CharPose(id="phantom_char_abc", action="whispering"),
        ],
    )

    # Must not raise KeyError
    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
    assert compiled.metadata["characters_count"] == 1
    assert "Mira" not in compiled.positive
    assert "a little girl" in compiled.positive
    assert "ghost_character_999" not in compiled.positive


def test_multi_character_screen_position_sorting():
    """Verify characters are sorted left-to-right regardless of order in spec.characters."""
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(
        shot="medium",
        characters=[
            ss.CharPose(id="pip", side="right", action="watching"),
            ss.CharPose(id="mira", side="left", action="looking"),
        ],
    )
    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
    pos = compiled.positive

    # Left character (mira / girl) must appear before right character (pip / bird)
    idx_left = pos.find("On the left:")
    idx_right = pos.find("On the right:")
    assert idx_left != -1
    assert idx_right != -1
    assert idx_left < idx_right


# ==============================================================================
# 3. Rare / Unmapped Action Verbs & Extreme Input Stress Testing
# ==============================================================================

def test_rare_unmapped_action_verbs():
    """Verify kinematic binding fallback gracefully when verbs are rare, unmapped, or archaic."""
    story = make_test_story("fantasy")
    spec = ss.ShotSpec(
        shot="medium",
        characters=[
            ss.CharPose(
                id="mira",
                pose="floccinaucinihilipilificating",
                action="levitating an arcane dodecahedron while transmogrifying the air",
                expression="inscrutable",
            )
        ],
        key_visuals=["somersaulting through temporal vortex"],
    )

    # Must compile without exception
    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
    pos = compiled.positive
    assert "floccinaucinihilipilificating" in pos.lower()
    assert "levitating an arcane dodecahedron" in pos
    assert "somersaulting through temporal vortex" in pos
    assert compiled.target_model == TargetModel.QWEN_IMAGE_21


def test_extreme_inputs_special_chars_emojis_and_whitespace():
    """Verify compiler survives emojis, unicode symbols, excessive whitespace, and empty strings."""
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(
        shot="medium",
        characters=[
            ss.CharPose(
                id="mira",
                pose="   \n\t  ",
                action="✨ (◕‿◕✿) ⚔️ holding a star-wand ⭐ 🌟",
                expression="   ",
            )
        ],
        setting="   \n\n\t  ",
        lighting="",
        mood="",
        key_visuals=["", "   ", "⭐ celestial flare"],
    )

    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
    assert "celestial flare" in compiled.positive
    assert "holding a star-wand" in compiled.positive
    # Danbooru weights should not be present
    assert ":1.3)" not in compiled.positive


def test_extremely_long_input_budget():
    """Verify compiler handles extremely long setting and key visual strings."""
    story = make_test_story("bedtime")
    long_desc = "very ancient wooden grandfather clock with intricate brass cogs " * 40
    spec = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", action="examining clock")],
        setting=long_desc,
        key_visuals=[long_desc],
    )
    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
    assert compiled.positive
    assert len(compiled.positive) > 500


def test_unknown_genre_and_camera_angle_fallback():
    """Verify compiler falls back gracefully when genre and camera angles are unknown."""
    story = make_test_story("cyberpunk_synthwave_unknown")
    spec = ss.ShotSpec(
        shot="unknown_hyper_zoom",
        camera="dutch_tilt_45_deg",
        characters=[ss.CharPose(id="mira")],
    )

    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
    assert compiled.positive
    assert "anime illustration" in compiled.positive.lower()
    # Should resolve default dimensions safely
    assert compiled.dimensions[0] > 0
    assert compiled.dimensions[1] > 0


# ==============================================================================
# 4. simplify=True Mode Stress Testing
# ==============================================================================

def test_simplify_mode_ordering_and_decoration_stripping():
    """Verify simplify=True behavior:

    - Places emphasis clause first.
    - Strips out kinematic contact binding decorations.
    - Strips out headroom/margin directives.
    - Preserves eyes closed directive when applicable.
    """
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(
        shot="medium",
        characters=[
            ss.CharPose(id="mira", action="firmly gripping a golden key with both hands", expression="eyes closed, sleeping")
        ],
        key_visuals=["golden key on the wooden table", "eyes closed"],
    )

    # 1. Standard mode (attempt 1) has kinematic bindings and margin directives
    c_standard = PromptCompiler.compile_image_prompt(story, spec, "attic", simplify=False)
    assert "Physical contact:" in c_standard.positive
    assert "generous headroom above the hair" in c_standard.positive

    # 2. Simplified mode (attempt >= 2) strips kinematics and margins
    c_simplified = PromptCompiler.compile_image_prompt(
        story, spec, "attic", emphasis=["golden key"], simplify=True
    )
    assert c_simplified.positive.startswith("Most important: the picture must clearly show golden key.")
    assert "Physical contact:" not in c_simplified.positive
    assert "generous headroom above the hair" not in c_simplified.positive
    # Eyes closed directive must be retained
    assert "Her/his eyes are closed." in c_simplified.positive


def test_simplify_mode_with_empty_emphasis():
    """Verify simplify=True handles empty or None emphasis list cleanly."""
    story = make_test_story("bedtime")
    spec = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", action="reading")],
        key_visuals=["illuminated scroll"],
    )

    c_none = PromptCompiler.compile_image_prompt(story, spec, "attic", emphasis=None, simplify=True)
    assert "Most important:" not in c_none.positive
    assert "The picture must clearly show: illuminated scroll." in c_none.positive

    c_empty = PromptCompiler.compile_image_prompt(story, spec, "attic", emphasis=[], simplify=True)
    assert "Most important:" not in c_empty.positive


def test_build_directorial_prompt_attempt_escalation():
    """Verify build_directorial_prompt toggles simplify=True when attempt >= 2."""
    story = make_test_story("bedtime")
    panel = Panel(
        id="p1",
        scene_id="s1",
        shot="medium",
        angle="eye_level",
        location_id="attic",
        character_ids=["mira"],
        action="Mira opening a secret latch",
        caption="",
        director=ss.ShotSpec(
            shot="medium",
            characters=[ss.CharPose(id="mira", action="opening a secret latch")],
            key_visuals=["secret latch"],
        ).model_dump(),
    )

    # Attempt 1: Standard compilation (simplify=False)
    c1 = build_directorial_prompt(story, panel, attempt=1)
    assert c1.metadata["simplify"] is False
    assert "generous headroom above the hair" in c1.positive

    # Attempt 2: Simplified compilation (simplify=True)
    c2 = build_directorial_prompt(story, panel, attempt=2)
    assert c2.metadata["simplify"] is True
    assert "generous headroom above the hair" not in c2.positive

    # Attempt 3: Still simplified
    c3 = build_directorial_prompt(story, panel, attempt=3)
    assert c3.metadata["simplify"] is True


# ==============================================================================
# 5. Video Prompt Kinematics & Resolution Stress Testing
# ==============================================================================

def test_video_resolution_snapping_multiple_of_32():
    """Verify that video dimension resolution snaps any arbitrary dimensions to multiples of 32."""
    test_cases = [
        ((1340, 770), (1344, 768)),
        ((1000, 1000), (992, 992)),
        ((1920, 1080), (1920, 1088)),
        ((15, 10), (32, 32)),  # Minimum 32
        ((1024, 1024), (1024, 1024)),
    ]
    for raw_dims, exp_dims in test_cases:
        res = resolve_video_dimensions(dimensions=raw_dims)
        assert res == exp_dims, f"Expected {exp_dims} for {raw_dims}, got {res}"
        assert res[0] % 32 == 0
        assert res[1] % 32 == 0


def test_video_prompt_rare_camera_direction_fallback():
    """Verify compile_video_prompt falls back to push_in for unrecognized camera trajectory."""
    res = compile_video_prompt(camera_direction="hyperloop_spiral_flyby")
    assert CAMERA_KINEMATICS["push_in"] in res.positive
    assert res.target_model == TargetModel.MINIMAX_H3


def test_video_prompt_6_heading_empty_inputs_resilience():
    """Verify compile_video_prompt in 6-heading mode handles completely empty inputs."""
    res = compile_video_prompt(
        spec=None,
        style_6_heading=True,
        subject_definitions="",
        summary="",
        retention_analysis="",
        soundscape="",
        music="",
    )
    assert "subject_definitions:" in res.positive
    assert "summary:" in res.positive
    assert "retention_analysis:" in res.positive
    assert "detailed_description:" in res.positive
    assert "overall_soundscape:" in res.positive
    assert "non_diegetic_music:" in res.positive
    assert res.dimensions == (1344, 768)
    assert res.dimensions[0] % 32 == 0
    assert res.dimensions[1] % 32 == 0
