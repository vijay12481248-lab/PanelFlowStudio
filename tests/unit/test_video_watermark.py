"""Unit tests for non-blur video watermark detection and removal pipeline."""
from __future__ import annotations

import tempfile
from pathlib import Path
import cv2
import numpy as np
import pytest

from engine.video.watermark.flow_inpainter import FlowInpainter
from engine.video.watermark.inverse_alpha import (
    estimate_alpha_and_watermark_from_frames,
    restore_inverse_alpha_patch,
)
from engine.video.watermark.models import (
    WatermarkBoundingBox,
    WatermarkMode,
    WatermarkRemovalParams,
)
from engine.video.watermark.pipeline import (
    preview_watermark_removal,
    remove_video_watermark,
)
from engine.video.watermark.static_detector import detect_static_watermarks


def test_bounding_box_clamping_and_expansion():
    box = WatermarkBoundingBox(x=100, y=100, width=50, height=30)
    assert box.x2 == 150
    assert box.y2 == 130

    clamped = WatermarkBoundingBox(x=-10, y=-5, width=500, height=500).clamp(100, 100)
    assert clamped.x == 0
    assert clamped.y == 0
    assert clamped.width == 100
    assert clamped.height == 100

    expanded = box.expand(margin=10, max_width=200, max_height=200)
    assert expanded.x == 90
    assert expanded.y == 90
    assert expanded.width == 70
    assert expanded.height == 50


def test_inverse_alpha_exact_recovery():
    """
    Mathematically verifies that inverse alpha blending recovers the exact original
    background pixels with zero blur for semi-transparent watermarks.
    """
    np.random.seed(42)
    # 1. Ground truth sharp background texture (gradients, edges)
    h, w = 64, 64
    x = np.linspace(0, 255, w)
    y = np.linspace(0, 255, h)
    xx, yy = np.meshgrid(x, y)
    bg_clean = np.stack([xx, yy, 255 - xx], axis=-1).astype(np.uint8)

    # 2. Add high frequency noise/texture to prove no blur occurs
    bg_clean = np.clip(bg_clean.astype(np.int16) + np.random.randint(-15, 15, (h, w, 3)), 0, 255).astype(np.uint8)

    # 3. Apply semi-transparent white watermark with alpha = 0.35
    alpha = 0.35
    alpha_mask = np.full((h, w, 1), alpha, dtype=np.float32)
    watermark_color = (255, 255, 255)

    watermarked_frame = (
        (1.0 - alpha) * bg_clean.astype(np.float32) + alpha * np.array(watermark_color, dtype=np.float32)
    ).astype(np.uint8)

    # 4. Invert alpha blending to restore background
    restored_bg = restore_inverse_alpha_patch(watermarked_frame, alpha_mask, watermark_color)

    # 5. Measure Mean Absolute Error between ground-truth and restored pixels
    mae = np.mean(np.abs(bg_clean.astype(np.float32) - restored_bg.astype(np.float32)))

    # Error must be less than 1.5 intensity units (due to 8-bit rounding quantization only)
    assert mae < 1.5, f"Expected exact recovery but got MAE: {mae}"


def test_estimate_alpha_and_watermark_from_frames():
    """Verify temporal variance alpha estimation on multiple frames."""
    h, w = 48, 48
    frames = []
    # Background moves across frames (varying intensity)
    for i in range(10):
        frame = np.full((h, w, 3), 50 + i * 15, dtype=np.uint8)
        # Apply static watermark with alpha = 0.5
        frame[10:38, 10:38] = (frame[10:38, 10:38] * 0.5 + 255 * 0.5).astype(np.uint8)
        frames.append(frame)

    alpha_mask, w_color = estimate_alpha_and_watermark_from_frames(frames, context_border_px=6)
    # The estimated alpha inside the watermark should be roughly 0.4 - 0.6
    inner_alpha = float(np.mean(alpha_mask[15:30, 15:30]))
    assert 0.35 <= inner_alpha <= 0.65, f"Estimated alpha {inner_alpha} outside expected range"


def test_flow_inpainter_flat_black_passthrough():
    box = WatermarkBoundingBox(x=10, y=10, width=30, height=30)
    inpainter = FlowInpainter(box)

    black_patch = np.zeros((30, 30, 3), dtype=np.uint8)
    assert inpainter.is_flat_black(black_patch) is True

    bright_patch = np.full((30, 30, 3), 128, dtype=np.uint8)
    assert inpainter.is_flat_black(bright_patch) is False


def test_flow_inpainter_window_and_feathering():
    box = WatermarkBoundingBox(x=20, y=20, width=40, height=40)
    inpainter = FlowInpainter(box, feather_px=3, context_margin_px=10)

    window_box, local_mask = inpainter.compute_window(100, 100)
    assert window_box.x == 10
    assert window_box.y == 10
    assert window_box.width == 60
    assert window_box.height == 60
    assert local_mask.shape == (60, 60)

    full_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    cleaned_patch = np.full((60, 60, 3), 200, dtype=np.uint8)
    composited = inpainter.composite_patch(full_frame, cleaned_patch, window_box)

    # Outside window remains 0
    assert composited[0, 0, 0] == 0
    # Inside window is updated
    assert composited[30, 30, 0] > 180


def test_optical_flow_warps_unmasked_pixels():
    """Verify that optical flow retrieves pixels visible in other frames."""
    box = WatermarkBoundingBox(x=15, y=15, width=20, height=20)
    inpainter = FlowInpainter(box, context_margin_px=10)

    # Textured background with distinct gradient
    x = np.arange(60, dtype=np.float32)
    y = np.arange(60, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)

    target_patch = np.stack([xx * 3.5, yy * 3.5, (xx + yy) * 1.8], axis=-1).astype(np.uint8)
    target_mask = np.zeros((60, 60), dtype=np.uint8)
    target_mask[20:40, 20:40] = 255  # Watermark location

    # Source frame has the background shifted by 6 pixels horizontally
    source_patch = np.stack([(xx + 6) * 3.5, yy * 3.5, (xx + 6 + yy) * 1.8], axis=-1).astype(np.uint8)
    source_mask = np.zeros((60, 60), dtype=np.uint8)
    source_mask[20:40, 20:40] = 255  # Static watermark in source

    reconstructed, rem_mask = inpainter.warp_pixels_via_optical_flow(
        target_patch, source_patch, target_mask, source_mask
    )

    # Pixels where background shifted in from unmasked areas are restored
    assert np.count_nonzero(rem_mask) < np.count_nonzero(target_mask)


def _create_synthetic_test_video(path: Path, num_frames=30, width=160, height=120) -> None:
    """Helper to synthesize a test video with moving background and static watermark."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, 24.0, (width, height))

    for i in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Moving diagonal gradient
        shift = (i * 4) % width
        for x in range(width):
            val = int(((x + shift) % width) / width * 200)
            frame[:, x] = [val, 200 - val, (val * 2) % 255]

        # Draw static watermark in top-right corner
        cv2.rectangle(frame, (110, 10), (150, 35), (255, 255, 255), -1)
        cv2.putText(frame, "LOGO", (112, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        out.write(frame)

    out.release()


def test_detect_static_watermarks_on_synthetic_video():
    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = Path(tmp_dir) / "test_synth.mp4"
        _create_synthetic_test_video(video_path, num_frames=40)

        candidates = detect_static_watermarks(video_path, num_samples=30)
        assert len(candidates) > 0, "Failed to detect static logo"

        best = candidates[0]
        # Should be in top-right area (x > 90, y < 50)
        assert best.box.x > 80
        assert best.box.y < 50
        assert best.confidence >= 0.35


def test_preview_watermark_removal():
    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = Path(tmp_dir) / "test_synth.mp4"
        _create_synthetic_test_video(video_path, num_frames=20)

        params = WatermarkRemovalParams(
            video_path=str(video_path),
            box=WatermarkBoundingBox(x=110, y=10, width=40, height=25),
            mode=WatermarkMode.AUTO,
        )

        preview = preview_watermark_removal(params, time_sec=0.2)
        assert preview.original_frame_base64
        assert preview.preview_frame_base64
        assert preview.mask_frame_base64
        assert preview.box.x == 110


def test_end_to_end_watermark_removal_pipeline():
    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = Path(tmp_dir) / "test_synth.mp4"
        clean_out_path = Path(tmp_dir) / "cleaned.mp4"
        _create_synthetic_test_video(video_path, num_frames=24)

        params = WatermarkRemovalParams(
            video_path=str(video_path),
            output_path=str(clean_out_path),
            box=WatermarkBoundingBox(x=110, y=10, width=40, height=25),
            mode=WatermarkMode.FLOW_GUIDED,
            use_gpu=False,
        )

        progress_calls = []
        def on_progress(pct, msg):
            progress_calls.append((pct, msg))

        result_path = remove_video_watermark(params, progress_callback=on_progress)
        assert result_path.exists()
        assert result_path.stat().st_size > 1000

        # Check that output video opens and has same frame count
        cap = cv2.VideoCapture(str(result_path))
        assert cap.isOpened()
        frames_out = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        assert frames_out == 24
        assert len(progress_calls) > 0


def test_api_video_watermark_endpoints():
    from fastapi.testclient import TestClient
    from engine.api.app import create_app
    from engine.database.session import init_db, SessionLocal
    from engine.database.models import ProjectRecord

    init_db()
    client = TestClient(create_app(allow_insecure=True), base_url="http://localhost")

    # 1. Test models status endpoint
    res = client.get("/api/video/watermark/models-status")
    assert res.status_code == 200
    data = res.json()
    assert "flow_inpainting_ready" in data
    assert data["flow_inpainting_ready"] is True
    assert data["inverse_alpha_ready"] is True

    # 2. Test detect endpoint on synthetic video
    with tempfile.TemporaryDirectory() as tmp_dir:
        with SessionLocal() as db:
            db.add(ProjectRecord(id="test_proj", title="Test", source_type="LOCAL_FOLDER", workspace_path=str(tmp_dir)))
            db.commit()

        video_path = Path(tmp_dir) / "test_synth.mp4"
        _create_synthetic_test_video(video_path, num_frames=30)

        detect_res = client.post("/api/video/watermark/detect", json={
            "video_path": str(video_path),
            "num_samples": 25,
            "max_candidates": 3,
        })
        assert detect_res.status_code == 200
        detect_data = detect_res.json()
        assert len(detect_data["candidates"]) > 0

        # 3. Test preview endpoint
        box = detect_data["candidates"][0]["box"]
        preview_res = client.post("/api/video/watermark/preview", json={
            "video_path": str(video_path),
            "box": box,
            "mode": "auto",
            "time_sec": 0.5,
        })
        assert preview_res.status_code == 200
        preview_data = preview_res.json()
        assert "original_frame_base64" in preview_data
        assert "preview_frame_base64" in preview_data

        # 4. Test remove enqueue endpoint
        remove_res = client.post("/api/video/watermark/remove", json={
            "project_id": "test_proj",
            "video_path": str(video_path),
            "box": box,
            "mode": "flow_guided",
        })
        assert remove_res.status_code == 200
        remove_data = remove_res.json()
        assert "job_id" in remove_data
        assert remove_data["status"] == "ENQUEUED"


def test_stationary_zero_blur_preserves_sharp_color_boundaries():
    """Verify that stationary domain restoration preserves sharp vertical transitions without blurring."""
    h, w = 60, 100
    # Left half is solid Green (0, 255, 0), Right half is solid Red (0, 0, 255)
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :50] = [0, 255, 0]
    frame[:, 50:] = [0, 0, 255]

    # Overlay a translucent watermark box with text spanning across the green/red boundary
    box = WatermarkBoundingBox(x=30, y=15, width=40, height=30)
    # 40% black attenuation inside box:
    frame[15:45, 30:70] = (frame[15:45, 30:70] * 0.6).astype(np.uint8)
    # White text across boundary
    cv2.putText(frame, "LOGO", (35, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    inpainter = FlowInpainter(box, feather_px=1, context_margin_px=10)
    win_box, local_mask = inpainter.compute_window(w, h)
    win_patch = frame[win_box.y : win_box.y2, win_box.x : win_box.x2]

    # Process single static frame
    cleaned_windows = inpainter.inpaint_window_sequence([win_patch], local_mask)
    cleaned_full = inpainter.composite_patch(frame, cleaned_windows[0], win_box)

    # Check that Green side (x=45) is green, Red side (x=55) is red, and no cross-smear occurred
    # Sample at y=30 across the watermark location
    assert cleaned_full[30, 45, 1] > 200, "Green bar corrupted or washed out"
    assert cleaned_full[30, 45, 2] < 30, "Red bled into green bar"
    assert cleaned_full[30, 55, 2] > 200, "Red bar corrupted or washed out"
    assert cleaned_full[30, 55, 1] < 30, "Green bled into red bar"

    # Transition from green to red should be sharp (within 2 pixels of x=50)
    assert cleaned_full[30, 48, 1] > 180, "Boundary blurred to the left"
    assert cleaned_full[30, 52, 2] > 180, "Boundary blurred to the right"


