"""DWPose Extractor: Standalone ONNX whole-body pose estimation (Body 18 + Hands 42 + Face 68)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np

from engine.motion_bank.models import FramePoseData
from engine.motion_bank.models_manifest import DEFAULT_MODELS_DIR


def _generate_yolox_grids_and_strides(
    strides: Tuple[int, ...] = (8, 16, 32),
    input_size: Tuple[int, int] = (640, 640),
) -> Tuple[np.ndarray, np.ndarray]:
    """Pre-generates anchor grids and stride arrays for YOLOX decoding."""
    grid_list = []
    stride_list = []
    for s in strides:
        h, w = input_size[0] // s, input_size[1] // s
        xv, yv = np.meshgrid(np.arange(w), np.arange(h))
        grid = np.stack([xv, yv], axis=-1).reshape(-1, 2)
        grid_list.append(grid)
        stride_list.append(np.full((len(grid), 1), s))
    return np.concatenate(grid_list, axis=0), np.concatenate(stride_list, axis=0)


class DWPoseExtractor:
    """
    Standalone Whole-Body Pose Extractor utilizing ONNX Runtime.
    Processes video frames to extract normalized 133-keypoint coordinates.
    """

    def __init__(
        self,
        det_model_path: Optional[Path] = None,
        pose_model_path: Optional[Path] = None,
        device: str = "cuda",
    ):
        self.models_dir = DEFAULT_MODELS_DIR
        self.det_model_path = det_model_path or (self.models_dir / "yolox_l.onnx")
        self.pose_model_path = pose_model_path or (self.models_dir / "dw-ll_ucoco_384.onnx")
        self.device = device
        self._det_session = None
        self._pose_session = None
        self._grids, self._strides = _generate_yolox_grids_and_strides()

    def is_ready(self) -> bool:
        """Checks if the required ONNX models exist on disk."""
        return self.det_model_path.is_file() and self.pose_model_path.is_file()

    def load_sessions(self) -> None:
        """Initializes ONNX Runtime sessions if models exist."""
        if not self.is_ready():
            raise FileNotFoundError(
                f"DWPose ONNX models not found on disk. Expected:\n"
                f"Detector: {self.det_model_path}\n"
                f"Pose Estimator: {self.pose_model_path}\n"
                f"Please request model approval and download via models_manifest.py."
            )

        import onnxruntime as ort

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if self.device == "cuda" else ["CPUExecutionProvider"]
        available = ort.get_available_providers()
        active_providers = [p for p in providers if p in available]

        self._det_session = ort.InferenceSession(str(self.det_model_path), providers=active_providers)
        self._pose_session = ort.InferenceSession(str(self.pose_model_path), providers=active_providers)

    def extract_frame_pose(
        self,
        frame_rgb: np.ndarray,
        frame_index: int,
        timestamp_sec: float,
        mock_if_missing: bool = False,
    ) -> FramePoseData:
        """
        Extracts whole-body keypoints from a single RGB frame.
        If models are not yet downloaded and mock_if_missing is True, returns synthetic kinematic data for testing.
        """
        h, w = frame_rgb.shape[:2]

        if not self.is_ready() or self._det_session is None:
            if mock_if_missing:
                return self._generate_synthetic_pose(frame_index, timestamp_sec)
            self.load_sessions()

        # Real ONNX inference
        det_input = self._preprocess_detector(frame_rgb)
        det_out = self._det_session.run(None, {self._det_session.get_inputs()[0].name: det_input})
        boxes = self._postprocess_boxes(det_out, w, h)

        if len(boxes) == 0:
            # No person detected; return empty pose frame
            return FramePoseData(frame_index=frame_index, timestamp_sec=timestamp_sec, body=[])

        # Pick primary foreground actor (highest confidence * area)
        primary_box = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        x1, y1, x2, y2 = primary_box

        # Crop and estimate pose
        pose_input = self._preprocess_pose(frame_rgb, primary_box)
        pose_out = self._pose_session.run(None, {self._pose_session.get_inputs()[0].name: pose_input})
        body, left_hand, right_hand, face = self._decode_keypoints(pose_out, primary_box, w, h)

        return FramePoseData(
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            body=body,
            left_hand=left_hand,
            right_hand=right_hand,
            face=face,
            bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
        )

    def extract_video_stream(
        self,
        video_path: Path,
        start_sec: float = 0.0,
        end_sec: Optional[float] = None,
        mock_if_missing: bool = False,
    ) -> List[FramePoseData]:
        """Processes a video file frame-by-frame and returns a list of FramePoseData."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        poses: List[FramePoseData] = []
        frame_idx = 0

        try:
            while True:
                ret, frame_bgr = cap.read()
                if not ret:
                    break
                ts = frame_idx / fps
                if ts < start_sec:
                    frame_idx += 1
                    continue
                if end_sec is not None and ts > end_sec:
                    break

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                pose_data = self.extract_frame_pose(frame_rgb, frame_idx, ts, mock_if_missing=mock_if_missing)
                poses.append(pose_data)
                frame_idx += 1
        finally:
            cap.release()

        return poses

    def _generate_synthetic_pose(self, frame_index: int, timestamp_sec: float) -> FramePoseData:
        """Generates deterministic mock kinematic keypoints for offline unit testing."""
        t = timestamp_sec * 4.0
        leg_swing = 0.08 * np.sin(t)
        arm_swing = 0.08 * np.cos(t)

        body: List[Tuple[float, float, float]] = [
            (0.50, 0.20, 0.95),  # 0 Nose
            (0.50, 0.26, 0.95),  # 1 Neck
            (0.42, 0.26, 0.90),  # 2 RShoulder
            (0.40, 0.38 + arm_swing, 0.85),  # 3 RElbow
            (0.38, 0.50 + arm_swing * 1.5, 0.85),  # 4 RWrist
            (0.58, 0.26, 0.90),  # 5 LShoulder
            (0.60, 0.38 - arm_swing, 0.85),  # 6 LElbow
            (0.62, 0.50 - arm_swing * 1.5, 0.85),  # 7 LWrist
            (0.45, 0.52, 0.90),  # 8 RHip
            (0.44, 0.68 + leg_swing, 0.88),  # 9 RKnee
            (0.43, 0.84 + leg_swing * 1.2, 0.85),  # 10 RAnkle
            (0.55, 0.52, 0.90),  # 11 LHip
            (0.56, 0.68 - leg_swing, 0.88),  # 12 LKnee
            (0.57, 0.84 - leg_swing * 1.2, 0.85),  # 13 LAnkle
            (0.48, 0.18, 0.95),  # 14 REye
            (0.52, 0.18, 0.95),  # 15 LEye
            (0.44, 0.19, 0.90),  # 16 REar
            (0.56, 0.19, 0.90),  # 17 LEar
        ]

        left_hand = [(0.62 + 0.01 * i, 0.50 + 0.005 * i, 0.8) for i in range(21)]
        right_hand = [(0.38 - 0.01 * i, 0.50 + 0.005 * i, 0.8) for i in range(21)]
        face = [(0.50 + 0.05 * np.cos(i * 0.1), 0.20 + 0.05 * np.sin(i * 0.1), 0.9) for i in range(68)]

        return FramePoseData(
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            body=body,
            left_hand=left_hand,
            right_hand=right_hand,
            face=face,
            bbox=(0.35, 0.15, 0.65, 0.90),
        )

    def _preprocess_detector(self, img: np.ndarray) -> np.ndarray:
        """Letterboxes frame to 640x640 for YOLOX detector."""
        h, w = img.shape[:2]
        r = min(640 / h, 640 / w)
        nh, nw = int(h * r), int(w * r)
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        padded = np.full((640, 640, 3), 114, dtype=np.uint8)
        padded[:nh, :nw] = resized
        blob = padded.transpose(2, 0, 1).astype(np.float32)[None, ...]
        return blob

    def _postprocess_boxes(self, det_out: list, orig_w: int, orig_h: int) -> List[Tuple[float, float, float, float]]:
        """Parses YOLOX detector outputs into image-space bounding boxes."""
        preds = det_out[0]
        if preds.ndim == 3:
            preds = preds[0]

        r = min(640 / orig_h, 640 / orig_w)

        # Decode raw YOLOX anchors if output matches grid count
        if preds.shape[0] == len(self._grids):
            xy = (preds[:, :2] + self._grids) * self._strides
            wh = np.exp(preds[:, 2:4]) * self._strides
            scores = preds[:, 4] * preds[:, 5]  # obj_conf * person_conf (class 0)
        else:
            xy = preds[:, :2]
            wh = preds[:, 2:4]
            scores = preds[:, 4] * preds[:, 5] if preds.shape[1] > 5 else preds[:, 4]

        valid_mask = scores > 0.35
        boxes = []
        for idx in np.where(valid_mask)[0]:
            cx, cy = xy[idx]
            bw, bh = wh[idx]
            x1 = max(0.0, float((cx - bw / 2) / r))
            y1 = max(0.0, float((cy - bh / 2) / r))
            x2 = min(float(orig_w), float((cx + bw / 2) / r))
            y2 = min(float(orig_h), float((cy + bh / 2) / r))
            if (x2 - x1) > 20 and (y2 - y1) > 40:
                boxes.append((x1, y1, x2, y2))
        return boxes

    def _preprocess_pose(self, img: np.ndarray, bbox: Tuple[float, float, float, float]) -> np.ndarray:
        """Crops and letterboxes person bounding box to 384x288 for DWPose model."""
        x1, y1, x2, y2 = [int(v) for v in bbox]
        crop = img[max(0, y1):max(1, y2), max(0, x1):max(1, x2)]
        if crop.size == 0:
            crop = np.zeros((384, 288, 3), dtype=np.uint8)
        resized = cv2.resize(crop, (288, 384), interpolation=cv2.INTER_LINEAR)
        # Normalization
        mean = np.array([123.675, 116.28, 103.53], dtype=np.float32)
        std = np.array([58.395, 57.12, 57.375], dtype=np.float32)
        norm = (resized.astype(np.float32) - mean) / std
        return norm.transpose(2, 0, 1)[None, ...]

    def _decode_keypoints(
        self,
        pose_out: list,
        bbox: Tuple[float, float, float, float],
        orig_w: int,
        orig_h: int,
    ) -> Tuple[list, list, list, list]:
        """Decodes SimCC heatmaps from DWPose into normalized coordinates."""
        x1, y1, x2, y2 = bbox
        bw = max(1.0, x2 - x1)
        bh = max(1.0, y2 - y1)

        simcc_x, simcc_y = pose_out[0][0], pose_out[1][0]
        kpts_x = np.argmax(simcc_x, axis=-1) / 2.0  # SimCC uses 2x resolution
        kpts_y = np.argmax(simcc_y, axis=-1) / 2.0
        confs_x = np.max(simcc_x, axis=-1)
        confs_y = np.max(simcc_y, axis=-1)
        confs = np.maximum(0.0, (confs_x + confs_y) / 2.0)

        all_kpts = []
        for i in range(len(kpts_x)):
            gx = (x1 + (kpts_x[i] / 288.0) * bw) / orig_w
            gy = (y1 + (kpts_y[i] / 384.0) * bh) / orig_h
            conf = float(confs[i])
            all_kpts.append((float(np.clip(gx, 0.0, 1.0)), float(np.clip(gy, 0.0, 1.0)), conf))

        # Wholebody 133 partitioning: 0-17 Body, 18-38 Left Hand, 39-59 Right Hand, 60-127 Face
        body = all_kpts[:18] if len(all_kpts) >= 18 else []
        left_hand = all_kpts[18:39] if len(all_kpts) >= 39 else None
        right_hand = all_kpts[39:60] if len(all_kpts) >= 60 else None
        face = all_kpts[60:128] if len(all_kpts) >= 128 else None

        return body, left_hand, right_hand, face
