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
    poses = [extractor.extract_frame_pose(np.zeros((100, 100, 3), dtype=np.uint8), i, i * 0.04, synthetic=True) for i in range(10)]

    out_video = tmp_path / "control.mp4"
    render_skeleton_video(poses, out_video, fps=24.0, width=320, height=240)
    assert out_video.exists()
    assert out_video.stat().st_size > 0


def test_dwpose_extractor_synthetic_kinematics():
    """Verifies DWPose extractor fallback/mock kinematics produce valid 133-point wholebody data."""
    extractor = DWPoseExtractor()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pose = extractor.extract_frame_pose(frame, frame_index=0, timestamp_sec=0.0, synthetic=True)

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
        extractor.extract_frame_pose(np.zeros((100, 100, 3), dtype=np.uint8), i, i * 0.04, synthetic=True)
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


def test_wholebody_layout_is_converted_to_openpose18():
    """DWPose emits COCO-WholeBody order; storage/visualiser expect OpenPose-18 + hands + face."""
    from engine.motion_bank.dwpose_extractor import wholebody_to_internal

    kpts = [(float(i), float(i) * 2, 0.9) for i in range(133)]
    body, lh, rh, face = wholebody_to_internal(kpts)

    assert len(body) == 18 and len(lh) == 21 and len(rh) == 21 and len(face) == 68
    assert body[0][0] == 0.0                                  # nose
    assert body[1][0] == (5 + 6) / 2                          # neck = midpoint of COCO shoulders 5 and 6
    assert (body[2][0], body[5][0]) == (6.0, 5.0)             # R then L shoulder
    assert (body[3][0], body[4][0]) == (8.0, 10.0)            # R elbow, R wrist
    assert (body[8][0], body[11][0]) == (12.0, 11.0)          # R hip, L hip
    assert (body[10][0], body[13][0]) == (16.0, 15.0)         # R ankle, L ankle
    assert (body[14][0], body[15][0], body[16][0], body[17][0]) == (2.0, 1.0, 4.0, 3.0)  # R/L eye, R/L ear
    assert lh[0][0] == 91.0 and rh[0][0] == 112.0 and face[0][0] == 23.0
    assert wholebody_to_internal(kpts[:50]) == ([], None, None, None)


def test_fill_short_gaps_interpolates_only_short_runs():
    from engine.motion_bank.dwpose_extractor import fill_short_gaps

    def fp(i, x):
        return FramePoseData(frame_index=i, timestamp_sec=i / 24, body=[(x, 0.5, 0.8)] if x is not None else [])

    seq = [fp(0, 0.0), fp(1, None), fp(2, None), fp(3, 0.3)] + [fp(i, None) for i in range(4, 20)] + [fp(20, 1.0)]
    out = fill_short_gaps(seq, max_gap=8)
    assert out[1].body[0][0] == pytest.approx(0.1) and out[2].body[0][0] == pytest.approx(0.2)
    assert all(not f.body for f in out[4:20])  # a 16-frame dropout is not invented


def test_missing_models_raise_unless_fallback_requested(tmp_path: Path):
    extractor = DWPoseExtractor(det_model_path=tmp_path / "a.onnx", pose_model_path=tmp_path / "b.onnx")
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    with pytest.raises(FileNotFoundError):
        extractor.extract_frame_pose(frame, 0, 0.0)
    assert extractor.extract_frame_pose(frame, 0, 0.0, mock_if_missing=True).body  # explicit fallback still works


def test_models_on_disk_are_used_even_when_fallback_requested(tmp_path: Path):
    """The old bug: with the models present, mock_if_missing=True still returned the fake skeleton."""
    (tmp_path / "a.onnx").write_bytes(b"x")
    (tmp_path / "b.onnx").write_bytes(b"x")
    extractor = DWPoseExtractor(det_model_path=tmp_path / "a.onnx", pose_model_path=tmp_path / "b.onnx")
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    with pytest.raises(Exception):  # the stub files are not valid ONNX, so loading the session must fail
        extractor.extract_frame_pose(frame, 0, 0.0, mock_if_missing=True)


def test_guide_dataset_skips_synthetic_motions(tmp_path: Path):
    from engine.motion_bank.guide.dataset import MotionBankDataset

    storage = MotionBankStorage(tmp_path)
    for i, synth in enumerate([True, False]):
        storage.save_motion(MotionRecord(
            id=f"m{i}", source_uri="x", action_title="t", duration_sec=1, fps=24, frame_count=1, resolution=(10, 10),
            keypoints_path=str(tmp_path / f"{i}.safetensors"), control_video_path=str(tmp_path / f"{i}.mp4"),
            metadata={"synthetic": synth},
        ))
    assert len(MotionBankDataset(storage)) == 1
    assert len(MotionBankDataset(storage, include_synthetic=True)) == 2


def test_actor_tracking_never_jumps_to_another_person():
    pick = DWPoseExtractor._pick_actor
    a, b = (100.0, 100.0, 300.0, 500.0), (500.0, 120.0, 650.0, 460.0)
    assert pick([a, b], None, 1000, 1000) == a                                   # no lock yet: the largest person
    assert pick([a, b], (0.11, 0.11, 0.31, 0.51), 1000, 1000) == a               # locked on a: stays on a
    assert pick([b], (0.1, 0.1, 0.3, 0.5), 1000, 1000) is None                   # a is gone, only b left: lost, not b
    assert pick([a, b], (0.5, 0.12, 0.65, 0.46), 1000, 1000) == b                # locked on b even though a is bigger
