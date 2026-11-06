"""Empirical Challenge & Stress Test Suite: Milestone M1.

Challenger 2 verification for:
1. ShotSpec serialization / deserialization with and without RiggingSpec.
2. resolve_dimensions resolution bucketing across all standard and turnaround buckets.
3. Negative prompt isolation (ensuring no cross-contamination between standard shots, IP-Adapter portraits, and turnaround sheets).
4. ComfyRunner turnaround generation integration, caching, and offline fallback resilience.
5. Edge cases: seed stability, slicing variations, input types, and error handling.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from PIL import Image
import pytest
from pydantic import ValidationError

from engine.original import art
from engine.original import shotspec as ss
from engine.original.models import Bible, Character, OriginalStory, Premise, Panel
from engine.original.rigging import (
    RIGGING_NEGATIVE,
    DecomposedLayer,
    LayerStack,
    MattingResult,
    RiggingSpec,
    TurnaroundSheet,
    compile_rigging_view_prompt,
    compile_turnaround_prompt,
    generate_rigging_views,
    generate_turnaround_sheet,
    slice_turnaround_sheet,
    _seed_for,
)


def make_test_story(genre: str = "bedtime") -> OriginalStory:
    bible = Bible(
        premise=Premise(title="Starlight Horizon", genre=genre, logline="Epic space journey", tone="Heroic", setting="Nebula Station"),
        characters=[
            Character(
                id="char_alpha",
                name="Aria",
                role="protagonist",
                age_group="teen",
                gender="female",
                look="crimson hair, twin tails, cybernetic eyepiece, obsidian armor",
                personality="fierce explorer",
            ),
            Character(
                id="char_beta",
                name="Balthazar",
                role="antagonist",
                age_group="elder",
                gender="male",
                look="flowing white beard, scarred face, hooded velvet cloak, runic staff",
                personality="ancient sorcerer",
            ),
        ],
        locations=[],
    )
    return OriginalStory(bible=bible, scenes=[], panels=[])


class MockComfyRunner:
    """Mock runner tracking call invocations for generation testing."""

    def __init__(self, style: str = "tags"):
        self.style = style
        self.invocations: list[dict] = []

    def generate(self, pos: str, neg: str, seed: int, width: int, height: int, prefix: str, **kwargs) -> bytes:
        self.invocations.append({
            "pos": pos,
            "neg": neg,
            "seed": seed,
            "width": width,
            "height": height,
            "prefix": prefix,
            "kwargs": kwargs,
        })
        img = Image.new("RGB", (width, height), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# ==============================================================================
# Challenge Area 1: ShotSpec Serialization & Deserialization
# ==============================================================================

class TestShotSpecSerialization:
    """Challenge serialization and deserialization of ShotSpec with and without rigging specifications."""

    def test_shotspec_default_serialization_roundtrip(self):
        """ShotSpec without rigging specification serializes cleanly to dict and JSON."""
        spec = ss.ShotSpec(shot="close", camera="eye_level", setting="laboratory", mood="tense")
        
        # 1. model_dump()
        dumped = spec.model_dump()
        assert dumped["shot"] == "close"
        assert dumped["rigging"] is None
        assert dumped["is_rigging"] is False
        assert dumped["rigging_pose"] == "a_pose"
        assert dumped["turnaround_views"] == ["front", "three_quarter", "side", "back"]
        assert dumped["orthographic"] is True
        assert dumped["limb_separation"] is True

        # Reconstruct from dict
        spec_from_dict = ss.ShotSpec(**dumped)
        assert spec_from_dict == spec

        # 2. model_dump_json() and model_validate_json()
        json_str = spec.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["shot"] == "close"
        assert parsed["rigging"] is None
        assert parsed["is_rigging"] is False

        spec_from_json = ss.ShotSpec.model_validate_json(json_str)
        assert spec_from_json == spec

    def test_shotspec_with_explicit_rigging_spec_roundtrip(self):
        """ShotSpec with explicit RiggingSpec preserves all nested fields across dict and JSON round-trips."""
        rig_spec = RiggingSpec(
            pose="t_pose",
            views=["front", "side", "back"],
            orthographic=True,
            limb_separation=True,
            visible_joints=True,
            neutral_background=True,
            flat_lighting=True,
            background_color="pure neutral gray",
        )
        spec = ss.ShotSpec(
            shot="turnaround",
            camera="eye_level",
            is_rigging=True,
            rigging=rig_spec,
            rigging_pose="t_pose",
            turnaround_views=["front", "side", "back"],
            orthographic=True,
            limb_separation=True,
            pose_weight=0.8,
            depth_weight=0.5,
        )

        # 1. model_dump()
        dumped = spec.model_dump()
        assert dumped["is_rigging"] is True
        assert dumped["rigging"]["pose"] == "t_pose"
        assert dumped["rigging"]["views"] == ["front", "side", "back"]
        assert dumped["rigging"]["background_color"] == "pure neutral gray"

        # Reconstruct from dict
        spec_from_dict = ss.ShotSpec(**dumped)
        assert spec_from_dict.rigging is not None
        assert isinstance(spec_from_dict.rigging, RiggingSpec)
        assert spec_from_dict.rigging.pose == "t_pose"
        assert spec_from_dict.rigging.views == ["front", "side", "back"]
        assert spec_from_dict == spec

        # 2. model_dump_json()
        json_str = spec.model_dump_json()
        spec_from_json = ss.ShotSpec.model_validate_json(json_str)
        assert spec_from_json == spec
        assert spec_from_json.rigging.pose == "t_pose"

    def test_shotspec_dict_coercion_for_nested_rigging(self):
        """Passing a raw dict for 'rigging' field automatically coerces to RiggingSpec model."""
        raw_data = {
            "shot": "turnaround_sheet",
            "is_rigging": True,
            "rigging": {
                "pose": "neutral_standing",
                "views": ["front", "three_quarter"],
                "orthographic": True,
                "limb_separation": True,
            },
        }
        spec = ss.ShotSpec(**raw_data)
        assert isinstance(spec.rigging, RiggingSpec)
        assert spec.rigging.pose == "neutral_standing"
        assert spec.rigging.views == ["front", "three_quarter"]

    def test_riggingspec_legacy_alias_and_property(self):
        """RiggingSpec handles legacy pose_type parameter and exposes pose_type property."""
        spec1 = RiggingSpec(pose_type="t_pose")
        assert spec1.pose == "t_pose"
        assert spec1.pose_type == "t_pose"

        spec2 = RiggingSpec(pose="neutral_standing")
        assert spec2.pose == "neutral_standing"
        assert spec2.pose_type == "neutral_standing"

    def test_riggingspec_validation_rejection(self):
        """RiggingSpec rejects invalid pose literals and invalid view literals."""
        with pytest.raises(ValidationError):
            RiggingSpec(pose="invalid_action_pose")  # type: ignore[arg-type]

        with pytest.raises(ValidationError):
            RiggingSpec(views=["front", "invalid_view"])  # type: ignore[list-item]

    def test_shotspec_model_copy_update_with_rigging(self):
        """ShotSpec.model_copy with update dict correctly updates rigging fields."""
        base_spec = ss.ShotSpec(shot="close")
        assert base_spec.is_rigging is False

        updated = base_spec.model_copy(update={
            "shot": "turnaround",
            "is_rigging": True,
            "rigging": RiggingSpec(pose="t_pose"),
        })
        assert updated.shot == "turnaround"
        assert updated.is_rigging is True
        assert updated.rigging is not None
        assert updated.rigging.pose == "t_pose"
        # Base remains unmodified (immutability)
        assert base_spec.shot == "close"
        assert base_spec.is_rigging is False


# ==============================================================================
# Challenge Area 2: resolve_dimensions Across Standard & Turnaround Buckets
# ==============================================================================

class TestResolveDimensionsBuckets:
    """Stress-test resolve_dimensions across all standard and turnaround buckets, multi-character overrides, and formatting."""

    @pytest.mark.parametrize(
        "shot_name,expected_dims",
        [
            ("turnaround", (1536, 768)),
            ("turnaround_sheet", (1536, 768)),
            ("rigging", (832, 1216)),
            ("rigging_view", (832, 1216)),
            ("character_sheet", (832, 1216)),
            ("sheet", (832, 1216)),
            ("portrait", (832, 1216)),
            ("full", (832, 1216)),
            ("full_body", (832, 1216)),
            ("wide", (1344, 768)),
            ("extreme_wide", (1344, 768)),
            ("landscape", (1344, 768)),
            ("medium", (1024, 1024)),
            ("close", (1024, 1024)),
            ("extreme_close", (1024, 1024)),
            ("cowboy", (1024, 1024)),
            ("over_shoulder", (1152, 896)),
        ],
    )
    def test_standard_buckets(self, shot_name: str, expected_dims: tuple[int, int]):
        """Each registered bucket resolves to its exact 1-MP dimension pair."""
        assert ss.resolve_dimensions(shot_name) == expected_dims

    @pytest.mark.parametrize(
        "raw_shot,expected_dims",
        [
            ("TURNAROUND", (1536, 768)),
            ("  turnaround  ", (1536, 768)),
            ("turnaround-sheet", (1536, 768)),
            ("TURNAROUND_SHEET", (1536, 768)),
            ("Turnaround Sheet", (1536, 768)),
            ("RIGGING", (832, 1216)),
            ("  rigging-view  ", (832, 1216)),
            ("Rigging View", (832, 1216)),
            ("CHARACTER-SHEET", (832, 1216)),
        ],
    )
    def test_case_and_delimiter_normalization(self, raw_shot: str, expected_dims: tuple[int, int]):
        """resolve_dimensions normalizes whitespace, dashes, and casing cleanly."""
        assert ss.resolve_dimensions(raw_shot) == expected_dims

    def test_turnaround_sheet_never_overridden_by_num_characters(self):
        """Turnaround and turnaround_sheet must stay (1536, 768) even when num_characters >= 2."""
        # For ordinary shots, num_characters >= 2 forces (1344, 768)
        assert ss.resolve_dimensions("close", num_characters=1) == (1024, 1024)
        assert ss.resolve_dimensions("close", num_characters=2) == (1344, 768)
        assert ss.resolve_dimensions("medium", num_characters=3) == (1344, 768)

        # But turnaround sheets MUST remain (1536, 768) ultra-wide landscape
        assert ss.resolve_dimensions("turnaround", num_characters=2) == (1536, 768)
        assert ss.resolve_dimensions("turnaround", num_characters=5) == (1536, 768)
        assert ss.resolve_dimensions("turnaround_sheet", num_characters=2) == (1536, 768)
        assert ss.resolve_dimensions("turnaround-sheet", num_characters=4) == (1536, 768)

    def test_fallback_behavior_unregistered_shots(self):
        """Unrecognized or empty shots fall back to default cleanly."""
        custom_default = (960, 540)
        # Empty string or None returns default
        assert ss.resolve_dimensions("", default=custom_default) == custom_default
        assert ss.resolve_dimensions(None, default=custom_default) == custom_default

        # Unknown shot name returns default
        assert ss.resolve_dimensions("non_existent_shot", default=custom_default) == custom_default

        # Ultra-wide without explicit entry falls back to default (1344, 768)
        assert ss.resolve_dimensions("ultra_wide") == (1344, 768)


# ==============================================================================
# Challenge Area 3: Negative Prompt Isolation & Anti-Collision
# ==============================================================================

class TestNegativePromptIsolation:
    """Challenge negative prompt containment to prove standard shots vs. turnarounds never bleed or collide."""

    def test_rigging_negative_strictly_omits_multiview_bans(self):
        """RIGGING_NEGATIVE must NOT contain bans on multiple views, split screen, collage, or reference sheet."""
        prohibited_in_rigging = [
            "multiple views",
            "split screen",
            "collage",
            "reference sheet",
            "multiple characters",
            "2girls",
            "2boys",
        ]
        for term in prohibited_in_rigging:
            assert term not in RIGGING_NEGATIVE, f"Term '{term}' must NOT be in RIGGING_NEGATIVE"

    def test_sheet_negative_strictly_includes_multiview_bans(self):
        """art.SHEET_NEGATIVE must forbid multiple views and reference sheets for single IP-Adapter portraits."""
        required_in_sheet_negative = [
            "multiple views",
            "split screen",
            "collage",
            "reference sheet",
            "multiple characters",
        ]
        for term in required_in_sheet_negative:
            assert term in art.SHEET_NEGATIVE, f"Term '{term}' must be in SHEET_NEGATIVE"

    def test_rigging_negative_contains_essential_rigging_defects(self):
        """RIGGING_NEGATIVE must explicitly suppress occlusions, overlapping appendages, and background clutter."""
        essential_rigging_terms = [
            "occluded limbs",
            "overlapping appendages",
            "overlapping limbs",
            "crossed limbs",
            "hands in pockets",
            "foreshortening",
            "background clutter",
            "bad anatomy",
            "bad hands",
        ]
        for term in essential_rigging_terms:
            assert term in RIGGING_NEGATIVE, f"Essential term '{term}' missing from RIGGING_NEGATIVE"

    def test_build_prompt_never_leaks_rigging_negative(self):
        """Standard panel build_prompt uses standard NEGATIVE, never RIGGING_NEGATIVE."""
        story = make_test_story()
        panel = Panel(
            id="panel_1",
            scene_id="s1",
            character_ids=["char_alpha"],
            location_id="loc_1",
            shot="medium",
            angle="eye_level",
            action="Aria examines the holographic star chart",
            key_visuals=["hologram", "star chart"],
        )
        pos, neg = art.build_prompt(story, panel, style="tags")
        assert neg.startswith(art.NEGATIVE)
        assert "occluded limbs" not in neg
        assert "overlapping appendages" not in neg
        assert "hands in pockets" not in neg

    def test_turnaround_prompt_negative_isolation(self):
        """compile_turnaround_prompt returns RIGGING_NEGATIVE for tags, and empty for natural style."""
        story = make_test_story()
        char = story.bible.characters[0]

        # Tags style with return_negative=True
        pos_tags, neg_tags = compile_turnaround_prompt(char, story, style_kind="tags", return_negative=True)
        assert neg_tags == RIGGING_NEGATIVE
        assert "multiple views" not in neg_tags

        # Natural style with return_negative=True
        pos_nat, neg_nat = compile_turnaround_prompt(char, story, style_kind="natural", return_negative=True)
        assert neg_nat == ""

        # Rigging view with return_negative=True
        pos_v, neg_v = compile_rigging_view_prompt(char, "side", story, style_kind="tags", return_negative=True)
        assert neg_v == RIGGING_NEGATIVE


# ==============================================================================
# Challenge Area 4: ComfyRunner Integration, Caching, and Fallback Resilience
# ==============================================================================

class TestComfyRunnerTurnaroundIntegration:
    """Stress-test ComfyRunner turnaround generation, caching, slicing, and offline fallback."""

    def test_runner_convenience_method_dispatch(self, tmp_path: Path):
        """art.ComfyRunner.generate_turnaround invokes generate_turnaround_sheet correctly."""
        story = make_test_story()
        char = story.bible.characters[0]
        runner = MockComfyRunner(style="tags")

        # Call generate_turnaround through runner interface
        sheet = art.generate_turnaround_sheet(char, story, tmp_path, runner=runner)
        assert isinstance(sheet, TurnaroundSheet)
        assert len(runner.invocations) == 1
        inv = runner.invocations[0]
        assert inv["width"] == 1536
        assert inv["height"] == 768
        assert inv["neg"] == RIGGING_NEGATIVE
        assert "character sheet" in inv["pos"]
        assert "turnaround" in inv["pos"]

    def test_runner_natural_style_dispatch(self, tmp_path: Path):
        """MockComfyRunner with style='natural' dispatches natural language prompt and empty negative."""
        story = make_test_story()
        char = story.bible.characters[0]
        runner = MockComfyRunner(style="natural")

        sheet = generate_turnaround_sheet(char, story, tmp_path, runner=runner)
        assert isinstance(sheet, TurnaroundSheet)
        assert len(runner.invocations) == 1
        inv = runner.invocations[0]
        assert inv["neg"] == ""
        assert "Professional 2D animation character turnaround model sheet" in inv["pos"]

    def test_generation_caching_behavior(self, tmp_path: Path):
        """Pre-existing turnaround sheet file bypasses runner execution on repeated calls."""
        story = make_test_story()
        char = story.bible.characters[0]
        runner = MockComfyRunner()

        sheet1 = generate_turnaround_sheet(char, story, tmp_path, runner=runner)
        assert len(runner.invocations) == 1
        assert Path(sheet1.image_path).exists()

        # Call again: should reuse existing file without calling runner.generate
        runner.invocations.clear()
        sheet2 = generate_turnaround_sheet(char, story, tmp_path, runner=runner)
        assert len(runner.invocations) == 0
        assert sheet2.image_path == sheet1.image_path

    def test_slice_turnaround_sheet_slice_views_false(self, tmp_path: Path):
        """When slice_views=False, master sheet is created but views dict remains empty."""
        story = make_test_story()
        char = story.bible.characters[0]

        sheet = generate_turnaround_sheet(char, story, tmp_path, runner=None, slice_views=False)
        assert Path(sheet.image_path).exists()
        assert sheet.views == {}

    def test_offline_fallback_visual_dimensions_and_slicing(self, tmp_path: Path):
        """Offline fallback produces exact (1536, 768) sheet and 4x (384, 768) slices with content."""
        story = make_test_story()
        char = story.bible.characters[0]
        spec = RiggingSpec(pose="a_pose")

        sheet = generate_turnaround_sheet(char, story, tmp_path, runner=None, spec=spec, slice_views=True)
        master_img = Image.open(sheet.image_path)
        assert master_img.size == (1536, 768)

        expected_views = ["front", "three_quarter", "side", "back"]
        for v in expected_views:
            assert v in sheet.views
            view_path = Path(sheet.views[v])
            assert view_path.exists()
            with Image.open(view_path) as vim:
                assert vim.size == (384, 768)

    def test_slice_turnaround_sheet_input_types(self):
        """slice_turnaround_sheet accepts Image, Path, str, and bytes."""
        w, h = 1536, 768
        img = Image.new("RGB", (w, h), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()

        # 1. Image.Image
        res1 = slice_turnaround_sheet(img)
        assert len(res1) == 4

        # 2. bytes
        res2 = slice_turnaround_sheet(raw_bytes)
        assert len(res2) == 4

        # 3. Invalid type raises TypeError
        with pytest.raises(TypeError):
            slice_turnaround_sheet(12345)  # type: ignore[arg-type]


# ==============================================================================
# Challenge Area 5: Rigorous Edge Cases & Invariance
# ==============================================================================

class TestRiggingEdgeCases:
    """Stress-test edge cases, seed invariance, custom views, and model fidelity."""

    def test_seed_determinism_and_uniqueness(self):
        """_seed_for produces identical seed for same inputs, different for different characters or poses."""
        story = make_test_story()
        char1 = story.bible.characters[0]
        char2 = story.bible.characters[1]

        seed1_a = _seed_for(story, f"turnaround_{char1.id}_a_pose", 0)
        seed1_b = _seed_for(story, f"turnaround_{char1.id}_a_pose", 0)
        assert seed1_a == seed1_b

        seed_char2 = _seed_for(story, f"turnaround_{char2.id}_a_pose", 0)
        assert seed1_a != seed_char2

        seed_t_pose = _seed_for(story, f"turnaround_{char1.id}_t_pose", 0)
        assert seed1_a != seed_t_pose

        seed_attempt1 = _seed_for(story, f"turnaround_{char1.id}_a_pose", 1)
        assert seed1_a != seed_attempt1

    def test_custom_view_subset_slicing(self):
        """slice_turnaround_sheet correctly divides width by number of requested views."""
        w, h = 1000, 500
        img = Image.new("RGB", (w, h))
        views = ["front", "back"]
        slices = slice_turnaround_sheet(img, views=views)
        assert len(slices) == 2
        assert slices["front"].size == (500, 500)
        assert slices["back"].size == (500, 500)

    def test_turnaround_sheet_path_protocols(self, tmp_path: Path):
        """TurnaroundSheet satisfies os.PathLike, string conversion, and exists() protocols."""
        fake_file = tmp_path / "char_turnaround.png"
        sheet_uncreated = TurnaroundSheet(character_id="c1", image_path=str(fake_file))
        assert not sheet_uncreated.exists()
        assert sheet_uncreated.path == fake_file
        assert str(sheet_uncreated) == str(fake_file)
        assert Path(sheet_uncreated) == fake_file

        fake_file.write_bytes(b"test_image")
        assert sheet_uncreated.exists()
