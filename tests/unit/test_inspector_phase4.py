"""Unit tests for Phase 4: Video Quality Inspector, Motion Jitter, Flickering, and Face Drift."""
from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from engine.inspector.schema import (
    FaceDetectionResult,
    InspectorConfig,
    TemporalDefectRecord,
    VideoQualityDecision,
)
from engine.inspector.temporal import TemporalVideoInspector, _bbox_iou
from engine.motion_bank.models import FramePoseData


def _create_synthetic_mp4(
    file_path: Path,
    width: int = 160,
    height: int = 120,
    fps: float = 24.0,
    segments: list[tuple[int, tuple[int, int, int]]] = None,
) -> Path:
    """Helper creating synthetic MP4 test videos using OpenCV VideoWriter."""
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


def test_scene_cut_detection(tmp_path):
    """Detects scene cut transition between two distinctly colored segments without artificial chops."""
    video_path = tmp_path / "two_scenes.mp4"
    # Shot 1: Blue (24 frames = 1.0s), Shot 2: Red (24 frames = 1.0s)
    _create_synthetic_mp4(
        video_path,
        segments=[
            (24, (255, 0, 0)),
            (24, (0, 0, 255)),
        ],
    )

    inspector = TemporalVideoInspector()
    shots = inspector.detect_scene_cuts_opencv(video_path, sample_step=2)

    assert len(shots) == 2
    assert shots[0][0] == 0.0
    assert 0.90 <= shots[0][1] <= 1.10
    assert 0.90 <= shots[1][0] <= 1.10
    assert 1.90 <= shots[1][1] <= 2.10


def test_root_motion_pan_tolerance():
    """Camera pan shifts all body joints uniformly; root compensation prevents false positive jitter."""
    inspector = TemporalVideoInspector()

    # Frame 0: Neck at (0.40, 0.40), Right Wrist at (0.50, 0.50)
    body_0 = [(0.0, 0.0, 0.0)] * 18
    body_0[1] = (0.40, 0.40, 0.90)  # Neck
    body_0[4] = (0.50, 0.50, 0.90)  # RWrist
    pose_0 = FramePoseData(frame_index=0, timestamp_sec=0.0, body=body_0)

    # Frame 1: Camera pans right by 0.20; both Neck and RWrist shift by +0.20
    body_1 = [(0.0, 0.0, 0.0)] * 18
    body_1[1] = (0.60, 0.40, 0.90)  # Neck shifted by +0.20
    body_1[4] = (0.70, 0.50, 0.90)  # RWrist shifted by +0.20
    pose_1 = FramePoseData(frame_index=2, timestamp_sec=0.08, body=body_1)

    poses = [(0, 0.0, pose_0), (2, 0.08, pose_1)]
    defects = inspector.analyze_keypoint_jitter(poses, shot_idx=0, start_sec=0.0, end_sec=0.08)

    # Since wrist moved exactly with the neck root, relative displacement is 0.0 (no defect)
    assert len(defects) == 0


def test_keypoint_velocity_jitter():
    """Limb extremity teleporting relative to stationary body triggers temporal_jitter defect."""
    inspector = TemporalVideoInspector()

    body_0 = [(0.0, 0.0, 0.0)] * 18
    body_0[1] = (0.40, 0.40, 0.90)  # Neck stationary
    body_0[4] = (0.45, 0.50, 0.90)  # RWrist
    pose_0 = FramePoseData(frame_index=0, timestamp_sec=0.0, body=body_0)

    body_1 = [(0.0, 0.0, 0.0)] * 18
    body_1[1] = (0.40, 0.40, 0.90)  # Neck stationary
    body_1[4] = (0.75, 0.50, 0.90)  # RWrist teleported by 0.30 norm units (> 0.18 threshold)
    pose_1 = FramePoseData(frame_index=2, timestamp_sec=0.08, body=body_1)

    poses = [(0, 0.0, pose_0), (2, 0.08, pose_1)]
    defects = inspector.analyze_keypoint_jitter(poses, shot_idx=0, start_sec=0.0, end_sec=0.08)

    assert len(defects) == 1
    assert defects[0].category == "temporal_jitter"
    assert defects[0].severity == "moderate"
    assert "Right Wrist" in defects[0].evidence


def test_flickering_limbs_dropout_and_popin():
    """Detects both limb dropouts (1->0->1) and phantom limb pop-ins (0->1->0)."""
    inspector = TemporalVideoInspector()

    def make_pose(f_idx, r_conf, l_conf):
        b = [(0.0, 0.0, 0.0)] * 18
        b[1] = (0.5, 0.3, 0.9)
        b[4] = (0.4, 0.6, r_conf)  # Right hand
        b[7] = (0.6, 0.6, l_conf)  # Left hand
        return FramePoseData(frame_index=f_idx, timestamp_sec=f_idx * 0.04, body=b)

    # Sequence with Right Hand dropout (0.8 -> 0.0 -> 0.8) and Left Hand phantom pop-in (0.0 -> 0.8 -> 0.0)
    p0 = make_pose(0, 0.8, 0.0)
    p1 = make_pose(2, 0.0, 0.8)  # R dropped out, L popped in
    p2 = make_pose(4, 0.8, 0.0)  # R restored, L vanished

    poses = [(0, 0.0, p0), (2, 0.08, p1), (4, 0.16, p2)]
    defects = inspector.analyze_flickering_limbs(poses, shot_idx=0, start_sec=0.0, end_sec=0.16)

    assert len(defects) == 2
    cats = [d.details["flicker_type"] for d in defects]
    assert "dropout" in cats
    assert "phantom_popin" in cats


def test_dropped_actor_detection():
    """Detects actor disappearing mid-shot without exiting the camera boundary."""
    inspector = TemporalVideoInspector()

    # Frame 0: Character in center of screen
    body_present = [(0.5, 0.5, 0.9)] * 14
    pose_0 = FramePoseData(
        frame_index=0,
        timestamp_sec=0.0,
        body=body_present,
        bbox=(0.3, 0.2, 0.7, 0.8),  # Safely inside center screen
    )

    # Frame 1: Completely missing body (0 joints)
    pose_1 = FramePoseData(
        frame_index=2,
        timestamp_sec=0.08,
        body=[(0.0, 0.0, 0.0)] * 18,
    )

    # Frame 2: Character reappears
    pose_2 = FramePoseData(
        frame_index=4,
        timestamp_sec=0.16,
        body=body_present,
        bbox=(0.3, 0.2, 0.7, 0.8),
    )

    poses = [(0, 0.0, pose_0), (2, 0.08, pose_1), (4, 0.16, pose_2)]
    defects = inspector.analyze_dropped_actors(poses, shot_idx=0, start_sec=0.0, end_sec=0.16)

    assert len(defects) == 1
    assert defects[0].category == "dropped_actor"
    assert defects[0].severity == "severe"


def test_multi_person_face_drift():
    """Spatial tracking prevents two distinct characters from triggering cross-face identity drift."""
    inspector = TemporalVideoInspector()

    # Mock face engine similarity: identical vectors return 1.0, differing return 0.20
    inspector.face_engine = MagicMock()
    inspector.face_engine.compute_similarity.side_effect = lambda a, b: 1.0 if a == b else 0.20

    # Two characters in Frame 0: Char A on left (0.1..0.3), Char B on right (0.7..0.9)
    emb_a = [1.0] * 128
    emb_b = [-1.0] * 128
    emb_drifted = [0.0] * 128

    f0_faces = [
        FaceDetectionResult(bbox=(0.10, 0.10, 0.30, 0.30), confidence=0.9, embedding=emb_a),
        FaceDetectionResult(bbox=(0.70, 0.10, 0.90, 0.30), confidence=0.9, embedding=emb_b),
    ]

    # Frame 1: Char A stays stable, Char B drifts
    f1_faces = [
        FaceDetectionResult(bbox=(0.12, 0.10, 0.32, 0.30), confidence=0.9, embedding=emb_a),
        FaceDetectionResult(bbox=(0.72, 0.10, 0.92, 0.30), confidence=0.9, embedding=emb_drifted),
    ]

    shot_faces = [(0, 0.0, f0_faces), (2, 0.08, f1_faces)]
    defects = inspector.analyze_identity_drift(shot_faces, shot_idx=0, start_sec=0.0, end_sec=0.08)

    # Only Char B drifted; Char A was not compared against Char B
    assert len(defects) == 1
    assert defects[0].category == "identity_drift"
    assert defects[0].severity == "severe"


def test_real_video_inspection():
    """Verifies end-to-end execution on real workspace video (output/bench_cpu.mp4) at 0 MB VRAM."""
    bench_video = Path("output/bench_cpu.mp4")
    if not bench_video.is_file():
        pytest.skip("output/bench_cpu.mp4 not present in workspace")

    inspector = TemporalVideoInspector()
    decision = inspector.inspect_video(bench_video, sample_step=5)

    assert isinstance(decision, VideoQualityDecision)
    assert decision.total_frames == 150
    assert 4.5 <= decision.duration_sec <= 5.5
    assert decision.shots_detected >= 1
    assert 0.0 <= decision.overall_score <= 100.0
    assert decision.status in ("PASS", "RETRY", "MANUAL_REVIEW")
    assert decision.seconds > 0.0
