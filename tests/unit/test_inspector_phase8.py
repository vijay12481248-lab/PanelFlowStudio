"""Unit tests for Phase 8: Reliability & Calibration Benchmark."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import torch

from engine.inspector.image_inspector import ImageInspector
from engine.inspector.schema import InspectorConfig, QualityDecision, VideoQualityDecision
from engine.inspector.temporal import TemporalVideoInspector
from tools.inspector.calibrate_inspector import run_calibration


def test_calibration_fpr_under_threshold(tmp_path):
    """Validates that False Positive Rate (FPR) on clean ground-truth images is strictly < 2.0%."""
    # Run calibration on first 15 images (contains verified clean images)
    results = run_calibration(
        limit=15,
        enable_vlm=False,
        output_report_path=str(tmp_path / "test_report.md"),
    )
    assert results["clean_expected"] > 0
    assert results["false_positive_rate"] < 0.02
    assert results["false_positives"] == 0


def test_calibration_latency_profile(tmp_path):
    """Validates that average inspection latency on CPU is strictly < 1500 ms."""
    results = run_calibration(
        limit=10,
        enable_vlm=False,
        output_report_path=str(tmp_path / "test_report.md"),
    )
    assert results["avg_latency_ms"] < 1500.0
    assert results["avg_latency_ms"] > 0.0


def test_vram_confinement():
    """Validates that CPU CV pipeline maintains strictly zero GPU VRAM consumption."""
    test_img = Path("output/anatomy_labels/klein_cross_legged_101.png")
    if not test_img.is_file():
        pytest.skip("Test image not found")

    inspector = ImageInspector(InspectorConfig(enable_vlm=False))
    if torch.cuda.is_available():
        vram_start = torch.cuda.memory_allocated(0)
        decision = inspector.inspect(test_img, prompt="sitting cross-legged", expected_people=1)
        vram_end = torch.cuda.memory_allocated(0)
        assert vram_end - vram_start == 0, f"Expected 0 MB VRAM delta, but got {vram_end - vram_start} bytes"
    else:
        decision = inspector.inspect(test_img, prompt="sitting cross-legged", expected_people=1)
    assert isinstance(decision, QualityDecision)


def test_calibration_report_generated():
    """Validates that docs/quality_inspector/BENCHMARK_CALIBRATION_REPORT.md is produced with required sections."""
    report_file = Path("docs/quality_inspector/BENCHMARK_CALIBRATION_REPORT.md")
    assert report_file.is_file()
    content = report_file.read_text(encoding="utf-8")
    assert "# AI Visual Quality Inspector — Reliability & Calibration Benchmark Report" in content
    assert "Executive Performance Summary" in content
    assert "False Positive Rate (FPR)" in content
    assert "Confusion Matrix" in content
    assert "Video Temporal Consistency Benchmark" in content
    assert "Architectural Verification & Commercial Monetization" in content


def test_video_benchmark_temporal_consistency():
    """Validates that TemporalVideoInspector correctly evaluates benchmark video sequence."""
    video_path = Path("output/bench_cpu.mp4")
    if not video_path.is_file():
        pytest.skip("output/bench_cpu.mp4 not found")

    inspector = TemporalVideoInspector()
    decision = inspector.inspect_video(video_path)
    assert isinstance(decision, VideoQualityDecision)
    assert decision.total_frames >= 24
    assert decision.overall_score >= 80.0
    assert decision.status in ("PASS", "WARN")


def test_vlm_defect_recall_mapping():
    """Validates that semantic VLM defects are mapped to DefectRecords with inpaint recommendation."""
    test_img = Path("output/anatomy_labels/klein_cross_legged_101.png")
    if not test_img.is_file():
        pytest.skip("Test image not found")

    # Mock judge that reports extra hands
    mock_judge = MagicMock()
    mock_judge.name = "mock_vlm_judge"

    async def mock_ask(img_bytes, prompt_str):
        p_low = prompt_str.lower()
        if "list every hand" in p_low or "hand 1:" in p_low:
            return "HAND 1: right hand on knee\nHAND 2: left hand on knee\nHAND 3: extra stray hand near floor"
        if "flags" in p_low or "whole picture" in p_low or "zoomed crop" in p_low:
            return "PEOPLE: 1\nTEXT: no\nDOUBLE: no\nMERGED: no\nEVIDENCE: girl sitting on floor"
        return "yes"

    mock_judge.ask = AsyncMock(side_effect=mock_ask)

    config = InspectorConfig(enable_vlm=True)
    inspector = ImageInspector(config, judges=[mock_judge])
    decision = inspector.inspect(
        test_img,
        prompt="A young woman sitting cross-legged, both hands resting on her knees.",
        expected_people=1,
    )

    assert isinstance(decision, QualityDecision)
    assert any(d.category == "extra_hands" for d in decision.defects)
    hand_defect = next(d for d in decision.defects if d.category == "extra_hands")
    assert hand_defect.recommended_action == "inpaint"
    assert decision.status in ("RETRY", "FAIL")
