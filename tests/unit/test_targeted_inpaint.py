"""Unit tests for Phase 3: Targeted Inpainting & Local Defect Repair Loop."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image
import pytest

from engine.comfyui import ComfyWorkflowRegistry
from engine.comfyui.client import ComfyUIClient
from engine.comfyui.service import ComfyImageGenerationError, _patch_workflow
from engine.original import art
from engine.original import review as review_mod
from engine.original.models import (
    Bible,
    Character,
    Claim,
    ItemVerdict,
    Line,
    Location,
    OriginalStory,
    Panel,
    Premise,
    Review,
    Scene,
)
from engine.original.shotspec import CharPose, ShotSpec


def _make_png(color="blue", size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _make_story() -> OriginalStory:
    bible = Bible(
        premise=Premise(title="Test Tale", genre="fantasy", logline="l", tone="t", setting="s"),
        characters=[
            Character(id="hero", name="Hero", role="protagonist", age_group="adult",
                      look="short black hair, blue eyes, iron armor, silver sword", personality="p"),
        ],
        locations=[Location(id="courtyard", name="Courtyard", look="stone pavement, castle walls")],
    )
    spec = ShotSpec(
        shot="medium",
        camera="eye_level",
        setting="stone pavement, castle walls",
        lighting="daylight",
        mood="tense",
        key_visuals=["holding silver sword"],
        characters=[CharPose(id="hero", side="center", pose="standing", expression="focused", action="gripping sword")],
    )
    panel = Panel(
        id="p001",
        scene_id="sc01",
        shot="medium",
        angle="eye_level",
        location_id="courtyard",
        character_ids=["hero"],
        action="Hero firmly holds his sword.",
        dialogue=[Line(speaker_id="hero", text="Stay back.")],
        director=spec.model_dump(),
        key_visuals=["holding silver sword"],
        caption="Hero stands in the courtyard, his hand gripping the silver sword.",
    )
    scene = Scene(id="sc01", location_id="courtyard", character_ids=["hero"], summary="s", mood="m")
    return OriginalStory(bible=bible, scenes=[scene], panels=[panel])


# ==============================================================================
# 1. Defect Mask Extraction Tests
# ==============================================================================

def test_extract_defect_mask_from_distorted_digits():
    verdict = ItemVerdict(
        item="hand digits check",
        critical=True,
        verdict="missing",
        confidence=0.85,
        vision="no",
        description_says=False,
        evidence="six fingers on right hand",
        category="anatomy",
        defect_type="distorted_digits",
        passed=False,
    )
    mask = review_mod.extract_defect_mask((1024, 1024), [verdict])
    assert mask is not None
    assert mask.size == (1024, 1024)
    assert mask.mode == "L"

    # Because evidence mentioned 'right', right quadrant should contain inpaint region (255)
    # Check pixels in right-hand region
    pixels = mask.load()
    right_val = pixels[int(0.6 * 1024), int(0.6 * 1024)]
    assert right_val > 0  # Inpainted defect region has non-zero mask values


def test_extract_defect_mask_from_explicit_bbox():
    verdict = ItemVerdict(
        item="hand digits check",
        critical=True,
        verdict="missing",
        confidence=0.9,
        vision="no",
        description_says=False,
        evidence="deformed hand",
        category="anatomy",
        defect_type="distorted_digits",
        passed=False,
        bbox=[200, 300, 400, 500],
    )
    mask = review_mod.extract_defect_mask((800, 800), [verdict], padding=10, blur_radius=0)
    assert mask is not None
    pixels = mask.load()
    # Inside the box + padding
    assert pixels[300, 400] == 255
    # Outside the box
    assert pixels[50, 50] == 0


def test_extract_defect_mask_from_normalized_bbox():
    verdict = ItemVerdict(
        item="hand check",
        critical=True,
        verdict="missing",
        confidence=0.9,
        vision="no",
        description_says=False,
        evidence="extra digit",
        category="anatomy",
        defect_type="distorted_digits",
        passed=False,
        bbox=[0.2, 0.3, 0.4, 0.5],
    )
    mask = review_mod.extract_defect_mask((1000, 1000), [verdict], padding=0, blur_radius=0)
    assert mask is not None
    pixels = mask.load()
    # Point inside normalized [0.2*1000, 0.3*1000, 0.4*1000, 0.5*1000] -> [200, 300, 400, 500]
    assert pixels[300, 400] == 255
    # Point outside
    assert pixels[100, 100] == 0


def test_extract_defect_mask_from_unanchored_object():
    verdict = ItemVerdict(
        item="object support check",
        critical=True,
        verdict="missing",
        confidence=0.8,
        vision="no",
        description_says=False,
        evidence="floating sword in air",
        category="spatial_contact",
        defect_type="unanchored_object",
        passed=False,
    )
    mask = review_mod.extract_defect_mask((512, 512), [verdict])
    assert mask is not None
    assert mask.size == (512, 512)
    pixels = mask.load()
    assert pixels[int(0.5 * 512), int(0.6 * 512)] > 0


def test_extract_defect_mask_from_polycephaly():
    verdict = ItemVerdict(
        item="head count check",
        critical=True,
        verdict="missing",
        confidence=0.9,
        vision="no",
        description_says=False,
        evidence="two faces visible",
        category="anatomy",
        defect_type="polycephaly",
        passed=False,
    )
    mask = review_mod.extract_defect_mask((1024, 1024), [verdict])
    assert mask is not None
    pixels = mask.load()
    # Head region is near the top
    assert pixels[int(0.5 * 1024), int(0.2 * 1024)] > 0


def test_extract_defect_mask_from_disconnected_interaction():
    verdict = ItemVerdict(
        item="grasp check",
        critical=True,
        verdict="missing",
        confidence=0.85,
        vision="no",
        description_says=False,
        evidence="sword floating next to hand",
        category="spatial_contact",
        defect_type="disconnected_interaction",
        passed=False,
    )
    mask = review_mod.extract_defect_mask((1024, 1024), [verdict])
    assert mask is not None
    pixels = mask.load()
    assert pixels[int(0.5 * 1024), int(0.6 * 1024)] > 0


def test_extract_defect_mask_clean_returns_none():
    verdicts = [
        ItemVerdict(item="looks good", critical=True, verdict="shown", confidence=0.9, vision="yes",
                    description_says=True, category="narration", passed=True),
        ItemVerdict(item="anatomy ok", critical=True, verdict="shown", confidence=0.9, vision="yes",
                    description_says=True, category="anatomy", defect_type="distorted_digits", passed=True),
    ]
    mask = review_mod.extract_defect_mask((1024, 1024), verdicts)
    assert mask is None


def test_extract_defect_mask_from_review_object():
    rev = Review(
        items=[
            ItemVerdict(item="distorted fingers", critical=True, verdict="missing", confidence=0.8,
                        vision="no", description_says=False, category="anatomy",
                        defect_type="distorted_digits", passed=False),
        ],
        score=0.4,
        confidence=0.8,
        decision="regenerate",
        anatomy_passed=False,
    )
    mask = review_mod.extract_defect_mask((800, 800), rev)
    assert mask is not None
    assert mask.size == (800, 800)


# ==============================================================================
# 2. Inpaint Correction Prompt Generation Tests
# ==============================================================================

def test_build_inpaint_correction_prompt_generic():
    verdict = ItemVerdict(
        item="digits",
        critical=True,
        verdict="missing",
        confidence=0.8,
        vision="no",
        description_says=False,
        category="anatomy",
        defect_type="distorted_digits",
        passed=False,
    )
    pos, neg = review_mod.build_inpaint_correction_prompt([verdict], base_prompt="masterpiece, fantasy armor")
    assert "detailed anatomical hand" in pos
    assert "five fingers" in pos
    assert "masterpiece, fantasy armor" in pos
    # AGENTS.md generic rule check: no story-specific names
    assert "Hero" not in pos and "Mira" not in pos
    assert "bad anatomy" in neg and "extra digits" in neg and "six fingers" in neg


def test_build_inpaint_correction_prompt_multi_defect():
    verdicts = [
        ItemVerdict(item="digits", critical=True, verdict="missing", confidence=0.8, vision="no",
                    description_says=False, category="anatomy", defect_type="distorted_digits", passed=False),
        ItemVerdict(item="contact", critical=True, verdict="missing", confidence=0.8, vision="no",
                    description_says=False, category="spatial_contact", defect_type="disconnected_interaction", passed=False),
    ]
    pos, neg = review_mod.build_inpaint_correction_prompt(verdicts)
    assert "five fingers" in pos
    assert "firmly gripping object" in pos
    assert "extra digits" in neg
    assert "disconnected grip" in neg


# ==============================================================================
# 3. Splicing & Pixel Preservation Tests
# ==============================================================================

def test_splice_repaired_image_preserves_unmasked_pixels():
    # Base is pure red, repaired is pure green
    base = Image.new("RGB", (100, 100), (255, 0, 0))
    repaired = Image.new("RGB", (100, 100), (0, 255, 0))

    # Mask has white square in center [40, 40, 60, 60], black everywhere else
    mask = Image.new("L", (100, 100), 0)
    for y in range(40, 60):
        for x in range(40, 60):
            mask.putpixel((x, y), 255)

    spliced = review_mod.splice_repaired_image(base, repaired, mask)

    # Outside the mask: must be pure red (identical to base)
    assert spliced.getpixel((10, 10)) == (255, 0, 0)
    assert spliced.getpixel((90, 90)) == (255, 0, 0)

    # Inside the mask: must be pure green (from repaired)
    assert spliced.getpixel((50, 50)) == (0, 255, 0)


# ==============================================================================
# 4. ComfyUI Inpaint Workflow & Registry Tests
# ==============================================================================

def test_inpaint_workflow_registered_and_patchable():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, checksum = reg.load("anime_sdxl_inpaint")
    entry = reg.metadata("anime_sdxl_inpaint")

    assert entry["id"] == "anime_sdxl_inpaint"
    assert entry["purpose"] == "inpaint"
    assert checksum == entry["sha256"]

    # Test patching with all slots
    patched = _patch_workflow(
        wf,
        entry["patch_slots"],
        prompt="detailed hand, 5 fingers",
        negative_prompt="bad hands",
        width=1024,
        height=1024,
        seed=12345,
        prefix="inpaint_unit",
        reference_image="base.png",
        mask_image="mask.png",
        denoise=0.75,
    )
    assert patched["2"]["inputs"]["text"] == "detailed hand, 5 fingers"
    assert patched["3"]["inputs"]["text"] == "bad hands"
    assert patched["4"]["inputs"]["image"] == "base.png"
    assert patched["5"]["inputs"]["image"] == "mask.png"
    assert patched["8"]["inputs"]["seed"] == 12345
    assert patched["8"]["inputs"]["denoise"] == 0.75
    assert patched["11"]["inputs"]["filename_prefix"] == "inpaint_unit"


def test_inpaint_workflow_fails_without_required_slots():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, _ = reg.load("anime_sdxl_inpaint")
    entry = reg.metadata("anime_sdxl_inpaint")

    # Missing mask_image must raise ComfyImageGenerationError
    with pytest.raises(ComfyImageGenerationError):
        _patch_workflow(
            wf,
            entry["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=1024,
            height=1024,
            seed=1,
            prefix="test",
            reference_image="base.png",
        )

    # Missing reference_image must raise ComfyImageGenerationError
    with pytest.raises(ComfyImageGenerationError):
        _patch_workflow(
            wf,
            entry["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=1024,
            height=1024,
            seed=1,
            prefix="test",
            mask_image="mask.png",
        )


def test_inpaint_workflow_optional_denoise_defaults():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, _ = reg.load("anime_sdxl_inpaint")
    entry = reg.metadata("anime_sdxl_inpaint")

    patched = _patch_workflow(
        wf,
        entry["patch_slots"],
        prompt="p",
        negative_prompt="n",
        width=1024,
        height=1024,
        seed=1,
        prefix="test",
        reference_image="base.png",
        mask_image="mask.png",
        denoise=None,  # workflow default applies
    )
    assert patched["8"]["inputs"]["denoise"] == 0.75


# ==============================================================================
# 5. ComfyRunner inpaint Method Mocking Test
# ==============================================================================

def test_comfy_runner_inpaint_submits_and_downloads():
    mock_client = MagicMock()
    mock_client.base_url = "http://127.0.0.1:8188/"
    mock_client.submit_prompt.return_value = "prompt_inpaint_1"
    mock_client.history.return_value = {
        "prompt_inpaint_1": {
            "outputs": {
                "11": {
                    "images": [{"filename": "repaired.png", "subfolder": "", "type": "output"}]
                }
            }
        }
    }
    mock_client.download_output.return_value = _make_png("green")

    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner.client = mock_client
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    runner.inpaint_wf = (reg.load("anime_sdxl_inpaint")[0], reg.metadata("anime_sdxl_inpaint"))
    runner._upload_bytes = MagicMock(side_effect=["uploaded_base.png", "uploaded_mask.png"])

    res = runner.inpaint(
        base_image=b"fakebase",
        mask_image=b"fakemask",
        prompt="detailed hand",
        neg="bad hand",
        seed=42,
        denoise=0.75,
    )
    assert res == _make_png("green")
    assert mock_client.submit_prompt.called
    assert mock_client.download_output.called


# ==============================================================================
# 6. art.py Targeted Repair Loop Integration Tests
# ==============================================================================

class MockInpaintRunner:
    """Mock runner supporting both generate and inpaint calls."""

    def __init__(self, initial_color="red", repaired_color="green"):
        self.initial_color = initial_color
        self.repaired_color = repaired_color
        self.generate_calls = []
        self.inpaint_calls = []

    def generate(self, pos, neg, seed, width, height, prefix, **kw):
        self.generate_calls.append({"pos": pos, "seed": seed, "prefix": prefix})
        return _make_png(self.initial_color, (width, height))

    def inpaint(self, base_image, mask_image, prompt, neg, seed, denoise=0.75, **kw):
        self.inpaint_calls.append({"prompt": prompt, "seed": seed, "denoise": denoise})
        return _make_png(self.repaired_color)


class MockReviewProvider:
    """Mock vision provider controlling defect presence across attempts."""

    def __init__(self, defect_on_initial=True, repair_succeeds=True):
        self.defect_on_initial = defect_on_initial
        self.repair_succeeds = repair_succeeds
        self.review_count = 0

    async def generate_structured(self, prompt, model, **kw):
        from engine.original import review as rv
        if model is rv._Claims:
            return model(claims=[Claim(text="Hero holds silver sword", critical=True)])
        if model is rv._DescJudge:
            # If initial had defect and this is initial review, return False; else True
            ok = not self.defect_on_initial or (self.review_count > 1 and self.repair_succeeds)
            return model(stated=[ok] * 10)
        raise AssertionError(f"Unexpected model: {model}")

    async def analyze_vision(self, image, prompt, **kw):
        from engine.original import review as rv
        if "format_schema" in kw:
            self.review_count += 1
            is_repair_review = self.review_count > 1
            if not self.defect_on_initial:
                answers = [{"n": i + 1, "answer": "yes", "evidence": "normal"} for i in range(10)]
            elif is_repair_review:
                if self.repair_succeeds:
                    answers = [{"n": i + 1, "answer": "yes", "evidence": "perfect hand with five fingers"} for i in range(10)]
                else:
                    answers = [{"n": 1, "answer": "no", "evidence": "six fingers still present"}] + [
                        {"n": i + 2, "answer": "yes", "evidence": "normal"} for i in range(9)
                    ]
            else:
                answers = [{"n": 1, "answer": "no", "evidence": "six fingers on right hand"}] + [
                    {"n": i + 2, "answer": "yes", "evidence": "normal"} for i in range(9)
                ]
            return json.dumps({"answers": answers})
        # Description
        if self.review_count > 1 and self.repair_succeeds:
            return "Hero standing with five fingers firmly gripping his sword"
        if self.defect_on_initial:
            return "Hero with six fingers holding a sword"
        return "Hero holding his silver sword"


def test_art_repair_loop_accepts_when_score_improves(tmp_path):
    story = _make_story()
    runner = MockInpaintRunner()
    provider = MockReviewProvider(defect_on_initial=True, repair_succeeds=True)

    out = art.generate_art(story, tmp_path, runner, provider=provider)

    assert len(runner.inpaint_calls) == 1
    assert "detailed anatomical hand" in runner.inpaint_calls[0]["prompt"]

    # Verify panel was accepted
    art_records = json.loads((tmp_path / "art.json").read_text())
    record = art_records[0]
    assert record["status"] == "accept"
    assert record["review"]["decision"] == "accept"
    assert record["review"]["anatomy_passed"] is True
    assert out["accepted"] == ["p001"]

    # the repair is a recorded candidate that points at the picture it repaired, with its mask, and it is the selected one
    reps = [i for i in record["iterations"] if i["kind"] == "repair"]
    assert len(reps) == 1 and reps[0]["kept"] is True and record["selected"] == reps[0]["n"]
    parent = next(i for i in record["iterations"] if i["n"] == reps[0]["parent"])
    assert parent["kind"] == "generate" and parent["review"]["decision"] == "regenerate"  # the unrepaired original is still on disk
    assert (tmp_path / parent["file"]).exists() and (tmp_path / reps[0]["file"].replace(".png", "_mask.png")).exists()


def test_art_repair_loop_rejects_and_falls_back_when_unimproved(tmp_path):
    story = _make_story()
    runner = MockInpaintRunner()
    # Repair fails to fix the defect
    provider = MockReviewProvider(defect_on_initial=True, repair_succeeds=False)

    out = art.generate_art(story, tmp_path, runner, provider=provider)

    # Inpaint was attempted
    assert len(runner.inpaint_calls) >= 1

    art_records = json.loads((tmp_path / "art.json").read_text())
    record = art_records[0]
    # Panel is not accepted because defects persisted across all attempts
    assert record["status"] == "needs_review"
    assert out["needs_review"] == ["p001"]
    assert all(i["kind"] == "repair" and i["kept"] is False for i in record["iterations"] if i["kind"] == "repair")
    assert record["selected"] in {i["n"] for i in record["iterations"]}


def test_art_repair_loop_falls_back_gracefully_when_inpaint_raises(tmp_path):
    story = _make_story()
    runner = MockInpaintRunner()

    def exploding_inpaint(*args, **kw):
        raise RuntimeError("ComfyUI inpainting unavailable")

    runner.inpaint = exploding_inpaint
    provider = MockReviewProvider(defect_on_initial=True, repair_succeeds=False)

    # Must complete cleanly without crashing
    out = art.generate_art(story, tmp_path, runner, provider=provider)
    assert out["generated"] == 1
    art_records = json.loads((tmp_path / "art.json").read_text())
    assert art_records[0]["status"] == "needs_review"


def test_art_repair_loop_skipped_when_panel_is_clean(tmp_path):
    story = _make_story()
    runner = MockInpaintRunner()
    # Panel is clean on initial generation
    provider = MockReviewProvider(defect_on_initial=False, repair_succeeds=True)

    out = art.generate_art(story, tmp_path, runner, provider=provider)

    # Inpaint should never be called for a clean panel
    assert len(runner.inpaint_calls) == 0
    art_records = json.loads((tmp_path / "art.json").read_text())
    assert art_records[0]["status"] == "accept"
    assert out["accepted"] == ["p001"]
