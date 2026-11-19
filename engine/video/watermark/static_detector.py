"""Automated static watermark and logo detector using temporal variance analysis.

Detects static broadcast bugs, station watermarks, promotional stamps, and overlays
by tracking pixel standard deviation over time:
- Moving background content has high temporal variance.
- Static watermarks have near-zero temporal variance.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np

from engine.video.watermark.models import DetectionCandidate, WatermarkBoundingBox


def detect_static_watermarks(
    video_path: str | Path,
    num_samples: int = 150,
    max_candidates: int = 5,
    min_area_px: int = 200,
    max_area_ratio: float = 0.12,
    temporal_variance_threshold: float = 8.0,
) -> List[DetectionCandidate]:
    """
    Scans a video for stationary watermarks or logos using temporal variance mapping.
    
    Args:
        video_path: Path to video file.
        num_samples: Number of evenly spaced frames to sample.
        max_candidates: Max candidate boxes to return.
        min_area_px: Minimum contour area in pixels.
        max_area_ratio: Maximum area as fraction of total frame area.
        temporal_variance_threshold: Standard deviation cutoff for static pixels.
        
    Returns:
        List of DetectionCandidate objects sorted by confidence.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)

        if total_frames <= 1 or width <= 0 or height <= 0:
            return []

        # Sample frames evenly across video
        sample_step = max(1, total_frames // num_samples)
        gray_frames: list[np.ndarray] = []
        frame_indices: list[int] = []

        idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if idx % sample_step == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray_frames.append(gray)
                frame_indices.append(idx)
                if len(gray_frames) >= num_samples:
                    break
            idx += 1

        if len(gray_frames) < 3:
            return []

        # Stack into 3D array: (N, H, W)
        stack = np.array(gray_frames, dtype=np.float32)

        # Temporal standard deviation: low std = stationary
        std_map = np.std(stack, axis=0)  # (H, W)

        # Edge persistence: high gradient in the mean image
        mean_img = np.mean(stack, axis=0).astype(np.uint8)
        edges = cv2.Canny(mean_img, 50, 150).astype(np.float32) / 255.0

        # Static score: persistent edges with low temporal standard deviation
        # Static score is high where edges exist and variance is low
        static_score = edges * np.maximum(0.0, 1.0 - (std_map / max(temporal_variance_threshold, 1.0)))

        # Normalize and threshold to binary mask
        norm_score = cv2.normalize(static_score, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        _, binary_mask = cv2.threshold(norm_score, 40, 255, cv2.THRESH_BINARY)

        # Morphological bridge to connect text / emblem characters
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 7))
        connected = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, kernel)
        connected = cv2.morphologyEx(connected, cv2.MORPH_DILATE, kernel)

        # Find candidate bounding contours
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        frame_area = width * height
        candidates: List[DetectionCandidate] = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area_px or area > (frame_area * max_area_ratio):
                continue

            x, y, w, h = cv2.boundingRect(cnt)

            # Score confidence based on position: corner/border watermarks are common
            is_near_corner_or_edge = (
                x < width * 0.25 or (x + w) > width * 0.75 or
                y < height * 0.25 or (y + h) > height * 0.75
            )
            position_multiplier = 1.2 if is_near_corner_or_edge else 0.8

            # Calculate average temporal variance inside candidate box
            box_std = float(np.mean(std_map[y:y+h, x:x+w]))
            std_confidence = max(0.0, min(1.0, 1.0 - (box_std / (temporal_variance_threshold * 2.0))))
            confidence = min(1.0, std_confidence * position_multiplier)

            if confidence >= 0.35:
                candidates.append(DetectionCandidate(
                    box=WatermarkBoundingBox(x=x, y=y, width=w, height=h),
                    confidence=round(confidence, 3),
                    detection_type="temporal_variance",
                    sample_frame_sec=round(float(frame_indices[len(frame_indices) // 2]) / fps, 2),
                    label="Stationary Logo / Watermark",
                ))

        # Sort descending by confidence
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[:max_candidates]

    finally:
        cap.release()
