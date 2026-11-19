"""Unit tests for Phase 3: Image Auto-Correction, Mask Generation, and Revalidation."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from PIL import Image

from engine.comfyui.art import ArtImage
from engine.inspector.mask_gen import DefectMaskGenerator
from engine.inspector.repair import ImageRepairEngine, RepairResult
from engine.inspector.schema import DefectRecord, QualityDecision


def _create_synthetic_png(width: int = 100, height: int = 100) -> bytes:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = (120, 120, 120)
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def test_mask_generator_category_adaptive_padding():
    """Defects with category extra_hands (0.20 pad) should generate a larger mask area than stray_text (0.08 pad)."""
    gen = DefectMaskGenerator()
    w, h = 500, 500
    bbox = (0.2, 0.2, 0.4, 0.4)

    hand_defect = DefectRecord(category="extra_hands", bbox=bbox)
    text_defect = DefectRecord(category="stray_text", bbox=bbox)

    hand_mask = gen.generate_mask(w, h, [hand_defect])
    text_mask = gen.generate_mask(w, h, [text_defect])

    hand_area = np.count_nonzero(hand_mask > 128)
    text_area = np.count_nonzero(text_mask > 128)

    assert hand_area > text_area
    assert hand_area > (0.2 * w) * (0.2 * h)  # Larger than base box


def test_mask_generator_gaussian_feathering():
    """Gaussian feathering should produce smooth edge gradient values strictly between 0 and 255."""
    gen = DefectMaskGenerator(feather_radius=21)
    mask = gen.generate_mask(200, 200, [DefectRecord(category="extra_hands", bbox=(0.2, 0.2, 0.6, 0.6))])

    # Check for presence of intermediate transition values (1..254) along boundary
    intermediate_vals = mask[(mask > 0) & (mask < 255)]
    assert len(intermediate_vals) > 0
    assert intermediate_vals.min() >= 1
    assert intermediate_vals.max() <= 254


def test_repair_engine_non_destructive_file_saving(tmp_path):
    """Auto-repair with file input creates a new versioned file and leaves the original untouched."""
    orig_file = tmp_path / "source_artwork.png"
    orig_bytes = _create_synthetic_png(120, 120)
    orig_file.write_bytes(orig_bytes)

    # Clean decision requires no inpaint
    clean_decision = QualityDecision(overall_score=95.0, status="PASS", clean=True, defects=[])

    repair_engine = ImageRepairEngine()
    result = repair_engine.repair_image(orig_file, decision=clean_decision, output_dir=tmp_path / "repaired")

    assert orig_file.read_bytes() == orig_bytes  # Untouched
    assert result.success is True
    assert result.original_score == 95.0


def test_repair_engine_inpaint_mock_and_revalidation(tmp_path):
    """Verifies localized inpainting pass triggers ComfyUI bridge and updates decision."""
    source_bytes = _create_synthetic_png(200, 200)
    defect = DefectRecord(
        category="extra_hands",
        bbox=(0.2, 0.2, 0.4, 0.4),
        severity="severe",
        recommended_action="inpaint",
    )
    initial_decision = QualityDecision(
        overall_score=68.0,
        status="RETRY",
        clean=False,
        defects=[defect],
    )

    repaired_bytes = _create_synthetic_png(200, 200)
    revalidated_decision = QualityDecision(
        overall_score=92.0,
        status="PASS",
        clean=True,
        defects=[],
    )

    # Mock ArtEngine
    mock_art = MagicMock()
    mock_art.client.upload_image_bytes.side_effect = ["input_hash.png", "mask_hash.png"]
    mock_art.registry.load.return_value = ({
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "4": {"class_type": "LoadImage", "inputs": {"image": ""}},
        "5": {"class_type": "LoadImageMask", "inputs": {"image": ""}},
        "8": {"class_type": "KSampler", "inputs": {"seed": 0, "denoise": 0.75}},
        "11": {"class_type": "SaveImage", "inputs": {"filename_prefix": ""}},
    }, "dummy_sha")
    mock_art.registry.metadata.return_value = {
        "patch_slots": {
            "prompt": {"node_id": "2", "input": "text", "class_type": "CLIPTextEncode"},
            "negative_prompt": {"node_id": "3", "input": "text", "class_type": "CLIPTextEncode"},
            "seed": {"node_id": "8", "input": "seed", "class_type": "KSampler"},
            "reference_image": {"node_id": "4", "input": "image", "class_type": "LoadImage"},
            "mask_image": {"node_id": "5", "input": "image", "class_type": "LoadImageMask"},
            "denoise": {"node_id": "8", "input": "denoise", "class_type": "KSampler"},
            "filename_prefix": {"node_id": "11", "input": "filename_prefix", "class_type": "SaveImage"},
        }
    }
    mock_art.run.return_value = (repaired_bytes, "prompt_101", {})

    # Mock ImageInspector
    mock_inspector = MagicMock()
    mock_inspector.inspect.return_value = revalidated_decision

    engine = ImageRepairEngine(art_engine=mock_art, inspector=mock_inspector)
    res = engine.repair_image(
        source_bytes,
        decision=initial_decision,
        prompt="girl sitting cross-legged",
    )

    assert res.success is True
    assert res.strategy_used == "inpaint"
    assert res.original_score == 68.0
    assert res.final_score == 92.0
    assert res.score_improvement == 24.0
    assert res.revalidated_decision.status == "PASS"
    assert mock_art.run.called


def test_repair_engine_redraw_fallback(tmp_path):
    """Verifies fallback to global redraw generation with anatomy rules when defect is structural."""
    source_bytes = _create_synthetic_png(200, 200)
    defect = DefectRecord(
        category="extra_limbs",
        bbox=(0.1, 0.1, 0.9, 0.9),
        severity="severe",
        recommended_action="redraw",  # Forces redraw path
    )
    initial_decision = QualityDecision(
        overall_score=50.0,
        status="RETRY",
        clean=False,
        defects=[defect],
    )

    new_art_bytes = _create_synthetic_png(200, 200)
    revalidated_decision = QualityDecision(
        overall_score=88.0,
        status="PASS",
        clean=True,
        defects=[],
    )

    mock_art = MagicMock()
    mock_art.generate.return_value = ArtImage(
        png=new_art_bytes,
        width=200,
        height=200,
        prompt_id="prompt_202",
        workflow_id="hidream_i1_fast",
        workflow_sha256="sha",
        model_files=[],
        source_output={},
        seed=12345,
    )

    mock_inspector = MagicMock()
    mock_inspector.inspect.return_value = revalidated_decision

    engine = ImageRepairEngine(art_engine=mock_art, inspector=mock_inspector)
    res = engine.repair_image(
        source_bytes,
        decision=initial_decision,
        prompt="standing warrior",
    )

    assert res.success is True
    assert res.strategy_used == "redraw"
    assert res.score_improvement == 38.0
    assert mock_art.generate.called


def test_mask_generator_tile_fallback():
    """Unbounded defect with tile='zoom_hands' resolves to deterministic quadrant coordinates."""
    gen = DefectMaskGenerator()
    w, h = 500, 500
    defect = DefectRecord(
        category="extra_hands",
        bbox=None,
        tile="zoom_hands",
        recommended_action="inpaint",
    )

    mask, coverage = gen.generate_mask_with_coverage(w, h, [defect])
    assert coverage > 0.10
    assert np.any(mask > 0)
    # Lower half of the image should have high mask activation
    lower_half = mask[int(h * 0.45) :, :]
    assert np.count_nonzero(lower_half > 128) > 0


def test_repair_engine_context_prompt_refinement():
    """Context-aware prompt refinement injects positive anatomical guidance based on detected defects."""
    engine = ImageRepairEngine()
    defects = [
        DefectRecord(category="extra_hands", evidence="Third hand detected on shoulder"),
        DefectRecord(category="distorted_face", evidence="Eye collapse"),
    ]
    refined = engine._refine_inpaint_prompt("1girl looking at camera", defects)
    assert "1girl looking at camera" in refined
    assert "anatomically correct hands" in refined
    assert "symmetrical detailed face" in refined


def test_repair_engine_mask_overflow_guard():
    """When defects cover > 45% of canvas, inpainting is skipped and escalated directly to global redraw."""
    source_bytes = _create_synthetic_png(200, 200)
    # Create large defects covering majority of canvas
    large_defect = DefectRecord(
        category="extra_limbs",
        bbox=(0.05, 0.05, 0.95, 0.95),  # ~81% area
        recommended_action="inpaint",
    )
    initial_decision = QualityDecision(
        overall_score=45.0,
        status="RETRY",
        clean=False,
        defects=[large_defect],
    )

    new_art_bytes = _create_synthetic_png(200, 200)
    reval_decision = QualityDecision(
        overall_score=85.0,
        status="PASS",
        clean=True,
        defects=[],
    )

    mock_art = MagicMock()
    mock_art.generate.return_value = ArtImage(
        png=new_art_bytes,
        width=200,
        height=200,
        prompt_id="prompt_overflow_fallback",
        workflow_id="hidream_i1_fast",
        workflow_sha256="sha",
        model_files=[],
        source_output={},
        seed=9999,
    )

    mock_inspector = MagicMock()
    mock_inspector.inspect.return_value = reval_decision

    engine = ImageRepairEngine(art_engine=mock_art, inspector=mock_inspector)
    res = engine.repair_image(
        source_bytes,
        decision=initial_decision,
        prompt="heroic knight",
    )

    # Inpaint should be bypassed because mask > 45%
    assert not mock_art.run.called
    assert mock_art.generate.called
    assert res.strategy_used == "redraw"
    assert any("inpaint_skipped_mask_overflow" in a for a in res.actions_taken)
    assert res.success is True


def test_repair_engine_adaptive_denoise_scheduling():
    """Inpainting retries use adaptive denoise scheduling (0.65 on attempt 1, 0.78 on attempt 2)."""
    source_bytes = _create_synthetic_png(200, 200)
    defect = DefectRecord(
        category="extra_hands",
        bbox=(0.3, 0.3, 0.5, 0.5),
        recommended_action="inpaint",
    )
    initial_decision = QualityDecision(
        overall_score=60.0,
        status="RETRY",
        clean=False,
        defects=[defect],
    )

    mock_art = MagicMock()
    mock_art.client.upload_image_bytes.side_effect = ["input.png", "mask.png", "input.png", "mask.png"]
    mock_art.registry.load.return_value = ({
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "4": {"class_type": "LoadImage", "inputs": {"image": ""}},
        "5": {"class_type": "LoadImageMask", "inputs": {"image": ""}},
        "8": {"class_type": "KSampler", "inputs": {"seed": 0, "denoise": 0.75}},
        "11": {"class_type": "SaveImage", "inputs": {"filename_prefix": ""}},
    }, "dummy_sha")
    mock_art.registry.metadata.return_value = {
        "patch_slots": {
            "prompt": {"node_id": "2", "input": "text", "class_type": "CLIPTextEncode"},
            "negative_prompt": {"node_id": "3", "input": "text", "class_type": "CLIPTextEncode"},
            "seed": {"node_id": "8", "input": "seed", "class_type": "KSampler"},
            "reference_image": {"node_id": "4", "input": "image", "class_type": "LoadImage"},
            "mask_image": {"node_id": "5", "input": "image", "class_type": "LoadImageMask"},
            "denoise": {"node_id": "8", "input": "denoise", "class_type": "KSampler"},
            "filename_prefix": {"node_id": "11", "input": "filename_prefix", "class_type": "SaveImage"},
        }
    }

    # First attempt fails to improve score (remains 60.0), second attempt succeeds (88.0)
    first_reval = QualityDecision(overall_score=60.0, status="RETRY", clean=False, defects=[defect])
    second_reval = QualityDecision(overall_score=88.0, status="PASS", clean=True, defects=[])

    mock_art.run.side_effect = [
        (source_bytes, "prompt_fail", {}),
        (source_bytes, "prompt_succ", {}),
    ]

    mock_inspector = MagicMock()
    mock_inspector.inspect.side_effect = [first_reval, second_reval]

    engine = ImageRepairEngine(art_engine=mock_art, inspector=mock_inspector)
    res = engine.repair_image(
        source_bytes,
        decision=initial_decision,
        prompt="girl with cat",
        max_attempts=2,
    )

    assert res.attempts == 2
    assert "denoise_0.65" in res.actions_taken[0]
    assert "denoise_0.78" in res.actions_taken[1]
    assert res.success is True

