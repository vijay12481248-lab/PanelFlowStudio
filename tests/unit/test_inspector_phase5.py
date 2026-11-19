"""Unit tests for Phase 5: Video Auto-Correction, Optical Flow Interpolation, and Shot Redraw Splicing."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from engine.inspector.schema import (
    InspectorConfig,
    TemporalDefectRecord,
    VideoQualityDecision,
)
from engine.inspector.temporal import TemporalVideoInspector
from engine.inspector.video_repair import (
    VideoRepairEngine,
    _extract_target_defective_frames,
    _interpolate_motion_bidirectional,
)


def _create_synthetic_video(
    file_path: Path,
    width: int = 160,
    height: int = 120,
    fps: float = 24.0,
    segments: list[tuple[int, tuple[int, int, int]]] = None,
) -> Path:
    """Helper generating synthetic MP4 files for video repair tests."""
    if segments is None:
        segments = [(24, (120, 120, 120))]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(file_path), fourcc, fps, (width, height))
    for num_frames, color in segments:
        frame = np.full((height, width, 3), color, dtype=np.uint8)
        for _ in range(num_frames):
            out.write(frame)
    out.release()
    return file_path


def test_optical_flow_bidirectional_interpolation():
    """Bidirectional optical flow smoothly warps moving features toward intermediate timestamp."""
    w, h = 100, 100
    frame_prev = np.zeros((h, w, 3), dtype=np.uint8)
    frame_next = np.zeros((h, w, 3), dtype=np.uint8)

    # Feature moving horizontally from x=44 to x=56
    cv2.circle(frame_prev, (44, 50), 12, (255, 255, 255), -1)
    cv2.circle(frame_next, (56, 50), 12, (255, 255, 255), -1)

    interp = _interpolate_motion_bidirectional(frame_prev, frame_next, alpha=0.5)

    assert interp.shape == (h, w, 3)
    # The intermediate frame should show high activation in the middle range (x=45..55)
    center_region = interp[45:55, 45:55, :]
    assert np.max(center_region) > 50


def test_flicker_frame_targeting():
    """Extracts specifically the defect frame index without flagging clean surrounding anchors."""
    defects = [
        TemporalDefectRecord(
            category="flickering_limbs",
            start_sec=0.0,
            end_sec=0.16,
            frame_indices=[0, 2, 4],
            details={"frame": 2, "flicker_type": "dropout"},
            recommended_action="inpaint",
        ),
        TemporalDefectRecord(
            category="dropped_actor",
            start_sec=0.5,
            end_sec=0.66,
            frame_indices=[12, 14, 16],
            details={"dropped_frame": 14},
            recommended_action="inpaint",
        ),
    ]

    target_indices = _extract_target_defective_frames(defects, total_frames=24, fps=24.0)

    # Exactly frames 2 and 14 should be targeted. Anchor frames (0, 4, 12, 16) must not be marked!
    assert target_indices == {2, 14}
    assert 0 not in target_indices
    assert 4 not in target_indices
    assert 12 not in target_indices
    assert 16 not in target_indices


def test_multi_shot_redraw_splice(tmp_path):
    """Splices newly generated shots into defective video intervals using FFmpeg concat."""
    source_video = tmp_path / "source_3shot.mp4"
    # Shot 1: Blue (24 frames = 1s), Shot 2: Green (24 frames = 1s), Shot 3: Red (24 frames = 1s)
    _create_synthetic_video(
        source_video,
        segments=[
            (24, (255, 0, 0)),
            (24, (0, 255, 0)),
            (24, (0, 0, 255)),
        ],
    )

    defect = TemporalDefectRecord(
        category="identity_drift",
        start_sec=1.0,
        end_sec=2.0,
        severity="severe",
        recommended_action="redraw",
    )
    decision = VideoQualityDecision(
        overall_score=55.0,
        status="RETRY",
        clean=False,
        defects=[defect],
        duration_sec=3.0,
        total_frames=72,
        fps=24.0,
        shots_detected=3,
    )

    # Mock shot generator producing a yellow replacement shot (BGR: 0, 255, 255)
    def mock_generator(s: float, e: float, seed: int) -> Path:
        out_shot = tmp_path / f"replacement_{seed}.mp4"
        return _create_synthetic_video(out_shot, segments=[(24, (0, 255, 255))])

    engine = VideoRepairEngine()
    repaired_path, reval_decision, meta = engine.repair_video(
        source_video,
        decision=decision,
        output_dir=tmp_path / "repaired",
        shot_generator_fn=mock_generator,
    )

    assert repaired_path.is_file()
    assert repaired_path != source_video
    assert "shot_redrawn" in str(meta["actions_applied"])

    # Check spliced video properties
    cap = cv2.VideoCapture(str(repaired_path))
    assert cap.isOpened()
    fcount = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    assert 60 <= fcount <= 80  # ~3 seconds preserved
    cap.release()


def test_video_repair_non_destructive_and_revalidation(tmp_path):
    """Frame-level optical flow repair preserves source video bit-for-bit and outputs versioned MP4."""
    source_video = tmp_path / "flicker_clip.mp4"
    # Clean grey frames with a 1-frame black glitch at frame 12
    segments = [(12, (150, 150, 150)), (1, (0, 0, 0)), (11, (150, 150, 150))]
    _create_synthetic_video(source_video, segments=segments)
    orig_bytes = source_video.read_bytes()

    defect = TemporalDefectRecord(
        category="flickering_limbs",
        start_sec=0.45,
        end_sec=0.55,
        frame_indices=[11, 12, 13],
        details={"frame": 12},
        recommended_action="inpaint",
    )
    initial_decision = VideoQualityDecision(
        overall_score=75.0,
        status="RETRY",
        clean=False,
        defects=[defect],
        duration_sec=1.0,
        total_frames=24,
        fps=24.0,
    )

    engine = VideoRepairEngine()
    repaired_path, revalidated, meta = engine.repair_video(
        source_video,
        decision=initial_decision,
        output_dir=tmp_path / "repaired",
    )

    # 1. Non-destructive: source video is completely untouched
    assert source_video.read_bytes() == orig_bytes

    # 2. Versioned output asset created
    assert repaired_path.is_file()
    assert repaired_path.parent == (tmp_path / "repaired")
    assert repaired_path.name.startswith("flicker_clip_repaired_")

    # 3. Metadata shows optical flow interpolation applied
    assert any("optical_flow_interpolation" in a for a in meta["actions_applied"])
    assert "revalidated_score" in meta


def test_real_video_repair_flow(tmp_path):
    """Executes non-destructive repair and revalidation on workspace video (output/bench_cpu.mp4)."""
    bench_video = Path("output/bench_cpu.mp4")
    if not bench_video.is_file():
        pytest.skip("output/bench_cpu.mp4 not present in workspace")

    orig_bytes = bench_video.read_bytes()

    # Create synthetic defect record for bench video
    defect = TemporalDefectRecord(
        category="flickering_limbs",
        start_sec=1.0,
        end_sec=1.1,
        frame_indices=[30, 31, 32],
        details={"frame": 31},
        recommended_action="inpaint",
    )
    decision = VideoQualityDecision(
        overall_score=80.0,
        status="RETRY",
        clean=False,
        defects=[defect],
        duration_sec=5.0,
        total_frames=150,
        fps=30.0,
    )

    engine = VideoRepairEngine()
    repaired_path, reval_decision, meta = engine.repair_video(
        bench_video,
        decision=decision,
        output_dir=tmp_path / "repaired",
    )

    assert bench_video.read_bytes() == orig_bytes  # Source untouched
    assert repaired_path.is_file()
    assert reval_decision.total_frames == 150
    assert 4.5 <= reval_decision.duration_sec <= 5.5
