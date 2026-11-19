"""Unit tests for Phase 2: Image-Level Visual Quality Inspector."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from PIL import Image

from engine.inspector.face_engine import OpenFaceEngine
from engine.inspector.image_inspector import ImageInspector
from engine.inspector.schema import (
    FaceDetectionResult,
    InspectorConfig,
    QualityDecision,
)
from engine.inspector.topology import SkeletonTopologyValidator
from engine.motion_bank.dwpose_extractor import FramePoseData


def test_face_engine_readiness():
    """Confirms OpenCV YuNet and SFace models are ready on disk."""
    engine = OpenFaceEngine()
    assert engine.is_ready() is True


def test_face_engine_duplicate_character_detection():
    """Twin face embeddings with similarity >= 0.82 should be flagged as duplicate_character."""
    engine = OpenFaceEngine()
    # Create two twin normalized embeddings
    feat_1 = [0.1] * 128
    feat_2 = [0.1] * 128  # Cosine similarity == 1.0

    face_a = FaceDetectionResult(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9, embedding=feat_1)
    face_b = FaceDetectionResult(bbox=(0.5, 0.1, 0.7, 0.3), confidence=0.9, embedding=feat_2)

    defects = engine.check_face_defects([face_a, face_b], people_count=2, identity_threshold=0.82)
    assert any(d.category == "duplicate_character" for d in defects)
    dup = next(d for d in defects if d.category == "duplicate_character")
    assert dup.confidence >= 0.99
    assert dup.recommended_action == "inpaint"


def test_face_engine_extra_head_detection():
    """Detecting more faces than people bodies should be flagged as extra_head."""
    engine = OpenFaceEngine()
    feat = [0.05] * 128
    face_a = FaceDetectionResult(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9, embedding=feat)
    face_b = FaceDetectionResult(bbox=(0.5, 0.1, 0.7, 0.3), confidence=0.9, embedding=feat)

    # 2 faces detected for 1 person body
    defects = engine.check_face_defects([face_a, face_b], people_count=1)
    assert any(d.category == "extra_head" for d in defects)
    head_defect = next(d for d in defects if d.category == "extra_head")
    assert "extra head" in head_defect.evidence.lower()


def test_face_engine_distorted_face_collapsed_eyes():
    """Collapsed eye distance (< 0.10 * width) should be flagged as distorted_face."""
    engine = OpenFaceEngine()
    # Face bbox width = 0.4 - 0.1 = 0.30
    # Eye distance = |0.201 - 0.200| = 0.001 << 0.03
    face = FaceDetectionResult(
        bbox=(0.1, 0.1, 0.4, 0.4),
        confidence=0.92,
        landmarks=[(0.200, 0.25), (0.201, 0.25), (0.25, 0.30), (0.22, 0.35), (0.28, 0.35)],
        embedding=[0.05] * 128,
    )

    defects = engine.check_face_defects([face], people_count=1)
    assert any(d.category == "distorted_face" for d in defects)
    d = next(d for d in defects if d.category == "distorted_face")
    assert d.severity == "severe"
    assert "collapsed eye distance" in d.evidence.lower()


def test_topology_floating_hand_detection():
    """A confident wrist without shoulder or elbow should trigger extra_limbs (floating hand)."""
    validator = SkeletonTopologyValidator(min_conf=0.4)
    # OpenPose-18 body keypoints:
    # 0: Nose, 1: Neck, 2: RShoulder, 3: RElbow, 4: RWrist
    body = [(0.0, 0.0, 0.0)] * 18
    body[1] = (0.5, 0.2, 0.9)   # Confident neck
    # RWrist is confident, but RShoulder(2) and RElbow(3) have conf=0.0
    body[4] = (0.8, 0.4, 0.85)

    pose = FramePoseData(frame_index=0, timestamp_sec=0.0, body=body)
    defects = validator.validate_pose(pose, people_count=1)

    assert any(d.category == "extra_limbs" for d in defects)
    floating = next(d for d in defects if d.category == "extra_limbs")
    assert "without connected elbow" in floating.evidence.lower()


def test_topology_multiperson_occlusion_tolerance():
    """In multi-person interactions (people_count >= 2), occluded shoulders/elbows should not trigger false alarms."""
    validator = SkeletonTopologyValidator(min_conf=0.4)
    body = [(0.0, 0.0, 0.0)] * 18
    body[1] = (0.5, 0.2, 0.9)
    body[4] = (0.8, 0.4, 0.85)  # Wrist without elbow

    pose = FramePoseData(frame_index=0, timestamp_sec=0.0, body=body)
    # When 2 people are present (e.g. hug or handshake), floating hand check is bypassed
    defects = validator.validate_pose(pose, people_count=2)
    assert not any(d.category == "extra_limbs" for d in defects)


def test_image_inspector_clean_synthetic():
    """A clean image without defects should evaluate with status PASS and clean=True."""
    # Plain neutral canvas
    img = np.full((300, 300, 3), 128, dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    raw_bytes = buf.tobytes()

    inspector = ImageInspector(config=InspectorConfig(enable_vlm=False))
    decision = inspector.inspect(raw_bytes, prompt="a plain grey background")

    assert decision.overall_score == 100.0
    assert decision.status == "PASS"
    assert decision.clean is True
    assert len(decision.defects) == 0


def test_image_inspector_real_defect_image():
    """Evaluates real workspace test image (klein_cross_legged_101.png) on CPU CV."""
    real_img = Path("output/anatomy_labels/klein_cross_legged_101.png")
    if not real_img.is_file():
        pytest.skip("Test image klein_cross_legged_101.png not present")

    inspector = ImageInspector(config=InspectorConfig(enable_vlm=False))
    decision = inspector.inspect(real_img, prompt="sitting cross-legged", expected_people=1)

    assert isinstance(decision, QualityDecision)
    assert decision.overall_score >= 0.0
    assert decision.overall_score <= 100.0
    assert decision.seconds > 0.0
