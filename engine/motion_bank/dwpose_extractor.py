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


def _iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _nms(boxes: List[Tuple[float, float, float, float]], scores: List[float], iou_thr: float = 0.45) -> List[Tuple[float, float, float, float]]:
    """Greedy non-maximum suppression; the detector emits many overlapping boxes for one person."""
    keep: List[Tuple[float, float, float, float]] = []
    for i in sorted(range(len(boxes)), key=lambda k: scores[k], reverse=True):
        if all(_iou(boxes[i], k) < iou_thr for k in keep):
            keep.append(boxes[i])
    return keep


# COCO-WholeBody (what DWPose emits): 0-16 body (COCO-17), 17-22 feet, 23-90 face (68), 91-111 left hand, 112-132 right hand.
# Internal layout (what storage, the visualiser and the guide model use): OpenPose-18 body, then hands and face.
# OpenPose index -> COCO index; None marks the neck, which COCO lacks (midpoint of the shoulders).
_OPENPOSE18_FROM_COCO17 = [0, None, 6, 8, 10, 5, 7, 9, 12, 14, 16, 11, 13, 15, 2, 1, 4, 3]


def wholebody_to_internal(all_kpts: list) -> Tuple[list, Optional[list], Optional[list], Optional[list]]:
    """Reorder 133 COCO-WholeBody keypoints (x, y, conf) into (body18, left_hand21, right_hand21, face68)."""
    if len(all_kpts) < 133:
        return [], None, None, None
    body = []
    for src in _OPENPOSE18_FROM_COCO17:
        if src is None:
            ls, rs = all_kpts[5], all_kpts[6]
            body.append(((ls[0] + rs[0]) / 2.0, (ls[1] + rs[1]) / 2.0, min(ls[2], rs[2])))
        else:
            body.append(all_kpts[src])
    return body, all_kpts[91:112], all_kpts[112:133], all_kpts[23:91]


def _lerp_points(a: Optional[list], b: Optional[list], t: float) -> Optional[list]:
    if not a or not b or len(a) != len(b):
        return None
    return [(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, min(p[2], q[2])) for p, q in zip(a, b)]


def fill_short_gaps(poses: List[FramePoseData], max_gap: int) -> List[FramePoseData]:
    """Interpolate runs of empty frames (detector dropouts) of at most `max_gap` frames between two detected frames."""
    i = 0
    n = len(poses)
    while i < n:
        if poses[i].body:
            i += 1
            continue
        j = i
        while j < n and not poses[j].body:
            j += 1
        if i > 0 and j < n and (j - i) <= max_gap:
            a, b = poses[i - 1], poses[j]
            for k in range(i, j):
                t = (k - i + 1) / (j - i + 1)
                poses[k] = FramePoseData(
                    frame_index=poses[k].frame_index,
                    timestamp_sec=poses[k].timestamp_sec,
                    body=_lerp_points(a.body, b.body, t) or [],
                    left_hand=_lerp_points(a.left_hand, b.left_hand, t),
                    right_hand=_lerp_points(a.right_hand, b.right_hand, t),
                    face=_lerp_points(a.face, b.face, t),
                    bbox=tuple(a.bbox[m] + (b.bbox[m] - a.bbox[m]) * t for m in range(4)) if a.bbox and b.bbox else None,
                )
        i = j
    return poses


def longest_tracked_run(poses: List[FramePoseData]) -> Tuple[int, int]:
    """[start, end) of the longest stretch of consecutive frames in which the actor was found ((0, 0) when never)."""
    best = (0, 0)
    start = None
    for i, p in enumerate(poses + [FramePoseData(frame_index=-1, timestamp_sec=0.0, body=[])]):
        if p.body and start is None:
            start = i
        elif not p.body and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    return best


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

    def providers(self) -> List[str]:
        """Execution providers the pose session really runs on ([] before the sessions are loaded)."""
        return list(self._pose_session.get_providers()) if self._pose_session is not None else []

    def extract_frame_pose(
        self,
        frame_rgb: np.ndarray,
        frame_index: int,
        timestamp_sec: float,
        mock_if_missing: bool = False,
        synthetic: bool = False,
        prev_bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> FramePoseData:
        """
        Extracts whole-body keypoints from a single RGB frame.

        `synthetic=True` returns the deterministic fake skeleton and never touches a model (tests and demos only;
        callers must label what they store). `mock_if_missing=True` falls back to that fake skeleton ONLY when the
        ONNX files are absent; whenever the models are on disk they are used. With neither flag a missing model raises.
        `prev_bbox` (normalised x1,y1,x2,y2 of the previous frame) keeps the same actor when several people are in shot.
        """
        h, w = frame_rgb.shape[:2]

        if synthetic:
            return self._generate_synthetic_pose(frame_index, timestamp_sec)
        if not self.is_ready():
            if mock_if_missing:
                return self._generate_synthetic_pose(frame_index, timestamp_sec)
            self.load_sessions()  # raises FileNotFoundError naming the missing files
        if self._det_session is None:
            self.load_sessions()

        # Real ONNX inference
        det_input = self._preprocess_detector(frame_rgb)
        det_out = self._det_session.run(None, {self._det_session.get_inputs()[0].name: det_input})
        boxes = self._postprocess_boxes(det_out, w, h)

        if len(boxes) == 0:
            # No person detected; return empty pose frame
            return FramePoseData(frame_index=frame_index, timestamp_sec=timestamp_sec, body=[])

        primary_box = self._pick_actor(boxes, prev_bbox, w, h)
        if primary_box is None:  # the tracked actor is not in this frame (other people are, but they are not him)
            return FramePoseData(frame_index=frame_index, timestamp_sec=timestamp_sec, body=[])
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
        synthetic: bool = False,
        max_gap_frames: int = 8,
        reacquire_after: int = 30,
    ) -> List[FramePoseData]:
        """
        Processes a video segment frame-by-frame and returns a list of FramePoseData.
        Follows one actor across frames (IoU with the last box; re-acquired after `reacquire_after` lost frames) and fills detector dropouts of at most
        `max_gap_frames` by linear interpolation; longer gaps stay empty (body == []).
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        poses: List[FramePoseData] = []
        frame_idx = int(round(start_sec * fps))
        if frame_idx > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        prev_bbox: Optional[Tuple[float, float, float, float]] = None
        lost = 0

        try:
            while True:
                ts = frame_idx / fps
                if end_sec is not None and ts > end_sec:
                    break
                ret, frame_bgr = cap.read()
                if not ret:
                    break

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                pose_data = self.extract_frame_pose(
                    frame_rgb, frame_idx, ts,
                    mock_if_missing=mock_if_missing, synthetic=synthetic, prev_bbox=prev_bbox,
                )
                if pose_data.bbox is not None:
                    prev_bbox, lost = pose_data.bbox, 0
                else:
                    lost += 1
                    if lost >= reacquire_after:  # a cut or a long exit: take whoever is the main person now
                        prev_bbox = None
                poses.append(pose_data)
                frame_idx += 1
        finally:
            cap.release()

        return fill_short_gaps(poses, max_gap_frames)

    @staticmethod
    def _pick_actor(
        boxes: List[Tuple[float, float, float, float]],
        prev_bbox: Optional[Tuple[float, float, float, float]],
        w: int,
        h: int,
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        The actor to follow. With a previous box: the box that overlaps it most, or None when nobody does (the
        actor is lost - never jump to a different person mid-take). Without one: the largest person.
        """
        if prev_bbox is not None:
            prev_px = (prev_bbox[0] * w, prev_bbox[1] * h, prev_bbox[2] * w, prev_bbox[3] * h)
            best = max(boxes, key=lambda b: _iou(b, prev_px))
            return best if _iou(best, prev_px) > 0.1 else None
        return max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))

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
        box_scores = []
        for idx in np.where(valid_mask)[0]:
            cx, cy = xy[idx]
            bw, bh = wh[idx]
            x1 = max(0.0, float((cx - bw / 2) / r))
            y1 = max(0.0, float((cy - bh / 2) / r))
            x2 = min(float(orig_w), float((cx + bw / 2) / r))
            y2 = min(float(orig_h), float((cy + bh / 2) / r))
            if (x2 - x1) > 20 and (y2 - y1) > 40:
                boxes.append((x1, y1, x2, y2))
                box_scores.append(float(scores[idx]))
        return _nms(boxes, box_scores)

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

        # DWPose emits COCO-WholeBody order; convert to the internal OpenPose-18 + hands + face layout.
        return wholebody_to_internal(all_kpts)
