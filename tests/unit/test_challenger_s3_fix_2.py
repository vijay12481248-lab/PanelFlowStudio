"""Empirical Challenger Suite: Sprint 3 Fix Adversarial Verification.

Tests prompt template casing consistency, turnaround dimensions (1536x768, 2:1 ratio, 16-multiple),
pure white background (255, 255, 255) image/prompt contracts, and ComfyUI patch slot regression guards.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from PIL import Image
import pytest

from engine.comfyui.art import ArtEngine, ComfyImageGenerationError, _patch_workflow
from engine.comfyui.client import ComfyUIClient
from engine.comfyui.registry import ComfyWorkflowRegistry
from engine.original import shotspec
from engine.original.models import Bible, Character, OriginalStory, Panel, Premise, Scene
from engine.original.rigging import (
    RIGGING_NATURAL_TEMPLATES,
    RIGGING_NEGATIVE,
    RiggingSpec,
    _create_offline_turnaround_image,
    compile_rigging_view_prompt,
    compile_turnaround_prompt,
    slice_turnaround_sheet,
)
from engine.original.story import init_bible_turnarounds, init_character_turnaround


def _make_story(
    genre: str = "bedtime",
    char_id: str = "mira",
    char_name: str = "Mira",
    char_look: str = "short brown hair, green eyes, yellow raincoat, red boots",
    species: str = "human",
    gender: str = "female",
    age_group: str = "child",
) -> tuple[OriginalStory, Character]:
    char = Character(
        id=char_id,
        name=char_name,
        role="protagonist",
        age_group=age_group,
        look=char_look,
        personality="curious",
        species=species,
        gender=gender,
    )
    bible = Bible(
        premise=Premise(title="Test Story", genre=genre, logline="L", tone="T", setting="S"),
        characters=[char],
        locations=[],
    )
    story = OriginalStory(bible=bible, scenes=[], panels=[])
    return story, char


# ==============================================================================
# 1. Prompt Template Casing Stress Tests
# ==============================================================================

class TestTurnaroundPromptTemplateCasing:
    """Adversarially verify that compile_turnaround_prompt produces uppercase
    'No text, no captions, no speech bubbles, no watermark.' across genres,
    character configurations, poses, and invocation styles.
    """

    TARGET_SENTENCE = "No text, no captions, no speech bubbles, no watermark."

    def test_rigging_templates_contain_exact_casing(self):
        """Templates in RIGGING_NATURAL_TEMPLATES must directly embed the exact sentence."""
        assert self.TARGET_SENTENCE in RIGGING_NATURAL_TEMPLATES["turnaround"]
        assert self.TARGET_SENTENCE in RIGGING_NATURAL_TEMPLATES["single_view"]

    @pytest.mark.parametrize(
        "genre",
        [
            "bedtime",
            "shonen",
            "romance",
            "scifi",
            "horror",
            "cyberpunk",
            "fantasy",
            "mystery",
            "nonexistent_genre_xyz",
        ],
    )
    def test_casing_across_genres(self, genre: str):
        """Uppercase casing must be present across all registered and unregistered genres."""
        story, char = _make_story(genre=genre)
        prompt = compile_turnaround_prompt(char, story, style_kind="natural")
        assert isinstance(prompt, str)
        assert self.TARGET_SENTENCE in prompt, f"Failed for genre={genre}: {prompt}"

    @pytest.mark.parametrize(
        "char_kwargs",
        [
            {"char_id": "c1", "char_name": "Standard Girl", "char_look": "blonde ponytail, blue eyes"},
            {"char_id": "c2", "char_name": "Kael'thas", "char_look": "long golden hair, fiery red robe, glowing orbs"},
            {"char_id": "c3", "char_name": "Mīrä-★", "char_look": "cybernetic eye, chrome arm, neon jacket"},
            {"char_id": "c4", "char_name": "Empty Look", "char_look": ""},
            {"char_id": "c5", "char_name": "Punctuation!", "char_look": "look with 'single' and \"double\" quotes, commas,; colons"},
            {"char_id": "c6", "char_name": "NonHuman", "species": "alien", "gender": "non-binary", "char_look": "blue skin, four arms"},
            {"char_id": "c7", "char_name": "Elderly", "age_group": "elderly", "char_look": "wrinkled skin, white beard"},
        ],
    )
    def test_casing_across_character_specs(self, char_kwargs: dict):
        """Uppercase casing must be invariant to character fields, unicode, or punctuation."""
        story, char = _make_story(**char_kwargs)
        prompt = compile_turnaround_prompt(char, story, style_kind="natural")
        assert isinstance(prompt, str)
        assert self.TARGET_SENTENCE in prompt, f"Failed for character {char_kwargs}: {prompt}"

    @pytest.mark.parametrize("pose", ["a_pose", "t_pose", "neutral_standing"])
    def test_casing_across_poses(self, pose: str):
        """Uppercase casing must persist across all valid orthographic poses."""
        story, char = _make_story()
        spec = RiggingSpec(pose=pose)  # type: ignore[arg-type]
        prompt = compile_turnaround_prompt(char, story, spec=spec, style_kind="natural")
        assert self.TARGET_SENTENCE in prompt

    def test_invalid_pose_raises_validation_error(self):
        """RiggingSpec strictly guards against invalid poses via Pydantic Literal validation."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RiggingSpec(pose="dynamic_custom")  # type: ignore[arg-type]

    def test_casing_with_negative_kwargs(self):
        """Uppercase casing must be preserved when tuple (pos, neg) is requested."""
        story, char = _make_story()
        spec = RiggingSpec()

        # return_negative=True
        pos, neg = compile_turnaround_prompt(char, story, spec=spec, style_kind="natural", return_negative=True)
        assert self.TARGET_SENTENCE in pos
        assert neg == ""

        # with_negative=True
        pos2, neg2 = compile_turnaround_prompt(char, story, spec=spec, style_kind="natural", with_negative=True)
        assert self.TARGET_SENTENCE in pos2
        assert neg2 == ""

    @pytest.mark.parametrize("view", ["front", "three_quarter", "side", "back"])
    def test_single_view_prompt_casing(self, view: str):
        """compile_rigging_view_prompt must also yield uppercase casing across all 4 views."""
        story, char = _make_story()
        prompt = compile_rigging_view_prompt(char, view=view, story=story, style_kind="natural")
        assert isinstance(prompt, str)
        assert self.TARGET_SENTENCE in prompt, f"Failed for view={view}: {prompt}"


# ==============================================================================
# 2. Turnaround Dimensions & Pure White Background Stress Tests
# ==============================================================================

class TestTurnaroundDimensionsAndPureWhiteBackground:
    """Adversarially verify that turnaround master sheets adhere to:
    1. Exact 1536x768 dimensions (2:1 aspect ratio, integer multiples of 16).
    2. Slices conforming to 384x768 (integer multiples of 16).
    3. Solid, seamless clean pure white background (255, 255, 255) across canvas and prompts.
    """

    def test_dimension_constants_and_multiples_of_16(self):
        """Both SHOT_DIMENSIONS entries must be (1536, 768) and divisible by 16."""
        for key in ("turnaround", "turnaround_sheet"):
            w, h = shotspec.SHOT_DIMENSIONS[key]
            assert (w, h) == (1536, 768), f"{key} dimensions mismatch"
            assert w / h == 2.0, f"{key} aspect ratio must be 2:1"
            assert w % 16 == 0, f"{key} width {w} must be multiple of 16"
            assert h % 16 == 0, f"{key} height {h} must be multiple of 16"

    def test_resolve_dimensions_turnaround_variants(self):
        """resolve_dimensions must map turnaround variants strictly to (1536, 768)."""
        assert shotspec.resolve_dimensions("turnaround") == (1536, 768)
        assert shotspec.resolve_dimensions("turnaround_sheet") == (1536, 768)

    def test_prompt_pure_white_background_directives(self):
        """Natural turnaround prompt must contain explicit clean pure white background directives."""
        story, char = _make_story()
        prompt = compile_turnaround_prompt(char, story, style_kind="natural")

        # Must specify pure white background
        assert "Solid, seamless clean pure white background" in prompt
        assert "zero environment, zero scenery, zero shadows, and no props" in prompt
        assert "to prevent background attention bleed" in prompt

        # Negative prompt under tags must suppress clutter
        _, neg = compile_turnaround_prompt(char, story, style_kind="tags", return_negative=True)
        assert "complex background" in neg
        assert "background clutter" in neg
        assert "scenery, props, furniture" in neg

    def test_offline_image_pixel_audit_pure_white(self):
        """Offline turnaround image must have pure white (255, 255, 255) background on corners and edges."""
        story, char = _make_story()
        img = _create_offline_turnaround_image(char, RiggingSpec(), (1536, 768))
        assert img.size == (1536, 768)
        w, h = img.size

        pixels = img.load()

        # Check all 4 corners
        corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
        for cx, cy in corners:
            assert pixels[cx, cy] == (255, 255, 255), f"Corner ({cx}, {cy}) is not pure white: {pixels[cx, cy]}"

        # Sample border pixels at y=2, y=h-3 (within empty margins, outside guide rect at y=8)
        for x in range(0, w, 100):
            assert pixels[x, 2] == (255, 255, 255), f"Top margin at ({x}, 2) is {pixels[x, 2]}"
            assert pixels[x, h - 3] == (255, 255, 255), f"Bottom margin at ({x}, {h-3}) is {pixels[x, h-3]}"

        for y in range(0, h, 50):
            assert pixels[2, y] == (255, 255, 255), f"Left margin at (2, {y}) is {pixels[2, y]}"
            assert pixels[w - 3, y] == (255, 255, 255), f"Right margin at ({w-3}, {y}) is {pixels[w-3, y]}"

    def test_turnaround_slicing_divisibility_and_purity(self):
        """slice_turnaround_sheet on a 1536x768 image must yield four 384x768 slices (multiples of 16)."""
        story, char = _make_story()
        master_img = _create_offline_turnaround_image(char, RiggingSpec(), (1536, 768))
        slices = slice_turnaround_sheet(master_img)

        assert len(slices) == 4
        expected_views = ["front", "three_quarter", "side", "back"]
        for view in expected_views:
            assert view in slices
            s_img = slices[view]
            sw, sh = s_img.size
            assert (sw, sh) == (384, 768), f"Slice {view} dimensions {(sw, sh)} != (384, 768)"
            assert sw % 16 == 0, f"Slice {view} width {sw} not divisible by 16"
            assert sh % 16 == 0, f"Slice {view} height {sh} not divisible by 16"

            # Check slice corners
            s_pixels = s_img.load()
            assert s_pixels[0, 0] == (255, 255, 255)
            assert s_pixels[sw - 1, 0] == (255, 255, 255)
            assert s_pixels[0, sh - 1] == (255, 255, 255)
            assert s_pixels[sw - 1, sh - 1] == (255, 255, 255)


# ==============================================================================
# 3. ComfyUI Patch Slot & Regression Defense Stress Tests
# ==============================================================================

class TestComfyUIPatchSlotRegressionDefense:
    """Adversarially verify that reference_image slot handling maintains exact contracts:
    1. Single Art Workflow invariant: qwen_image_21 is sole text_to_image workflow.
    2. qwen_image_21 treats reference_image as strictly optional (no crash if omitted).
    3. Legacy workflows (anime_sdxl_ipa, etc.) treat reference_image as required (raises error if omitted).
    """

    def test_single_art_workflow_invariant(self):
        """Only qwen_image_21 may have purpose 'text_to_image' in workflow_registry.json."""
        reg_file = Path("engine/comfyui/workflow_registry.json")
        data = json.loads(reg_file.read_text(encoding="utf-8"))
        t2i = [w for w in data if isinstance(w, dict) and w.get("purpose") == "text_to_image"]
        assert len(t2i) == 1
        assert t2i[0]["id"] == "qwen_image_21"

    def test_qwen_workflow_omitted_reference_image_succeeds(self):
        """_patch_workflow on qwen_image_21 without reference_image succeeds and cleans DAG."""
        reg = ComfyWorkflowRegistry()
        workflow, _ = reg.load("qwen_image_21")
        entry = reg.metadata("qwen_image_21")
        patch_slots = entry["patch_slots"]

        # Call with reference_image=None
        patched = _patch_workflow(
            workflow=workflow,
            patch_slots=patch_slots,
            prompt="test pos",
            negative_prompt="test neg",
            width=1024,
            height=1024,
            seed=12345,
            prefix="test",
            reference_image=None,
        )

        assert isinstance(patched, dict)
        # Verify node 4 (TextEncodeQwenImage21) inputs do NOT contain 'images.image_1'
        node4 = patched.get("4")
        assert isinstance(node4, dict)
        assert "images.image_1" not in node4["inputs"]

        # Verify no LoadImage node was dynamically injected
        load_nodes = [nid for nid, n in patched.items() if isinstance(n, dict) and n.get("class_type") == "LoadImage"]
        assert len(load_nodes) == 0

    def test_qwen_workflow_supplied_reference_image_injects_load_image(self):
        """_patch_workflow on qwen_image_21 with reference_image injects LoadImage node."""
        reg = ComfyWorkflowRegistry()
        workflow, _ = reg.load("qwen_image_21")
        entry = reg.metadata("qwen_image_21")
        patch_slots = entry["patch_slots"]

        patched = _patch_workflow(
            workflow=workflow,
            patch_slots=patch_slots,
            prompt="test pos",
            negative_prompt="test neg",
            width=1024,
            height=1024,
            seed=12345,
            prefix="test",
            reference_image="mira_turnaround.png",
        )

        assert isinstance(patched, dict)
        # Find injected LoadImage node
        load_nodes = [
            (nid, n)
            for nid, n in patched.items()
            if isinstance(n, dict) and n.get("class_type") == "LoadImage"
        ]
        assert len(load_nodes) == 1
        injected_id, injected_node = load_nodes[0]
        assert injected_node["inputs"]["image"] == "mira_turnaround.png"

        # Verify node 4 connects to the injected LoadImage node
        node4 = patched.get("4")
        assert node4["inputs"]["images.image_1"] == [injected_id, 0]

    @pytest.mark.parametrize(
        "legacy_workflow_id",
        [
            "anime_sdxl_ipa",
            "anime_sdxl_inpaint",
            "anime_alpha_matting",
            "wan21_14b_i2v",
        ],
    )
    def test_legacy_workflows_fail_without_reference_image(self, legacy_workflow_id: str):
        """Legacy workflows declaring reference_image MUST fail if reference_image is omitted."""
        reg = ComfyWorkflowRegistry()
        try:
            workflow, _ = reg.load(legacy_workflow_id)
            entry = reg.metadata(legacy_workflow_id)
        except Exception:
            pytest.skip(f"Workflow {legacy_workflow_id} could not be loaded")

        patch_slots = entry.get("patch_slots", {})
        if "reference_image" not in patch_slots:
            pytest.skip(f"Workflow {legacy_workflow_id} does not declare reference_image")

        # Omission must raise ComfyImageGenerationError
        with pytest.raises(ComfyImageGenerationError) as exc_info:
            _patch_workflow(
                workflow=workflow,
                patch_slots=patch_slots,
                prompt="test pos",
                negative_prompt="test neg",
                width=1024,
                height=1024,
                seed=12345,
                prefix="test",
                reference_image=None,
            )
        assert "Approved workflow does not declare every required patch slot" in str(exc_info.value)
