"""Unit tests for Motion Bank: Ingest, Rights Gate, DWPose Extractor, Visualizer, and Storage."""
from __future__ import annotations

import json
from pathlib import Path
import cv2
import numpy as np
import pytest
import torch

from engine.acquisition.rights.models import RightsDeclaration, RightsStatus
from engine.motion_bank.models import (
    FramePoseData,
    MotionIngestRecord,
    MotionRecord,
    MotionSegment,
    MotionSourceType,
)
from engine.motion_bank.ingest import ingest_motion_source
from engine.motion_bank.segmenter import detect_cuts
from engine.motion_bank.visualizer import draw_skeleton_frame, render_skeleton_video
from engine.motion_bank.dwpose_extractor import DWPoseExtractor
from engine.motion_bank.storage import MotionBankStorage


def test_rights_gate_refusal_unknown(tmp_path: Path):
    """Verifies that UNKNOWN rights status is strictly rejected per owner rules."""
    rights = RightsDeclaration(status=RightsStatus.UNKNOWN)
    with pytest.raises(ValueError, match="Acquisition cannot proceed with UNKNOWN rights"):
        ingest_motion_source("dummy.mp4", tmp_path, rights)


def test_rights_gate_refusal_commentary_without_notes(tmp_path: Path):
    """Verifies that COMMENTARY_REVIEW without permission_notes is refused."""
    rights = RightsDeclaration(status=RightsStatus.COMMENTARY_REVIEW, permission_notes=None)
    with pytest.raises(ValueError, match="COMMENTARY_REVIEW requires permission_notes"):
        ingest_motion_source("dummy.mp4", tmp_path, rights)


def test_ingest_local_video(tmp_path: Path):
    """Tests local video file ingest with USER_OWNED rights."""
    # Create a small synthetic MP4 test video
    test_video = tmp_path / "sample_action.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(test_video), fourcc, 24.0, (320, 240))
    for i in range(24):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.circle(frame, (160 + i * 2, 120), 20, (255, 255, 255), -1)
        out.write(frame)
    out.release()

    workspace = tmp_path / "workspace"
    rights = RightsDeclaration(
        status=RightsStatus.USER_OWNED,
        permission_notes="Locally generated synthetic animation for test verification",
    )

    rec = ingest_motion_source(str(test_video), workspace, rights, title="Test Action")
    assert rec.title == "Test Action"
    assert rec.source_type == MotionSourceType.LOCAL_FILE
    assert rec.width == 320
    assert rec.height == 240
    assert rec.fps == 24.0
    assert rec.duration_sec > 0
    assert (workspace / "source.json").exists()


def test_segmenter_detect_cuts(tmp_path: Path):
    """Tests continuous video take detection."""
    test_video = tmp_path / "cut_test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(test_video), fourcc, 24.0, (160, 120))
    # Render 48 frames (2 seconds)
    for i in range(48):
        frame = np.full((120, 160, 3), 10 + i * 2, dtype=np.uint8)
        out.write(frame)
    out.release()

    cuts = detect_cuts(test_video, min_duration_sec=0.5)
    assert len(cuts) >= 1
    assert cuts[0].duration_sec >= 0.5
    assert cuts[0].fps == 24.0


def test_visualizer_draw_skeleton():
    """Verifies that OpenPose skeleton renders without error and generates correct canvas shapes."""
    body = [(0.5, 0.2, 0.9), (0.5, 0.3, 0.9), (0.4, 0.3, 0.8), (0.6, 0.3, 0.8)]
    canvas = draw_skeleton_frame(width=640, height=360, body_kpts=body, background="black")
    assert canvas.shape == (360, 640, 3)
    assert canvas.dtype == np.uint8
    # Ensure canvas is not entirely black (skeleton drawn)
    assert np.any(canvas > 0)


def test_visualizer_render_video(tmp_path: Path):
    """Tests rendering of a sequence of pose keypoints into an MP4 control video."""
    extractor = DWPoseExtractor()
    poses = [extractor.extract_frame_pose(np.zeros((100, 100, 3), dtype=np.uint8), i, i * 0.04, mock_if_missing=True) for i in range(10)]

    out_video = tmp_path / "control.mp4"
    render_skeleton_video(poses, out_video, fps=24.0, width=320, height=240)
    assert out_video.exists()
    assert out_video.stat().st_size > 0


def test_dwpose_extractor_synthetic_kinematics():
    """Verifies DWPose extractor fallback/mock kinematics produce valid 133-point wholebody data."""
    extractor = DWPoseExtractor()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pose = extractor.extract_frame_pose(frame, frame_index=0, timestamp_sec=0.0, mock_if_missing=True)

    assert pose.frame_index == 0
    assert len(pose.body) == 18
    assert pose.left_hand is not None and len(pose.left_hand) == 21
    assert pose.right_hand is not None and len(pose.right_hand) == 21
    assert pose.face is not None and len(pose.face) == 68
    assert pose.bbox is not None


def test_motion_bank_storage_and_safetensors(tmp_path: Path):
    """Tests saving and querying motion records in SQLite and serializing kinematics to safetensors."""
    storage = MotionBankStorage(tmp_path)
    extractor = DWPoseExtractor()

    # Generate 5 frames of mock kinematics
    poses = [
        extractor.extract_frame_pose(np.zeros((100, 100, 3), dtype=np.uint8), i, i * 0.04, mock_if_missing=True)
        for i in range(5)
    ]

    kp_path = tmp_path / "mot_001" / "motion.safetensors"
    record = MotionRecord(
        id="mot_samurai_slash_001",
        source_uri="local://test/samurai.mp4",
        action_title="Samurai Dash and Slash",
        action_summary="A rapid dash forward with horizontal blade draw",
        action_tags=["samurai", "sword", "fight", "dash"],
        duration_sec=2.5,
        fps=24.0,
        frame_count=60,
        resolution=(1280, 720),
        actor_track_id=1,
        keypoints_path=str(kp_path),
        control_video_path=str(tmp_path / "mot_001" / "control.mp4"),
    )

    # 1. Save motion record and safetensors
    saved = storage.save_motion(record, frames_poses=poses)
    assert saved.id == "mot_samurai_slash_001"
    assert kp_path.exists()

    # 2. Verify safetensors kinematic tensor
    tensor = storage.load_keypoints_tensor(kp_path)
    assert tensor.shape == (5, 133, 3)
    assert isinstance(tensor, torch.Tensor)

    # 3. Retrieve from SQLite
    retrieved = storage.get_motion("mot_samurai_slash_001")
    assert retrieved is not None
    assert retrieved.action_title == "Samurai Dash and Slash"
    assert "sword" in retrieved.action_tags

    # 4. Search by tag and query
    results_tag = storage.list_motions(tag="sword")
    assert len(results_tag) == 1
    assert results_tag[0].id == "mot_samurai_slash_001"

    results_search = storage.search_motions("dash")
    assert len(results_search) == 1
    assert results_search[0].id == "mot_samurai_slash_001"
