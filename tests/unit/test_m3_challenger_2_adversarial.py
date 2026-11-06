"""Adversarial Challenge & Stress Test Suite: Milestone M3.

Challenger 2 verification for:
1. Dimension Compatibility: divisibility policies (16-multiple for image, 32-multiple for video) across all standard shot buckets, custom dimensions, and edge cases.
2. Negative Prompt Contracts: strict isolation between Flux/natural (empty negative) and Qwen Image 2.1 (rich defect suppression tokens), SDXL tags, and Rigging negatives.
3. MiniMax Fast H3 Video & Temporal Stability Guardrails: kinematics, motion pacing, bokeh directives, 6-heading schema, and temporal anti-morphing tokens.
4. Robustness against adversarial, boundary, and malformed inputs.
"""
from __future__ import annotations

import random
from typing import Any
import pytest

from engine.original import shotspec as ss
from engine.original import art
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
    UNIVERSAL_VIDEO_NEGATIVE_PROMPT,
    VIDEO_BOKEH_DIRECTIVE,
    VIDEO_SECONDARY_DYNAMICS,
    VIDEO_TEMPORAL_INVARIANCE,
    CompiledPrompt,
    DirectorialPromptSpec,
    PromptCompiler,
    TargetModel,
    build_directorial_prompt,
    compile_image_prompt,
    compile_video_prompt,
    resolve_video_dimensions,
)
from tests.unit.test_original_story import full_bible


def make_test_story(genre: str = "bedtime") -> OriginalStory:
    """Helper creating a standard story instance with custom genre."""
    bible = full_bible()
    bible.premise.genre = genre
    return OriginalStory(bible=bible, scenes=[], panels=[])


# ==============================================================================
# Challenge Area 1: Dimension Compatibility & Divisibility Policies
# ==============================================================================

class TestDimensionDivisibilityPolicies:
    """Adversarially challenge dimension divisibility policies:
    - All image dimensions emitted by compile_image_prompt must be multiples of 16.
    - All video dimensions emitted by compile_video_prompt must be multiples of 32.
    """

    def test_all_shot_dimensions_are_multiples_of_16(self):
        """Every single bucket in ss.SHOT_DIMENSIONS must have width and height divisible by 16."""
        assert len(ss.SHOT_DIMENSIONS) >= 15, "SHOT_DIMENSIONS must contain all standard shot buckets"
        for shot_name, dims in ss.SHOT_DIMENSIONS.items():
            w, h = dims
            assert w % 16 == 0, f"Shot '{shot_name}' width {w} is not divisible by 16"
            assert h % 16 == 0, f"Shot '{shot_name}' height {h} is not divisible by 16"
            assert w > 0 and h > 0, f"Shot '{shot_name}' dimensions must be positive"

    def test_compile_image_prompt_standard_shot_buckets_divisible_by_16(self):
        """compile_image_prompt across all registered shots must emit dimensions divisible by 16."""
        story = make_test_story("bedtime")
        for shot in ss.SHOT_DIMENSIONS:
            spec = ss.ShotSpec(shot=shot, characters=[ss.CharPose(id="mira")])
            compiled = PromptCompiler.compile_image_prompt(story, spec, "attic")
            w, h = compiled.dimensions
            assert w % 16 == 0, f"compile_image_prompt shot '{shot}' width {w} not divisible by 16"
            assert h % 16 == 0, f"compile_image_prompt shot '{shot}' height {h} not divisible by 16"

    def test_compile_image_prompt_character_scaling_dimensions_divisible_by_16(self):
        """Single character vs 2+ characters aspect ratio scaling preserves multiple of 16."""
        story = make_test_story("bedtime")

        # 1 character close: square (1024, 1024)
        s1 = ss.ShotSpec(shot="close", characters=[ss.CharPose(id="mira")])
        c1 = PromptCompiler.compile_image_prompt(story, s1, "attic")
        assert c1.dimensions == (1024, 1024)
        assert c1.dimensions[0] % 16 == 0 and c1.dimensions[1] % 16 == 0

        # 2 characters close: landscape override (1344, 768)
        s2 = ss.ShotSpec(shot="close", characters=[ss.CharPose(id="mira"), ss.CharPose(id="pip")])
        c2 = PromptCompiler.compile_image_prompt(story, s2, "attic")
        assert c2.dimensions == (1344, 768)
        assert c2.dimensions[0] % 16 == 0 and c2.dimensions[1] % 16 == 0

        # Turnaround sheet: ultra-wide (1536, 768)
        s_turn = ss.ShotSpec(shot="turnaround", characters=[ss.CharPose(id="mira")])
        c_turn = PromptCompiler.compile_image_prompt(story, s_turn, "attic")
        assert c_turn.dimensions == (1536, 768)
        assert c_turn.dimensions[0] % 16 == 0 and c_turn.dimensions[1] % 16 == 0

    def test_resolve_video_dimensions_fuzzing_strict_divisibility_by_32(self):
        """resolve_video_dimensions must snap ANY dimension to a valid multiple of 32 (>= 32)."""
        # Test standard dimensions
        standard_cases = [
            ((1344, 768), (1344, 768)),
            ((1920, 1080), (1920, 1088)),  # 1080 -> 1088 (34 * 32)
            ((1280, 720), (1280, 704)),    # 720/32=22.5 -> round-half-to-even = 22 -> 704
            ((1024, 1024), (1024, 1024)),
            ((832, 1216), (832, 1216)),
            ((1536, 768), (1536, 768)),
        ]
        for inp, expected in standard_cases:
            res = resolve_video_dimensions(dimensions=inp)
            assert res == expected, f"Input {inp} expected {expected}, got {res}"
            assert res[0] % 32 == 0
            assert res[1] % 32 == 0

        # Boundary and adversarial cases
        adversarial_cases = [
            (0, 0),
            (1, 1),
            (15, 17),
            (31, 33),
            (100, 100),
            (777, 999),
            (4095, 4097),
            (-50, -100),
        ]
        for w_in, h_in in adversarial_cases:
            w_out, h_out = resolve_video_dimensions(dimensions=(w_in, h_in))
            assert w_out >= 32, f"Width {w_out} is less than minimum 32 for input {w_in}"
            assert h_out >= 32, f"Height {h_out} is less than minimum 32 for input {h_in}"
            assert w_out % 32 == 0, f"Width {w_out} is not divisible by 32 for input {w_in}"
            assert h_out % 32 == 0, f"Height {h_out} is not divisible by 32 for input {h_in}"

        # Pseudo-random fuzzing (100 iterations)
        rng = random.Random(42)
        for _ in range(100):
            rw = rng.randint(-100, 5000)
            rh = rng.randint(-100, 5000)
            res_w, res_h = resolve_video_dimensions(dimensions=(rw, rh))
            assert res_w >= 32
            assert res_h >= 32
            assert res_w % 32 == 0
            assert res_h % 32 == 0

    def test_compile_video_prompt_dimensions_always_divisible_by_32(self):
        """PromptCompiler.compile_video_prompt must always emit dimensions divisible by 32."""
        # 1. Default dimensions
        c_def = PromptCompiler.compile_video_prompt()
        assert c_def.dimensions == (1344, 768)
        assert c_def.dimensions[0] % 32 == 0 and c_def.dimensions[1] % 32 == 0

        # 2. From ShotSpec with square framing (1024, 1024)
        sp_square = ss.ShotSpec(shot="medium")
        c_sq = PromptCompiler.compile_video_prompt(spec=sp_square)
        assert c_sq.dimensions[0] % 32 == 0 and c_sq.dimensions[1] % 32 == 0

        # 3. Custom non-multiple dimensions passed explicitly
        c_custom = PromptCompiler.compile_video_prompt(dimensions=(1920, 1080))
        assert c_custom.dimensions == (1920, 1088)
        assert c_custom.dimensions[0] % 32 == 0 and c_custom.dimensions[1] % 32 == 0


# ==============================================================================
# Challenge Area 2: Negative Prompt Contracts & Engine Isolation
# ==============================================================================

class TestNegativePromptContracts:
    """Adversarially challenge negative prompt contracts:
    - Target 'flux' and 'natural' must ALWAYS receive empty negative prompt ("").
    - Target Qwen Image 2.1 must receive comprehensive defect tokens.
    - Target SDXL must receive Danbooru tag-style negative.
    - Rigging specifications must receive RIGGING_NEGATIVE and never multiview bans.
    """

    def test_flux_target_negative_is_strictly_empty(self):
        """Target 'flux' or 'natural' in compile_image_prompt must produce an empty negative prompt."""
        story = make_test_story("bedtime")
        spec = ss.ShotSpec(
            shot="medium",
            characters=[ss.CharPose(id="mira", action="reading a book")],
            key_visuals=["glowing book"],
        )

        for tgt in ("flux", "FLUX", "Flux", "natural", "NATURAL"):
            res = PromptCompiler.compile_image_prompt(story, spec, "attic", target=tgt)
            assert res.negative == "", f"Target '{tgt}' produced non-empty negative prompt: {res.negative}"

    def test_qwen_image_21_target_has_rich_defect_tokens(self):
        """Target Qwen Image 2.1 must produce rich anatomical and spatial defect suppression tokens."""
        story = make_test_story("bedtime")
        spec = ss.ShotSpec(
            shot="medium",
            characters=[ss.CharPose(id="mira", action="reading a book")],
        )

        for tgt in (TargetModel.QWEN_IMAGE_21, "qwen_image_21", "qwen"):
            res = PromptCompiler.compile_image_prompt(story, spec, "attic", target=tgt)
            assert res.negative != "", f"Target '{tgt}' should not produce empty negative prompt"
            # Verify critical anatomical defect tokens
            critical_tokens = [
                "bad anatomy",
                "deformed hands",
                "extra fingers",
                "missing fingers",
                "mutated hands",
                "broken wrists",
                "floating objects",
                "disconnected grip",
            ]
            for tok in critical_tokens:
                assert tok in res.negative, f"Target '{tgt}' missing defect token: '{tok}'"

    def test_sdxl_target_has_booru_tags_negative(self):
        """Target SDXL must produce Danbooru-style negative prompt tokens."""
        story = make_test_story("bedtime")
        spec = ss.ShotSpec(shot="medium", characters=[ss.CharPose(id="mira")])

        for tgt in (TargetModel.SDXL, "sdxl", "tags"):
            res = PromptCompiler.compile_image_prompt(story, spec, "attic", target=tgt)
            assert "bad-hands-5" in res.negative or "bad anatomy" in res.negative or "lowres" in res.negative
            assert res.target_model == TargetModel.SDXL

    def test_art_build_prompt_engine_dispatch(self):
        """art.build_prompt must cleanly route runner.engine to appropriate negative contract."""
        story = make_test_story("bedtime")
        panel = Panel(
            id="p1",
            scene_id="s1",
            location_id="attic",
            shot="medium",
            angle="eye_level",
            action="Mira sits by the glowing fireplace reading",
            character_ids=["mira"],
            key_visuals=["glowing fireplace"],
            director={"shot": "medium", "camera": "eye_level", "characters": [{"id": "mira", "action": "sitting"}]},
        )

        # 1. Runner with engine='flux'
        class MockFluxRunner:
            engine = "flux"
            style = "natural"

        pos_flux, neg_flux = art.build_prompt(story, panel, runner=MockFluxRunner())
        assert neg_flux == "", f"Flux runner must receive empty negative, got: '{neg_flux}'"

        # 2. Runner with engine='qwen'
        class MockQwenRunner:
            engine = "qwen"
            style = "natural"

        pos_qwen, neg_qwen = art.build_prompt(story, panel, runner=MockQwenRunner())
        assert "bad anatomy" in neg_qwen
        assert "deformed hands" in neg_qwen

        # 3. Runner with style='tags' (SDXL)
        class MockSDXLRunner:
            engine = "sdxl"
            style = "tags"

        pos_sdxl, neg_sdxl = art.build_prompt(story, panel, runner=MockSDXLRunner())
        assert "bad-hands-5" in neg_sdxl or "bad anatomy" in neg_sdxl or "lowres" in neg_sdxl

    def test_turnaround_rigging_negative_isolation(self):
        """Rigging / turnaround shots must emit RIGGING_NEGATIVE without multiview bans."""
        story = make_test_story("bedtime")
        spec_turn = ss.ShotSpec(shot="turnaround", characters=[ss.CharPose(id="mira")])
        res = PromptCompiler.compile_image_prompt(story, spec_turn, "attic", target=TargetModel.QWEN_IMAGE_21)

        assert res.negative == RIGGING_NEGATIVE
        assert "occluded limbs" in res.negative
        assert "overlapping appendages" in res.negative
        # Multiview bans MUST be absent
        assert "multiple views" not in res.negative
        assert "split screen" not in res.negative
        assert "collage" not in res.negative


# ==============================================================================
# Challenge Area 3: MiniMax H3 Temporal Stability Guardrails
# ==============================================================================

class TestMiniMaxH3TemporalGuardrails:
    """Adversarially challenge MiniMax Fast H3 video compilation and temporal guardrails."""

    def test_temporal_negative_contains_all_15_essential_artifact_suppressions(self):
        """UNIVERSAL_VIDEO_NEGATIVE_PROMPT must contain all 15 core temporal suppression tokens."""
        compiled = PromptCompiler.compile_video_prompt()
        neg = compiled.negative

        expected_suppressions = [
            "fast jerky motion",
            "abrupt camera jump cut",
            "morphing face",
            "distorted hands",
            "flickering",
            "twitching",
            "bad anatomy",
            "jittery artifacts",
            "melted face",
            "blurry facial features",
            "faceless pedestrians",
            "temporal tearing",
            "frame stutter",
            "rapid zoom",
            "disfigured limbs",
        ]
        for term in expected_suppressions:
            assert term in neg, f"Temporal negative missing critical suppression: '{term}'"

    def test_positive_motion_kinematics_and_temporal_invariance(self):
        """Positive motion prompt must include camera kinematics, cloth/hair dynamics, and 24fps invariance."""
        compiled = PromptCompiler.compile_video_prompt(camera_direction="pan_right", intensity="balanced")
        pos = compiled.positive

        assert "Gentle camera pan from left to right" in pos
        assert "cloth and hair dynamics" in pos
        assert "consistent character appearance across all frames" in pos
        assert "24fps smooth motion" in pos

    def test_wide_shot_triggers_bokeh_directive(self):
        """Wide shots must automatically inject the shallow depth of field / bokeh directive."""
        sp_wide = ss.ShotSpec(shot="wide")
        c_wide = PromptCompiler.compile_video_prompt(spec=sp_wide)
        assert VIDEO_BOKEH_DIRECTIVE in c_wide.positive

        sp_ext_wide = ss.ShotSpec(shot="extreme_wide")
        c_ext_wide = PromptCompiler.compile_video_prompt(spec=sp_ext_wide)
        assert VIDEO_BOKEH_DIRECTIVE in c_ext_wide.positive

        # Close shot should not have bokeh directive unless explicit
        sp_close = ss.ShotSpec(shot="close")
        c_close = PromptCompiler.compile_video_prompt(spec=sp_close)
        assert VIDEO_BOKEH_DIRECTIVE not in c_close.positive

        # Explicit bokeh_background=True injects it on any shot
        c_close_bokeh = PromptCompiler.compile_video_prompt(spec=sp_close, bokeh_background=True)
        assert VIDEO_BOKEH_DIRECTIVE in c_close_bokeh.positive

    def test_style_6_heading_schema_structural_integrity(self):
        """6-heading schema mode must strictly format all 6 headings and retention rules."""
        compiled = PromptCompiler.compile_video_prompt(
            style_6_heading=True,
            camera_direction="orbit",
            soundscape="Gentle summer rain on wooden window pane",
            music="Soft acoustic guitar",
        )
        pos = compiled.positive

        required_headings = [
            "subject_definitions:\n",
            "summary:\n",
            "retention_analysis:\n",
            "detailed_description:\n",
            "overall_soundscape:\n",
            "non_diegetic_music:\n",
        ]
        for h in required_headings:
            assert h in pos, f"6-heading prompt missing header: {repr(h)}"

        # Retention analysis must contain strict anti-morphing rules
        assert "Retain exact facial geometry" in pos
        assert "Zero morphing of facial features" in pos
        assert "zero digit deformities" in pos
        assert "zero clothing alteration across all frames" in pos

        # Audio fields must match inputs
        assert "Gentle summer rain on wooden window pane" in pos
        assert "Soft acoustic guitar" in pos


# ==============================================================================
# Challenge Area 4: Boundary & Adversarial Input Robustness
# ==============================================================================

class TestAdversarialInputRobustness:
    """Stress-test edge cases, boundary conditions, and unexpected inputs."""

    def test_compile_video_prompt_with_malformed_inputs(self):
        """compile_video_prompt survives None, empty, and unusual inputs gracefully."""
        # 1. spec=None
        c1 = PromptCompiler.compile_video_prompt(spec=None)
        assert isinstance(c1, CompiledPrompt)
        assert c1.dimensions == (1344, 768)

        # 2. Unknown camera direction falls back to push_in
        c2 = PromptCompiler.compile_video_prompt(camera_direction="hyper_speed_zoom_unknown")
        assert CAMERA_KINEMATICS["push_in"] in c2.positive

        # 3. fx_tags as varied types
        c3 = PromptCompiler.compile_video_prompt(fx_tags=["film_grain", "vignette", ""])
        assert "film_grain" in c3.positive
        assert "vignette" in c3.positive

        c4 = PromptCompiler.compile_video_prompt(fx_tags="lens_flare")
        assert "lens_flare" in c4.positive

    def test_compiled_prompt_container_ergonomics_and_immutability(self):
        """CompiledPrompt satisfies tuple unpacking, sequence indexing, and len."""
        cp = CompiledPrompt(
            positive="A serene illustration.",
            negative="blurry",
            dimensions=(1024, 1024),
            target_model=TargetModel.QWEN_IMAGE_21,
        )

        # 1. Tuple unpacking
        pos, neg = cp
        assert pos == "A serene illustration."
        assert neg == "blurry"

        # 2. Sequence indexing
        assert cp[0] == "A serene illustration."
        assert cp[1] == "blurry"
        with pytest.raises(IndexError):
            _ = cp[2]

        # 3. Length
        assert len(cp) == 2

        # 4. as_tuple export
        assert cp.as_tuple() == ("A serene illustration.", "blurry")
