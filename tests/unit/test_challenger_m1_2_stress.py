"""Empirical Challenger 2 stress-test harness for Phase 3 Targeted Inpainting & ComfyUI Workflow Integration.

Verifies:
1. ComfyWorkflowRegistry robustness (corrupted files, missing/unexpected patch slots, checksum tamper, dimension policy).
2. Inpainting error handling in art.py (network failure, ComfyUI crash, malformed output, graceful fallback without crashing).
3. Score threshold boundary conditions (score drop threshold, persistent defect rejection, partial defect reduction edge cases).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
import pytest

from engine.comfyui.client import ComfyUIClient, ComfyUIError
from engine.comfyui.registry import ComfyWorkflowRegistry, WorkflowRegistryError, _REGISTRY_FILE
from engine.comfyui.service import ComfyImageGenerationError
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


def _make_png_bytes(color: str = "blue", size: tuple[int, int] = (64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _make_test_story() -> OriginalStory:
    bible = Bible(
        premise=Premise(title="Stress Tale", genre="fantasy", logline="l", tone="t", setting="s"),
        characters=[
            Character(id="c1", name="Knight", role="protagonist", age_group="adult",
                      look="armor, silver sword", personality="p"),
        ],
        locations=[Location(id="loc1", name="Arena", look="stone floor")],
    )
    spec = ShotSpec(
        shot="medium",
        camera="eye_level",
        setting="stone floor",
        lighting="daylight",
        mood="tense",
        key_visuals=["holding silver sword"],
        characters=[CharPose(id="c1", side="center", pose="standing", expression="focused", action="gripping sword")],
    )
    panel = Panel(
        id="p001",
        scene_id="sc01",
        shot="medium",
        angle="eye_level",
        location_id="loc1",
        character_ids=["c1"],
        action="Knight firmly holds his sword.",
        dialogue=[Line(speaker_id="c1", text="Halt.")],
        director=spec.model_dump(),
        key_visuals=["holding silver sword"],
        caption="Knight standing with sword.",
    )
    scene = Scene(id="sc01", location_id="loc1", character_ids=["c1"], summary="s", mood="m")
    return OriginalStory(bible=bible, scenes=[scene], panels=[panel])


# ==============================================================================
# Suite 1: ComfyWorkflowRegistry Robustness & Checksum Integrity
# ==============================================================================

class TestComfyWorkflowRegistryRobustness:
    """Stress tests for ComfyWorkflowRegistry tamper protection and structural validation."""

    @pytest.fixture
    def mock_workflow_root(self, tmp_path):
        """Creates a temporary isolated workflow directory."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        return wf_dir

    @pytest.fixture
    def base_inpaint_fixture(self, mock_workflow_root):
        """Loads genuine inpaint workflow and metadata as a clean baseline for tampering tests."""
        raw_reg = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
        entry = next(e for e in raw_reg if e["id"] == "anime_sdxl_inpaint")
        real_wf_path = Path(__file__).resolve().parents[2] / "engine" / "comfyui" / "workflows" / entry["filename"]
        raw_bytes = real_wf_path.read_bytes()

        # Copy to mock workflow root
        target_file = mock_workflow_root / entry["filename"]
        target_file.write_bytes(raw_bytes)

        mock_client = MagicMock(spec=ComfyUIClient)
        mock_client.api_workflow_root.return_value = mock_workflow_root
        return entry, raw_bytes, mock_client

    def test_production_anime_sdxl_inpaint_integrity(self):
        """Verify the repository's anime_sdxl_inpaint workflow has exact SHA256 and valid structure."""
        reg = ComfyWorkflowRegistry(ComfyUIClient())
        wf, checksum = reg.load("anime_sdxl_inpaint")
        meta = reg.metadata("anime_sdxl_inpaint")

        assert checksum == meta["sha256"]
        assert len(wf) == 11
        assert "mask_image" in meta["patch_slots"]
        assert "denoise" in meta["patch_slots"]
        assert meta["patch_slots"]["mask_image"]["class_type"] == "LoadImageMask"
        assert meta["patch_slots"]["denoise"]["class_type"] == "KSampler"

    def test_sha256_checksum_mismatch_single_byte_tamper(self, base_inpaint_fixture, mock_workflow_root):
        """Verify modifying even a single byte in the workflow file raises WorkflowRegistryError."""
        entry, raw_bytes, mock_client = base_inpaint_fixture
        tampered = bytearray(raw_bytes)
        # Flip/modify one character in the file
        tampered[10] = ord(b"X") if tampered[10] != ord(b"X") else ord(b"Y")
        (mock_workflow_root / entry["filename"]).write_bytes(tampered)

        reg = ComfyWorkflowRegistry(mock_client)
        with pytest.raises(WorkflowRegistryError, match="Workflow checksum mismatch"):
            reg.load("anime_sdxl_inpaint")

    def test_corrupted_json_syntax(self, base_inpaint_fixture, mock_workflow_root):
        """Verify invalid JSON syntax triggers WorkflowRegistryError."""
        entry, _, mock_client = base_inpaint_fixture
        corrupted_content = b'{"node_1": {"class_type": "KSampler", UNTERMINATED_JSON'
        (mock_workflow_root / entry["filename"]).write_bytes(corrupted_content)

        # Update registry entry sha256 to match so we test JSON parsing resilience
        reg = ComfyWorkflowRegistry(mock_client)
        reg._entries["anime_sdxl_inpaint"]["sha256"] = hashlib.sha256(corrupted_content).hexdigest()

        with pytest.raises(WorkflowRegistryError, match="Workflow JSON is invalid"):
            reg.load("anime_sdxl_inpaint")

    def test_non_mapping_json_types(self, base_inpaint_fixture, mock_workflow_root):
        """Verify non-dictionary JSON roots (array, string, empty dict) are rejected."""
        entry, _, mock_client = base_inpaint_fixture

        for bad_payload in [b"[]", b'["node1", "node2"]', b'"just_a_string"', b"{}"]:
            (mock_workflow_root / entry["filename"]).write_bytes(bad_payload)
            reg = ComfyWorkflowRegistry(mock_client)
            reg._entries["anime_sdxl_inpaint"]["sha256"] = hashlib.sha256(bad_payload).hexdigest()

            with pytest.raises(WorkflowRegistryError, match="is empty or not an API-format mapping"):
                reg.load("anime_sdxl_inpaint")

    def test_missing_required_patch_slots(self, base_inpaint_fixture, mock_workflow_root):
        """Verify omission of any _REQUIRED_PATCH_SLOTS is rejected."""
        entry, raw_bytes, mock_client = base_inpaint_fixture
        reg = ComfyWorkflowRegistry(mock_client)

        for required_slot in ["prompt", "negative_prompt", "seed", "filename_prefix"]:
            entry_copy = copy.deepcopy(reg._entries["anime_sdxl_inpaint"])
            del entry_copy["patch_slots"][required_slot]
            reg._entries["anime_sdxl_inpaint"] = entry_copy

            with pytest.raises(WorkflowRegistryError, match="must declare exact patch slots"):
                reg.load("anime_sdxl_inpaint")

    def test_unexpected_unauthorized_patch_slot(self, base_inpaint_fixture, mock_workflow_root):
        """Verify unauthorized/unknown patch slots outside _OPTIONAL_PATCH_SLOTS are rejected."""
        entry, raw_bytes, mock_client = base_inpaint_fixture
        reg = ComfyWorkflowRegistry(mock_client)

        entry_copy = copy.deepcopy(reg._entries["anime_sdxl_inpaint"])
        entry_copy["patch_slots"]["malicious_script_hook"] = {
            "node_id": "8",
            "input": "seed",
            "class_type": "KSampler",
        }
        reg._entries["anime_sdxl_inpaint"] = entry_copy

        with pytest.raises(WorkflowRegistryError, match="must declare exact patch slots"):
            reg.load("anime_sdxl_inpaint")

    def test_patch_slot_missing_required_keys(self, base_inpaint_fixture, mock_workflow_root):
        """Verify patch slots missing 'class_type' or having unexpected fields are rejected."""
        entry, raw_bytes, mock_client = base_inpaint_fixture
        reg = ComfyWorkflowRegistry(mock_client)

        entry_copy = copy.deepcopy(reg._entries["anime_sdxl_inpaint"])
        # Missing class_type
        entry_copy["patch_slots"]["denoise"] = {"node_id": "8", "input": "denoise"}
        reg._entries["anime_sdxl_inpaint"] = entry_copy

        with pytest.raises(WorkflowRegistryError, match="patch slot denoise is invalid"):
            reg.load("anime_sdxl_inpaint")

    def test_patch_slot_nonexistent_node_id(self, base_inpaint_fixture, mock_workflow_root):
        """Verify patch slot pointing to non-existent node ID in workflow raises error."""
        entry, raw_bytes, mock_client = base_inpaint_fixture
        reg = ComfyWorkflowRegistry(mock_client)

        entry_copy = copy.deepcopy(reg._entries["anime_sdxl_inpaint"])
        entry_copy["patch_slots"]["denoise"] = {
            "node_id": "999",  # Does not exist in workflow
            "input": "denoise",
            "class_type": "KSampler",
        }
        reg._entries["anime_sdxl_inpaint"] = entry_copy

        with pytest.raises(WorkflowRegistryError, match="patch slot denoise node is missing"):
            reg.load("anime_sdxl_inpaint")

    def test_patch_slot_class_type_mismatch(self, base_inpaint_fixture, mock_workflow_root):
        """Verify patch slot claiming wrong class_type for the target node raises error."""
        entry, raw_bytes, mock_client = base_inpaint_fixture
        reg = ComfyWorkflowRegistry(mock_client)

        entry_copy = copy.deepcopy(reg._entries["anime_sdxl_inpaint"])
        entry_copy["patch_slots"]["denoise"] = {
            "node_id": "8",
            "input": "denoise",
            "class_type": "VAEDecode",  # Actual node 8 is KSampler
        }
        reg._entries["anime_sdxl_inpaint"] = entry_copy

        with pytest.raises(WorkflowRegistryError, match="class_type does not match approved metadata"):
            reg.load("anime_sdxl_inpaint")

    def test_patch_slot_missing_input_in_node(self, base_inpaint_fixture, mock_workflow_root):
        """Verify patch slot specifying an input name absent from target node inputs raises error."""
        entry, raw_bytes, mock_client = base_inpaint_fixture
        reg = ComfyWorkflowRegistry(mock_client)

        entry_copy = copy.deepcopy(reg._entries["anime_sdxl_inpaint"])
        entry_copy["patch_slots"]["denoise"] = {
            "node_id": "8",
            "input": "non_existent_hyperparameter",
            "class_type": "KSampler",
        }
        reg._entries["anime_sdxl_inpaint"] = entry_copy

        with pytest.raises(WorkflowRegistryError, match="input is missing"):
            reg.load("anime_sdxl_inpaint")

    def test_invalid_dimension_policy_boundary_cases(self, base_inpaint_fixture, mock_workflow_root):
        """Verify strict dimension policy validation (mode, min, max, multiple_of)."""
        entry, raw_bytes, mock_client = base_inpaint_fixture
        reg = ComfyWorkflowRegistry(mock_client)

        bad_policies = [
            {"mode": "flexible", "min": 512, "max": 1024, "multiple_of": 64},  # wrong mode
            {"mode": "exact", "min": 0, "max": 1024, "multiple_of": 64},       # min < 1
            {"mode": "exact", "min": 1024, "max": 512, "multiple_of": 64},     # max < min
            {"mode": "exact", "min": 512, "max": 1024, "multiple_of": 0},      # multiple_of < 1
            {"mode": "exact", "min": "512", "max": 1024, "multiple_of": 64},   # non-int
        ]
        for bad_policy in bad_policies:
            entry_copy = copy.deepcopy(reg._entries["anime_sdxl_inpaint"])
            entry_copy["dimension_policy"] = bad_policy
            reg._entries["anime_sdxl_inpaint"] = entry_copy

            with pytest.raises(WorkflowRegistryError, match="requires an exact dimension policy"):
                reg.load("anime_sdxl_inpaint")

    def test_oversized_workflow_file(self, base_inpaint_fixture, mock_workflow_root):
        """Verify workflow file exceeding 4MB size limit is rejected."""
        entry, _, mock_client = base_inpaint_fixture
        oversized = b" " * (4 * 1024 * 1024 + 10)
        (mock_workflow_root / entry["filename"]).write_bytes(oversized)

        reg = ComfyWorkflowRegistry(mock_client)
        with pytest.raises(WorkflowRegistryError, match="exceeds size limit"):
            reg.load("anime_sdxl_inpaint")

    def test_path_traversal_rejection(self, base_inpaint_fixture):
        """Verify filenames attempting directory traversal are blocked."""
        _, _, mock_client = base_inpaint_fixture
        reg = ComfyWorkflowRegistry(mock_client)
        reg._entries["anime_sdxl_inpaint"]["filename"] = "../outside.json"

        with pytest.raises(WorkflowRegistryError, match="missing or unsafe"):
            reg.load("anime_sdxl_inpaint")


# ==============================================================================
# Suite 2: Inpainting Error Handling & Fallback in art.py
# ==============================================================================

class TestInpaintErrorHandlingInArt:
    """Stress tests for runner exceptions during inpainting ensuring zero crashes and clean fallback."""

    def _setup_initial_review_with_defect(self):
        """Returns an initial Review object with an anatomical defect."""
        verdict = ItemVerdict(
            item="hand digits",
            critical=True,
            verdict="missing",
            confidence=0.9,
            vision="no",
            description_says=False,
            evidence="six fingers on right hand",
            category="anatomy",
            defect_type="distorted_digits",
            passed=False,
            bbox=[0.5, 0.5, 0.8, 0.8],
        )
        return Review(
            score=0.75,
            confidence=0.9,
            decision="regenerate",
            description="Character with distorted hand",
            items=[verdict],
            anatomy_passed=False,
            spatial_contact_passed=True,
            defects=["distorted_digits"],
        )

    @pytest.mark.parametrize("exception_to_raise", [
        ConnectionError("Failed to connect to ComfyUI on 127.0.0.1:8188"),
        TimeoutError("ComfyUI inpaint produced no image within 300s"),
        RuntimeError("CUDA out of memory in KSampler"),
        ComfyImageGenerationError("Workflow output unreadable"),
        ComfyUIError("Internal ComfyUI 500 error"),
    ])
    def test_runner_inpaint_exceptions_fallback_gracefully(self, tmp_path, exception_to_raise):
        """Verify that any runner exception during inpaint does NOT crash generate_art and preserves base panel."""
        story = _make_test_story()
        initial_png = _make_png_bytes("red", (512, 512))

        mock_runner = MagicMock()
        mock_runner.generate.return_value = initial_png
        mock_runner.inpaint.side_effect = exception_to_raise

        initial_rev = self._setup_initial_review_with_defect()

        with patch("engine.original.review.review_image", new=AsyncMock(return_value=initial_rev)):
            # Should not raise exception
            out = art.generate_art(story, tmp_path, mock_runner, provider=MagicMock())

        assert mock_runner.inpaint.called
        # Verify result was written and status falls back to needs_review / regenerate
        art_records = json.loads((tmp_path / "art.json").read_text())
        assert len(art_records) == 1
        record = art_records[0]
        assert record["status"] == "needs_review"
        assert record["review"]["anatomy_passed"] is False

        # Verify disk file holds initial image
        saved_img = Path(record["image"]).read_bytes()
        assert saved_img == initial_png

        # Verify no temporary repair files leaked
        leftover_rep_files = list(tmp_path.glob("**/_try_rep_*.png"))
        assert len(leftover_rep_files) == 0

    def test_runner_returns_malformed_bytes(self, tmp_path):
        """Verify runner returning corrupt/empty non-image bytes is caught and gracefully discarded."""
        story = _make_test_story()
        initial_png = _make_png_bytes("red", (512, 512))

        mock_runner = MagicMock()
        mock_runner.generate.return_value = initial_png
        mock_runner.inpaint.return_value = b"NOT_A_VALID_PNG_FILE_STREAM"

        initial_rev = self._setup_initial_review_with_defect()

        with patch("engine.original.review.review_image", new=AsyncMock(return_value=initial_rev)):
            out = art.generate_art(story, tmp_path, mock_runner, provider=MagicMock())

        assert mock_runner.inpaint.called
        art_records = json.loads((tmp_path / "art.json").read_text())
        assert art_records[0]["status"] == "needs_review"

        leftover_rep_files = list(tmp_path.glob("**/_try_rep_*.png"))
        assert len(leftover_rep_files) == 0

    def test_runner_lacks_inpaint_method(self, tmp_path):
        """Verify runner without inpaint method skips repair loop cleanly."""
        story = _make_test_story()
        initial_png = _make_png_bytes("red", (512, 512))

        class NoInpaintRunner:
            def generate(self, *a, **kw):
                return initial_png

        runner = NoInpaintRunner()
        initial_rev = self._setup_initial_review_with_defect()

        with patch("engine.original.review.review_image", new=AsyncMock(return_value=initial_rev)):
            out = art.generate_art(story, tmp_path, runner, provider=MagicMock())

        art_records = json.loads((tmp_path / "art.json").read_text())
        assert art_records[0]["status"] == "needs_review"

    def test_comfyrunner_direct_inpaint_method_edge_cases(self):
        """Direct stress testing of ComfyRunner.inpaint argument validations."""
        mock_client = MagicMock(spec=ComfyUIClient)
        runner = art.ComfyRunner.__new__(art.ComfyRunner)
        runner.client = mock_client
        runner.inpaint_wf = None

        # 1. Unloaded workflow
        with pytest.raises(RuntimeError, match="workflow anime_sdxl_inpaint is not available"):
            runner.inpaint(b"base", b"mask", "p", "n", 1)

        # 2. Type validation
        runner.inpaint_wf = ({}, {"patch_slots": {}})
        with pytest.raises(TypeError, match="Unsupported base_image type"):
            runner.inpaint(12345, b"mask", "p", "n", 1)

        runner._upload_bytes = MagicMock(return_value="uploaded.png")
        with pytest.raises(TypeError, match="Unsupported mask_image type"):
            runner.inpaint(b"base", 12345, "p", "n", 1)

        # 3. Cancellation token
        mock_client.submit_prompt.return_value = "prompt_1"
        with patch("engine.original.art._patch_workflow", return_value={}):
            with pytest.raises(RuntimeError, match="cancelled"):
                runner.inpaint(b"base", b"mask", "p", "n", 1, is_cancelled=lambda: True)


# ==============================================================================
# Suite 3: Score Threshold Boundary Testing
# ==============================================================================

class TestScoreThresholdBoundaries:
    """Stress tests for mathematical score comparisons and defect reduction criteria in art.py."""

    def _make_review(self, score: float, decision: str, anatomy_passed: bool,
                     spatial_contact_passed: bool, defects: list[str]) -> Review:
        # Build compliant Review with dummy item
        verdicts = []
        if not anatomy_passed or defects:
            verdicts.append(ItemVerdict(
                item="hand check",
                critical=True,
                verdict="missing" if not anatomy_passed else "shown",
                confidence=0.9,
                vision="no" if not anatomy_passed else "yes",
                description_says=False,
                evidence="defect" if not anatomy_passed else "ok",
                category="anatomy" if not anatomy_passed else "other",
                defect_type=defects[0] if defects else None,
                passed=anatomy_passed,
                bbox=[0.5, 0.5, 0.8, 0.8] if not anatomy_passed else None,
            ))
        else:
            verdicts.append(ItemVerdict(
                item="hand check",
                critical=True,
                verdict="shown",
                confidence=0.95,
                vision="yes",
                description_says=True,
                evidence="perfect hand",
                category="anatomy",
                passed=True,
            ))

        return Review(
            score=score,
            confidence=0.9,
            decision=decision,
            description="Review",
            items=verdicts,
            anatomy_passed=anatomy_passed,
            spatial_contact_passed=spatial_contact_passed,
            defects=defects,
        )

    def _run_repair_boundary_test(self, tmp_path, initial_rev: Review, rep_rev: Review) -> tuple[bool, str]:
        """Runs art.generate_art with mocked review responses and returns (accepted, final_status)."""
        story = _make_test_story()
        base_png = _make_png_bytes("red", (512, 512))
        rep_png = _make_png_bytes("green", (512, 512))

        mock_runner = MagicMock()
        mock_runner.generate.return_value = base_png
        mock_runner.inpaint.return_value = rep_png

        # Sequence of reviews: 1st is initial_rev, 2nd is rep_rev, subsequent attempts return initial_rev
        reviews = [initial_rev, rep_rev]

        async def mock_review_image(*args, **kwargs):
            if reviews:
                return reviews.pop(0)
            return initial_rev

        with patch("engine.original.review.review_image", side_effect=mock_review_image):
            art.generate_art(story, tmp_path, mock_runner, provider=MagicMock())

        art_records = json.loads((tmp_path / "art.json").read_text())
        record = art_records[0]
        saved_bytes = Path(record["image"]).read_bytes()
        is_repaired_adopted = (saved_bytes != base_png)
        return is_repaired_adopted, record["status"]

    def test_repaired_score_substantially_lower_is_rejected(self, tmp_path):
        """Case: Repaired fixed anatomy, but score dropped below (rev.score - 0.05). Must be REJECTED."""
        initial = self._make_review(score=0.85, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits"])
        # Score drops to 0.75 (drop is 0.10 > 0.05)
        repaired = self._make_review(score=0.75, decision="accept", anatomy_passed=True,
                                     spatial_contact_passed=True, defects=[])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert not accepted
        assert status == "needs_review"

    def test_repaired_score_just_below_tolerance_is_rejected(self, tmp_path):
        """Case: Repaired score drops by 0.051 (rev.score 0.85 -> 0.799). Must be REJECTED."""
        initial = self._make_review(score=0.85, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits"])
        repaired = self._make_review(score=0.799, decision="accept", anatomy_passed=True,
                                     spatial_contact_passed=True, defects=[])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert not accepted
        assert status == "needs_review"

    def test_repaired_score_at_exact_minus_005_tolerance_is_accepted(self, tmp_path):
        """Case: Repaired score drops by exactly 0.05 (0.85 -> 0.80) with anatomy passed. Must be ACCEPTED."""
        initial = self._make_review(score=0.85, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits"])
        repaired = self._make_review(score=0.80, decision="accept", anatomy_passed=True,
                                     spatial_contact_passed=True, defects=[])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert accepted
        assert status == "accept"

    def test_repaired_score_equal_with_anatomy_passed_is_accepted(self, tmp_path):
        """Case: Repaired score is equal (0.85 == 0.85) and anatomy passed. Must be ACCEPTED."""
        initial = self._make_review(score=0.85, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits"])
        repaired = self._make_review(score=0.85, decision="accept", anatomy_passed=True,
                                     spatial_contact_passed=True, defects=[])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert accepted
        assert status == "accept"

    def test_repaired_score_higher_with_anatomy_passed_is_accepted(self, tmp_path):
        """Case: Repaired score increases (0.85 -> 0.95) and anatomy passed. Must be ACCEPTED."""
        initial = self._make_review(score=0.85, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits"])
        repaired = self._make_review(score=0.95, decision="accept", anatomy_passed=True,
                                     spatial_contact_passed=True, defects=[])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert accepted
        assert status == "accept"

    def test_repaired_score_equal_with_persistent_defect_is_rejected(self, tmp_path):
        """Case: Candidate score is equal (0.85 == 0.85) but defect persists. Must be REJECTED."""
        initial = self._make_review(score=0.85, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits"])
        repaired = self._make_review(score=0.85, decision="regenerate", anatomy_passed=False,
                                     spatial_contact_passed=True, defects=["distorted_digits"])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert not accepted
        assert status == "needs_review"

    def test_repaired_score_higher_but_defect_count_unchanged_is_rejected(self, tmp_path):
        """Case: Candidate score increased (0.70 -> 0.85), but defect count is unchanged (1 -> 1) and anatomy failed.
        Must be REJECTED (defect not resolved)."""
        initial = self._make_review(score=0.70, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits"])
        repaired = self._make_review(score=0.85, decision="regenerate", anatomy_passed=False,
                                     spatial_contact_passed=True, defects=["distorted_digits"])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert not accepted
        assert status == "needs_review"

    def test_repaired_score_higher_and_defect_count_reduced_is_accepted(self, tmp_path):
        """Case: Defect count decreased (2 -> 1) AND score increased (0.70 -> 0.80).
        Meets branch: (len(rep_rev.defects) < len(rev.defects) and rep_rev.score > rev.score). Must be ACCEPTED."""
        initial = self._make_review(score=0.70, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits", "polycephaly"])
        repaired = self._make_review(score=0.80, decision="regenerate", anatomy_passed=False,
                                     spatial_contact_passed=True, defects=["distorted_digits"])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert accepted
        # Decision is regenerate because 1 defect remains, so status is needs_review, but candidate_png was adopted
        art_records = json.loads((tmp_path / "art.json").read_text())
        assert art_records[0]["review"]["score"] == 0.80
        assert art_records[0]["review"]["defects"] == ["distorted_digits"]

    def test_repaired_score_equal_when_defect_count_reduced_is_rejected(self, tmp_path):
        """Case: Defect count decreased (2 -> 1) BUT score did not strictly improve (0.70 == 0.70). Must be REJECTED."""
        initial = self._make_review(score=0.70, decision="regenerate", anatomy_passed=False,
                                    spatial_contact_passed=True, defects=["distorted_digits", "polycephaly"])
        repaired = self._make_review(score=0.70, decision="regenerate", anatomy_passed=False,
                                     spatial_contact_passed=True, defects=["distorted_digits"])

        accepted, status = self._run_repair_boundary_test(tmp_path, initial, repaired)
        assert not accepted
        # Retained initial panel
        art_records = json.loads((tmp_path / "art.json").read_text())
        assert art_records[0]["review"]["score"] == 0.70
        assert len(art_records[0]["review"]["defects"]) == 2

    def test_clean_panel_without_defects_does_not_trigger_inpaint(self, tmp_path):
        """Case: Initial review passes with no defects; runner.inpaint must NEVER be called."""
        story = _make_test_story()
        base_png = _make_png_bytes("green", (512, 512))

        mock_runner = MagicMock()
        mock_runner.generate.return_value = base_png

        clean_rev = self._make_review(score=0.95, decision="accept", anatomy_passed=True,
                                      spatial_contact_passed=True, defects=[])

        with patch("engine.original.review.review_image", new=AsyncMock(return_value=clean_rev)):
            art.generate_art(story, tmp_path, mock_runner, provider=MagicMock())

        assert not mock_runner.inpaint.called
        art_records = json.loads((tmp_path / "art.json").read_text())
        assert art_records[0]["status"] == "accept"
