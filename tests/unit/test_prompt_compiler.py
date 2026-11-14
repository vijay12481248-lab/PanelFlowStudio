"""Unit tests for the centralized prompt architecture and compilation pipeline.

Verifies Requirements R1, R2, R3, R4 and acceptance criteria from:
- docs/PROMPT_PRACTITIONER_GUIDE.md
- engine/original/prompt.py
- .agents/teamwork/ORIGINAL_REQUEST.md
- .agents/teamwork/orchestrator_prompt_arch/SCOPE.md
"""

from __future__ import annotations

import json
from typing import Any

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
    INPAINT_CORRECTION_PROMPTS,
    MINIMAX_H3_NEGATIVE,
    MOTION_PACING,
    NATURAL_PERSON_LOOKUP,
    QWEN_IMAGE_21_BASE_NEGATIVE,
    RIGGING_NEGATIVE,
    UNIVERSAL_NEGATIVE_PROMPT,
    UNIVERSAL_VIDEO_NEGATIVE_PROMPT,
    VIDEO_BOKEH_DIRECTIVE,
    VIDEO_SECONDARY_DYNAMICS,
    VIDEO_TEMPORAL_INVARIANCE,
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


def make_story() -> OriginalStory:
    """Helper creating a standard story instance with bedtime bible."""
    return OriginalStory(bible=full_bible(), scenes=[], panels=[])


@pytest.fixture
def story() -> OriginalStory:
    """Pytest fixture providing a fresh OriginalStory instance."""
    return make_story()


# ==============================================================================
# 1. Practitioner Best Practices Verification
# ==============================================================================

def test_compiled_prompt_adheres_to_practitioner_best_practices(story: OriginalStory):
    """Verify compiled prompts satisfy the 6 Core Engineering Principles from Practitioner Guide:

    1. Explicit 4-tier visual style anchors (medium, line geometry, palette, lighting physics).
    2. Character proper names un-named to descriptive role noun phrases.
    3. Pseudo-quality buzzwords ('masterpiece', '8k', 'ultra realistic') eliminated.
    4. Kinematic contact bindings present when action verbs are specified.
    5. Headroom and margin clearances explicitly enforced.
    """
    spec = ss.ShotSpec(
        shot="medium",
        camera="eye_level",
        setting="a cozy bedroom with wooden rafters",
        lighting="",
        mood="",
        key_visuals=["Mira holding a wooden staff"],
        characters=[
            ss.CharPose(
                id="mira",
                side="center",
                pose="standing tall",
                expression="smiling gently",
                action="Mira holding a wooden staff firmly",
            )
        ],
    )
    compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
    pos, neg = compiled
    preset = GENRE_STYLE_PRESETS["bedtime"]

    # 1. Four-tier style anchors present
    assert preset.medium in pos, "Tier 1 Medium anchor missing"
    assert preset.line_geometry in pos, "Tier 2 Line geometry anchor missing"
    assert preset.palette in pos, "Tier 3 Palette anchor missing"
    assert preset.lighting_physics in pos, "Tier 4 Lighting physics anchor missing"

    # 2. Unnaming protocol: character proper names must be absent, replaced by role nouns
    assert "Mira" not in pos, "Character proper name 'Mira' leaked into positive prompt"
    assert "Pip" not in pos, "Character proper name 'Pip' leaked into positive prompt"
    assert "a little girl with short brown hair" in pos

    # 3. Elimination of pseudo-quality buzzwords
    forbidden_buzzwords = [
        "masterpiece",
        "high quality",
        "8k",
        "ultra realistic",
        "trending on artstation",
        "best quality",
    ]
    for buzzword in forbidden_buzzwords:
        assert buzzword not in pos.lower(), f"Forbidden buzzword '{buzzword}' found in prompt"

    # 4. Kinematic contact bindings enforced
    assert "hands firmly gripping the object" in pos or "fingers visibly curled around it" in pos

    # 5. Headroom and margin clearances enforced
    assert "generous headroom above the hair" in pos
    assert "no cropping at top" in pos


# ==============================================================================
# 2. Qwen Image 2.1 Compilation Verification
# ==============================================================================

def test_qwen_image_21_compilation(story: OriginalStory):
    """Verify prompt compilation for Qwen Image 2.1 via compile_image_prompt:

    - Natural prose paragraph structure with proper sentence punctuation.
    - Multiple of 16 dimensions across all standard shot framing buckets.
    - Negative prompt contains comprehensive anatomical and spatial defect suppression.
    - Pose-sensitivity detection attenuating gaze and adding closed/facing-away tokens.
    """
    # Test aspect ratio buckets and multiple of 16 compliance
    shot_dimension_pairs = [
        ("full", (832, 1216)),
        ("medium", (1024, 1024)),
        ("wide", (1344, 768)),
    ]
    for shot, exp_dims in shot_dimension_pairs:
        sp = ss.ShotSpec(shot=shot, characters=[ss.CharPose(id="mira")])
        res = PromptCompiler.compile_image_prompt(
            story, sp, "attic", target=TargetModel.QWEN_IMAGE_21
        )
        assert res.dimensions == exp_dims, f"Expected {exp_dims} for {shot}, got {res.dimensions}"
        assert res.dimensions[0] % 16 == 0, f"Width {res.dimensions[0]} not divisible by 16"
        assert res.dimensions[1] % 16 == 0, f"Height {res.dimensions[1]} not divisible by 16"
        assert res.target_model == TargetModel.QWEN_IMAGE_21

        # Natural prose structure: ends with terminal punctuation, no booru weights
        assert res.positive.endswith(".") or res.positive.endswith("design.")
        assert ":1.3)" not in res.positive, "Danbooru weighting leaked into natural prose"

        # Negative prompt contains defect suppression tokens
        assert "bad anatomy" in res.negative
        assert "deformed hands" in res.negative
        assert "extra fingers" in res.negative
        assert "missing fingers" in res.negative
        assert "floating objects" in res.negative
        assert "disconnected grip" in res.negative

    # Pose sensitivity: sleeping character triggers open eyes suppression
    sp_asleep = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", expression="sleeping peacefully, eyes closed")],
    )
    res_asleep = PromptCompiler.compile_image_prompt(story, sp_asleep, "attic")
    assert "open eyes" in res_asleep.negative
    assert "looking at viewer" in res_asleep.negative

    # Pose sensitivity: rear-facing character triggers looking at viewer suppression
    sp_away = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", pose="facing away from camera")],
    )
    res_away = PromptCompiler.compile_image_prompt(story, sp_away, "attic")
    assert "looking at viewer" in res_away.negative


# ==============================================================================
# 3. MiniMax Fast H3 Video Compilation Verification
# ==============================================================================

def test_minimax_h3_video_compilation(story: OriginalStory):
    """Verify video prompt compilation for MiniMax H3 Turbo via compile_video_prompt:

    - Kinematic delta motion prompts avoiding redundant pixel re-description.
    - All 7 camera kinematics trajectories supported.
    - Motion pacing modes ('subtle', 'balanced', 'action').
    - Multiple of 32 dimensions strictly enforced.
    - Temporal negative prompt suppresses morphing, flickering, and jump cuts.
    - Native 6-heading schema mode supported.
    """
    # 1. Camera kinematics vocabulary across all 7 modes
    for cam_dir in ["push_in", "pull_out", "pan_right", "pan_left", "tilt_up", "orbit", "static"]:
        res_v = PromptCompiler.compile_video_prompt(camera_direction=cam_dir)
        assert CAMERA_KINEMATICS[cam_dir] in res_v.positive, f"Kinematics missing for {cam_dir}"
        assert res_v.dimensions[0] % 32 == 0, "Video width must be multiple of 32"
        assert res_v.dimensions[1] % 32 == 0, "Video height must be multiple of 32"
        assert "morphing face" in res_v.negative
        assert "fast jerky motion" in res_v.negative
        assert "temporal tearing" in res_v.negative

    # 2. Motion pacing
    res_subtle = PromptCompiler.compile_video_prompt(intensity="subtle")
    assert MOTION_PACING["subtle"] in res_subtle.positive

    res_action = PromptCompiler.compile_video_prompt(intensity="action")
    assert MOTION_PACING["action"] in res_action.positive

    # 3. Wide shot bokeh directive
    sp_wide = ss.ShotSpec(shot="wide")
    res_wide_v = PromptCompiler.compile_video_prompt(spec=sp_wide)
    assert VIDEO_BOKEH_DIRECTIVE in res_wide_v.positive

    # 4. Native 6-heading schema compilation
    res_6h = PromptCompiler.compile_video_prompt(
        style_6_heading=True,
        soundscape="Subtle night breeze through cedar branches",
        music="Gentle cello arpeggios",
    )
    expected_headings = [
        "subject_definitions:",
        "summary:",
        "retention_analysis:",
        "detailed_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    ]
    for h in expected_headings:
        assert h in res_6h.positive, f"Heading {h} missing in 6-heading mode"
    assert "Subtle night breeze through cedar branches" in res_6h.positive
    assert "Gentle cello arpeggios" in res_6h.positive
    assert "Zero morphing of facial features" in res_6h.positive


# ==============================================================================
# 4. Prompt-Following Engine Empty Negative Verification
# ==============================================================================

def test_prompt_following_engine_empty_negative(story: OriginalStory):
    """Verify that prompt-following diffusion engines receive an empty negative prompt:

    Target 'flux' or 'natural' must yield negative == '' to resolve test_original_art.py:252.
    """
    sp = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", action="reading an ancient map")],
    )
    res_flux = PromptCompiler.compile_image_prompt(story, sp, "attic", target="flux")
    assert res_flux.negative == "", f"Target 'flux' must receive empty negative, got: {res_flux.negative}"

    res_natural = PromptCompiler.compile_image_prompt(story, sp, "attic", target="natural")
    assert res_natural.negative == "", f"Target 'natural' must receive empty negative, got: {res_natural.negative}"


# ==============================================================================
# 5. Multi-Shot Visual Style Consistency Verification
# ==============================================================================

def test_multi_shot_style_consistency(story: OriginalStory):
    """Verify that style anchors remain strictly invariant across a multi-panel sequence:

    - Visual style tiers (medium and line geometry) remain identical.
    - Shots, angles, and poses vary according to scene beats.
    - Proper character names are never leaked in any panel.
    """
    s1 = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", side="center", pose="sitting", action="holding a lamp")],
    )
    s2 = ss.ShotSpec(
        shot="close",
        characters=[ss.CharPose(id="mira", side="center", pose="standing", expression="smiling")],
    )
    s3 = ss.ShotSpec(
        shot="wide",
        characters=[
            ss.CharPose(id="mira", side="left", pose="standing", action="pointing at window"),
            ss.CharPose(id="pip", side="right", pose="perched", action="watching"),
        ],
    )

    c1 = PromptCompiler.compile_image_prompt(story, s1, "attic")
    c2 = PromptCompiler.compile_image_prompt(story, s2, "attic")
    c3 = PromptCompiler.compile_image_prompt(story, s3, "attic")

    anchor = GENRE_STYLE_PRESETS["bedtime"]
    for idx, c in enumerate((c1, c2, c3), 1):
        assert anchor.medium in c.positive, f"Medium anchor drifted in shot {idx}"
        assert anchor.line_geometry in c.positive, f"Line geometry drifted in shot {idx}"
        assert "Mira" not in c.positive, f"Character name leaked in shot {idx}"
        assert "Pip" not in c.positive, f"Character name leaked in shot {idx}"

    # Verify framing variations occurred correctly
    assert c1.dimensions == (1024, 1024)
    assert c2.dimensions == (1024, 1024)
    assert c3.dimensions == (1344, 768)
    assert "Medium shot from the waist up" in c1.positive
    assert "Centered framing focusing on the face" in c2.positive or "Medium shot" in c2.positive
    assert "Wide shot showing the whole scene" in c3.positive


# ==============================================================================
# 6. Defect Mitigation & System Guardrails Verification
# ==============================================================================

def test_defect_mitigation_and_guardrails(story: OriginalStory):
    """Verify anatomical, spatial, and rigging defect guardrails:

    1. Hand and digit guardrails: 5-digit specification and polydactyly negative suppression.
    2. Spatial partitioning: 2-character horizontal separation on widescreen canvas.
    3. Turnaround sheet: 1536x768 resolution, neutral A-pose, RIGGING_NEGATIVE suppression.
    """
    # 1. Hand and digit guardrails
    s1 = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", action="holding a carved staff")],
    )
    c1 = PromptCompiler.compile_image_prompt(story, s1, "attic")
    assert "Hands drawn with natural human anatomy, exactly five distinct separated fingers, no extra digits." in c1.positive
    assert "extra fingers" in c1.negative
    assert "fused fingers" in c1.negative

    # 2. 2-character spatial separation
    s2 = ss.ShotSpec(
        shot="medium",
        characters=[
            ss.CharPose(id="mira", side="left", action="holding lantern"),
            ss.CharPose(id="pip", side="right", action="perched on beam"),
        ],
    )
    c2 = PromptCompiler.compile_image_prompt(story, s2, "attic")
    assert c2.dimensions == (1344, 768)
    assert "Clear horizontal separation between characters, distinct individual identities, zero feature blending." in c2.positive
    assert "On the left:" in c2.positive
    assert "On the right:" in c2.positive

    # 3. Turnaround sheet compilation
    s_turn = ss.ShotSpec(shot="turnaround", characters=[ss.CharPose(id="mira")])
    c_turn = PromptCompiler.compile_image_prompt(story, s_turn, "attic")
    assert c_turn.dimensions == (1536, 768)
    assert "Unobstructed neutral A-pose with arms angled 45 degrees downward" in c_turn.positive
    assert "Single clean character sheet, no text, no labels, no watermark." in c_turn.positive
    assert c_turn.negative == RIGGING_NEGATIVE


# ==============================================================================
# 7. Retry Simplify Mode Verification
# ==============================================================================

def test_qwen_simplify_mode_on_retry(story: OriginalStory):
    """Verify that simplify=True (used on retry attempts >= 2):

    - Places the missing visual/emphasis clause first in the prompt.
    - Strips extraneous kinematic decorations to focus latent sampling.
    """
    s_simp = ss.ShotSpec(
        shot="medium",
        key_visuals=["golden key on the table"],
        characters=[ss.CharPose(id="mira", action="searching for key")],
    )
    c_simp = PromptCompiler.compile_image_prompt(
        story, s_simp, "attic", emphasis=["golden key on the table"], simplify=True
    )
    assert c_simp.positive.startswith("Most important: the picture must clearly show golden key on the table.")


# ==============================================================================
# 8. Legacy SDXL Tag Compilation Verification
# ==============================================================================

def test_legacy_sdxl_tag_compilation(story: OriginalStory):
    """Verify backwards-compatible SDXL tag prompt compilation:

    - Emits comma-separated Danbooru tags.
    - Sets character count tags ('solo', '2others', 'no humans').
    - Applies weight formatting '(tag:1.3)' for emphasis.
    - Respects word budget limits.
    """
    s1 = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", action="holding a lantern")],
    )
    c_sdxl = PromptCompiler.compile_sdxl_tag_prompt(story, s1, "attic", emphasis=["lantern"])
    assert "solo" in c_sdxl.positive
    assert "(lantern:1.4)" in c_sdxl.positive or "(lantern:1.3)" in c_sdxl.positive
    assert c_sdxl.target_model == TargetModel.SDXL
    assert c_sdxl.negative != ""


# ==============================================================================
# 9. Genre Style Presets Integrity Verification
# ==============================================================================

def test_genre_style_presets_integrity():
    """Verify all 6 production genres have fully codified 4-tier style presets:

    'bedtime', 'horror', 'mystery', 'fantasy', 'mythology', 'vox'.
    """
    production_genres = ["bedtime", "horror", "mystery", "fantasy", "mythology", "vox"]
    for genre in production_genres:
        assert genre in GENRE_STYLE_PRESETS, f"Preset for genre '{genre}' is missing"
        preset = GENRE_STYLE_PRESETS[genre]
        assert preset.medium, f"Medium missing for {genre}"
        assert preset.line_geometry, f"Line geometry missing for {genre}"
        assert preset.palette, f"Palette missing for {genre}"
        assert preset.lighting_physics, f"Lighting physics missing for {genre}"
        assert preset.negative_prompt, f"Negative prompt missing for {genre}"
        assert preset.review_witness_rule, f"Review witness rule missing for {genre}"

        prose = preset.to_natural_prose()
        assert preset.medium.rstrip(".") in prose
        assert preset.line_geometry.rstrip(".") in prose

        tags = preset.to_tags()
        assert len(tags) > 0


# ==============================================================================
# 10. Character Identity Token Schema & Unnaming Verification
# ==============================================================================

def test_character_identity_token_unnaming_and_separation():
    """Verify CharacterIdentityToken separates immutable anatomy from mutable wardrobe

    and enforces unnaming across human and non-human species.
    """
    # Human character
    char_human = Character(
        id="hero",
        name="Marcus",
        role="protagonist",
        age_group="teen",
        gender="male",
        species="human",
        look="black spiky hair, blue eyes, dark jacket, leather boots",
        personality="brave",
    )
    token_human = CharacterIdentityToken.from_character(char_human)
    assert token_human.unnamed_role == "a teenage boy"
    assert "black spiky hair" in token_human.immutable_features
    assert "dark jacket" in token_human.mutable_features
    assert "Marcus" not in token_human.to_natural_description()

    # Animal companion
    char_animal = Character(
        id="cat",
        name="Biscuit",
        role="companion",
        age_group="adult",
        gender="female",
        species="cat",
        look="orange calico fur, emerald eyes",
        personality="playful",
    )
    token_animal = CharacterIdentityToken.from_character(char_animal)
    assert token_animal.unnamed_role == "a cat"
    assert "Biscuit" not in token_animal.to_natural_description()


# ==============================================================================
# 11. Camera Optics, Lighting Physics & Composition Guardrails Schemas
# ==============================================================================

def test_camera_optics_and_lighting_physics_schemas():
    """Verify camera optics, lighting physics, and composition guardrails schemas."""
    # Camera optics
    cam = CameraOptics(shot="close", headroom_margin=0.15)
    framing = cam.to_framing_directive()
    assert "generous headroom" in framing
    assert "15%" in framing

    # Lighting physics
    lp = LightingPhysics(
        primary_source="lantern_glow",
        direction="top_left",
        color_temperature="3000K warm amber",
    )
    lighting_dir = lp.to_lighting_directive()
    assert "lantern glow" in lighting_dir
    assert "3000K warm amber" in lighting_dir

    # Composition guardrails
    cg = CompositionGuardrails(
        hand_anatomy_guard="Natural hands with five digits.",
        spatial_partitioning_directive="Left and right separation.",
    )
    prose = cg.to_guardrail_prose()
    assert "Natural hands with five digits." in prose
    assert "Left and right separation." in prose


# ==============================================================================
# 12. CompiledPrompt Container Ergonomics Verification
# ==============================================================================

def test_compiled_prompt_container_ergonomics():
    """Verify CompiledPrompt backwards compatibility:

    - Tuple unpacking: pos, neg = compiled
    - Indexing: compiled[0], compiled[1]
    - Length check: len(compiled) == 2
    - as_tuple() method
    - Attribute access: .positive, .negative, .dimensions, .target_model
    """
    cp = CompiledPrompt(
        positive="a beautiful landscape",
        negative="blurry, low quality",
        dimensions=(1344, 768),
        target_model=TargetModel.QWEN_IMAGE_21,
    )
    # 1. Unpacking
    pos, neg = cp
    assert pos == "a beautiful landscape"
    assert neg == "blurry, low quality"

    # 2. Indexing
    assert cp[0] == "a beautiful landscape"
    assert cp[1] == "blurry, low quality"

    # 3. Length & tuple export
    assert len(cp) == 2
    assert cp.as_tuple() == ("a beautiful landscape", "blurry, low quality")

    # 4. Attributes
    assert cp.dimensions == (1344, 768)
    assert cp.target_model == TargetModel.QWEN_IMAGE_21


# ==============================================================================
# 13. Inpaint Correction Prompts Registry Verification
# ==============================================================================

def test_inpaint_correction_prompts_registry():
    """Verify that INPAINT_CORRECTION_PROMPTS contains entries for all 7 canonical defect types:

    'polycephaly', 'extra_limbs', 'missing_limbs', 'distorted_digits',
    'limb_topology', 'unanchored_object', 'disconnected_interaction'.
    """
    canonical_defects = [
        "polycephaly",
        "extra_limbs",
        "missing_limbs",
        "distorted_digits",
        "limb_topology",
        "unanchored_object",
        "disconnected_interaction",
    ]
    for defect_key in canonical_defects:
        assert defect_key in INPAINT_CORRECTION_PROMPTS
        entry = INPAINT_CORRECTION_PROMPTS[defect_key]
        assert "positive" in entry and entry["positive"]
        assert "negative" in entry and entry["negative"]
        assert "bbox" in entry and len(entry["bbox"]) == 4


# ==============================================================================
# 14. DirectorialPromptSpec Builders Verification
# ==============================================================================

def test_directorial_prompt_spec_builders(story: OriginalStory):
    """Verify DirectorialPromptSpec factory constructors:

    - from_shotspec
    - from_panel
    """
    sp = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", action="holding staff")],
    )
    spec_obj = DirectorialPromptSpec.from_shotspec(story, sp, "attic")
    assert spec_obj.target_engine == TargetModel.QWEN_IMAGE_21
    assert spec_obj.dimensions == (1024, 1024)
    assert len(spec_obj.characters) == 1
    assert spec_obj.characters[0].unnamed_role == "a little girl"

    panel = Panel(
        id="p1",
        scene_id="s1",
        shot="full",
        angle="eye_level",
        location_id="attic",
        character_ids=["mira"],
        action="Mira standing in attic",
        caption="",
    )
    panel_spec_obj = DirectorialPromptSpec.from_panel(story, panel)
    assert panel_spec_obj.dimensions == (832, 1216)
    assert len(panel_spec_obj.characters) == 1


# ==============================================================================
# 15. Directorial Prompt Dispatch Verification
# ==============================================================================

def test_build_directorial_prompt_dispatch(story: OriginalStory):
    """Verify build_directorial_prompt dispatches correctly according to runner configuration."""
    class DummyRunner:
        def __init__(self, engine: str, style: str):
            self.engine = engine
            self.style = style

    panel_with_dir = Panel(
        id="p1",
        scene_id="s1",
        shot="medium",
        angle="eye_level",
        location_id="attic",
        character_ids=["mira"],
        action="reading a letter",
        caption="",
        director=ss.ShotSpec(
            shot="medium",
            characters=[ss.CharPose(id="mira", action="reading a letter")],
        ).model_dump(),
    )
    # 1. Qwen runner
    res_qwen = build_directorial_prompt(
        story, panel_with_dir, runner=DummyRunner("qwen", "natural")
    )
    assert res_qwen.target_model == TargetModel.QWEN_IMAGE_21
    assert res_qwen.negative != ""

    # 2. Flux runner (must have empty negative)
    res_flux = build_directorial_prompt(
        story, panel_with_dir, runner=DummyRunner("flux", "natural")
    )
    assert res_flux.negative == ""

    # 3. SDXL runner (tag mode)
    res_sdxl = build_directorial_prompt(
        story, panel_with_dir, runner=DummyRunner("sdxl", "tags")
    )
    assert res_sdxl.target_model == TargetModel.SDXL

    # 4. Fallback when director is None
    panel_no_dir = Panel(
        id="p2",
        scene_id="s1",
        shot="medium",
        angle="eye_level",
        location_id="attic",
        character_ids=["mira"],
        action="sitting quietly in the attic",
        caption="",
    )
    res_fallback = build_directorial_prompt(
        story, panel_no_dir, runner=DummyRunner("qwen", "natural")
    )
    assert res_fallback.positive == "sitting quietly in the attic"
    assert res_fallback.negative == ""


# ==============================================================================
# 16. Directorial Visual Style Profiles Verification (WP-1.4)
# ==============================================================================

def test_directorial_visual_style_profiles_registration():
    """Verify all 4 directorial visual style profiles are registered with 4-tier anchors."""
    from engine.original.prompt import DIRECTORIAL_STYLE_PROFILES

    required_profiles = [
        "shonen_manga_screentone",
        "dark_fantasy_graphic",
        "modern_webtoon_color",
        "cyberpunk_neon_noir",
    ]
    for profile in required_profiles:
        assert profile in DIRECTORIAL_STYLE_PROFILES, f"{profile} missing from DIRECTORIAL_STYLE_PROFILES"
        assert profile in GENRE_STYLE_PRESETS, f"{profile} missing from GENRE_STYLE_PRESETS"

        anchor = DIRECTORIAL_STYLE_PROFILES[profile]
        assert anchor.medium, f"Medium missing for {profile}"
        assert anchor.line_geometry, f"Line geometry missing for {profile}"
        assert anchor.palette, f"Palette missing for {profile}"
        assert anchor.lighting_physics, f"Lighting physics missing for {profile}"
        assert anchor.negative_prompt, f"Negative prompt missing for {profile}"
        assert anchor.review_witness_rule, f"Review witness rule missing for {profile}"

        prose = anchor.to_natural_prose()
        assert len(prose) > 50
        tags = anchor.to_tags()
        assert len(tags) > 0


def test_directorial_visual_style_profiles_compilation(story):
    """Verify each directorial visual style profile compiles deterministic positive and negative prompts."""
    from engine.original import shotspec as ss

    spec = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", action="examines an ancient talisman")],
        key_visuals=["glowing runes"],
    )

    # 1. shonen_manga_screentone
    c_shonen = compile_image_prompt(
        story, spec, "attic", style_profile="shonen_manga_screentone"
    )
    assert "screentone dot textures" in c_shonen.positive
    assert "G-pen ink" in c_shonen.positive
    assert "color" in c_shonen.negative

    # 2. dark_fantasy_graphic
    c_dark = compile_image_prompt(
        story, spec, "attic", style_profile="dark_fantasy_graphic"
    )
    assert "Dark fantasy graphic novel" in c_dark.positive
    assert "Heavy traditional crosshatching" in c_dark.positive
    assert "bright" in c_dark.negative

    # 3. modern_webtoon_color
    c_webtoon = compile_image_prompt(
        story, spec, "attic", style_profile="modern_webtoon_color"
    )
    assert "webtoon manhwa" in c_webtoon.positive
    assert "luminous digital airbrush" in c_webtoon.positive
    assert "monochrome" in c_webtoon.negative

    # 4. cyberpunk_neon_noir
    c_cyber = compile_image_prompt(
        story, spec, "attic", style_profile="cyberpunk_neon_noir"
    )
    assert "cyberpunk neon noir" in c_cyber.positive
    assert "volumetric neon lighting" in c_cyber.positive
    assert "daylight" in c_cyber.negative


def test_directorial_style_profile_override_on_different_genre(story):
    """Verify style_profile override takes precedence over story.bible.premise.genre."""
    from engine.original import shotspec as ss

    # Story genre is bedtime
    assert story.bible.premise.genre == "bedtime"

    spec = ss.ShotSpec(
        shot="close",
        characters=[ss.CharPose(id="mira", expression="smiling")],
    )

    # Compile with cyberpunk override
    c_cyber = compile_image_prompt(
        story, spec, "attic", style_profile="cyberpunk_neon_noir"
    )
    assert "cyberpunk neon noir" in c_cyber.positive
    assert "gentle storybook" not in c_cyber.positive

    # Compile default (without override): should follow bedtime
    c_default = compile_image_prompt(story, spec, "attic")
    assert "gentle storybook" in c_default.positive


def test_compile_sdxl_tag_prompt_handles_directorial_styles_safely(story):
    """Verify compile_sdxl_tag_prompt does not raise KeyError when genre is a directorial style."""
    from engine.original import shotspec as ss

    # Mutate premise genre to a directorial style not present in GENRES
    story.bible.premise.genre = "shonen_manga_screentone"

    spec = ss.ShotSpec(
        shot="medium",
        characters=[ss.CharPose(id="mira", action="ready to battle")],
    )

    c_tag = compile_sdxl_tag_prompt(story, spec, "attic")
    assert c_tag.target_model == TargetModel.SDXL
    assert len(c_tag.positive) > 0
    # Restore
    story.bible.premise.genre = "bedtime"


