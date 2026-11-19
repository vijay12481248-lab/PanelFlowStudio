"""Temporal Video Quality Inspector: Scene Gating, Keypoint Velocity Jitter & Face Drift Analysis."""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

from engine.inspector.face_engine import OpenFaceEngine
from engine.inspector.schema import (
    DecisionStatus,
    FaceDetectionResult,
    InspectorConfig,
    TemporalDefectRecord,
    VideoQualityDecision,
)
from engine.motion_bank.dwpose_extractor import DWPoseExtractor
from engine.motion_bank.models import FramePoseData


def _euclidean_2d(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _bbox_iou(box_a: Tuple[float, float, float, float], box_b: Tuple[float, float, float, float]) -> float:
    """Calculates Intersection-over-Union (IoU) of two normalized bounding boxes (x1, y1, x2, y2)."""
    xa = max(box_a[0], box_b[0])
    ya = max(box_a[1], box_b[1])
    xb = min(box_a[2], box_b[2])
    yb = min(box_a[3], box_b[3])
    inter_area = max(0.0, xb - xa) * max(0.0, yb - ya)
    box_a_area = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    box_b_area = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    union_area = box_a_area + box_b_area - inter_area
    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


@dataclass
class _SampledFrameData:
    frame_index: int
    timestamp_sec: float
    shot_index: int
    pose: Optional[FramePoseData] = None
    faces: List[FaceDetectionResult] = field(default_factory=list)


class TemporalVideoInspector:
    """
    Independent Temporal Video Quality Inspector executing 100% on CPU (0 MB VRAM).
    Features:
    1. Single-Pass Streaming Video Decoder: Reads video linearly without expensive seeking.
    2. Dedicated OpenCV Scene Cut Gating: Segments shots by HSV histogram correlation without forced cuts.
    3. Root-Compensated Keypoint Jitter: Subtracts camera root motion (neck/hip) to isolate unnatural joint teleportation.
    4. Dual-Direction Flickering Limb Analysis: Detects both limb dropouts (1->0->1) and phantom pop-ins (0->1->0).
    5. Dropped Actor Glitch Detection: Flags sudden character disappearances in frame center.
    6. Multi-Person Spatial Face Tracking: Clusters faces across frames before SFace cosine drift evaluation.
    """

    def __init__(
        self,
        config: Optional[InspectorConfig] = None,
        dwpose: Optional[DWPoseExtractor] = None,
        face_engine: Optional[OpenFaceEngine] = None,
    ):
        self.config = config or InspectorConfig()
        self.dwpose = dwpose or DWPoseExtractor()
        self.face_engine = face_engine or OpenFaceEngine()

    def detect_scene_cuts_opencv(
        self,
        video_path: Path | str,
        sample_step: int = 4,
        similarity_thresh: float = 0.60,
    ) -> List[Tuple[float, float]]:
        """
        Detects continuous camera shots using HSV 2D histogram correlation.
        Returns list of (start_sec, end_sec) intervals. Guaranteed no forced artificial chops.
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else 0.0

        prev_hist: Optional[np.ndarray] = None
        cut_times: List[float] = [0.0]
        curr_frame = 0

        while curr_frame < total_frames:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            if curr_frame % sample_step == 0:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
                cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

                if prev_hist is not None:
                    sim = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                    if sim < similarity_thresh:
                        ts = round(curr_frame / fps, 2)
                        # Ensure minimal shot duration of 0.25s to avoid duplicate boundary flags
                        if ts - cut_times[-1] >= 0.25:
                            cut_times.append(ts)
                prev_hist = hist

            curr_frame += 1

        cap.release()

        # Build shot intervals
        shots: List[Tuple[float, float]] = []
        for i in range(len(cut_times)):
            start = cut_times[i]
            end = cut_times[i + 1] if i + 1 < len(cut_times) else round(duration_sec, 2)
            if end > start:
                shots.append((start, end))

        if not shots:
            shots = [(0.0, round(duration_sec, 2))]
        return shots

    def inspect_video(
        self,
        video_path: Path | str,
        sample_step: int = 2,
    ) -> VideoQualityDecision:
        """
        Executes end-to-end temporal inspection across an MP4 video file in a single linear pass.
        """
        t0 = time.monotonic()
        vpath = Path(video_path)
        if not vpath.is_file():
            raise FileNotFoundError(f"Video file not found at: {vpath}")

        cap = cv2.VideoCapture(str(vpath))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {vpath}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else 0.0

        # 1. Single-Pass Streaming Video Extraction & Live Scene Gating
        sampled_data: List[_SampledFrameData] = []
        prev_hist: Optional[np.ndarray] = None
        current_shot_idx = 0
        shot_boundaries: List[float] = [0.0]
        curr_frame = 0

        while True:
            ret, frame_bgr = cap.read()
            if not ret or frame_bgr is None:
                break

            ts = curr_frame / fps

            # Frame sampling condition
            if curr_frame % sample_step == 0:
                # Scene cut check
                hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
                cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

                if prev_hist is not None:
                    sim = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                    if sim < 0.60 and (ts - shot_boundaries[-1]) >= 0.25:
                        current_shot_idx += 1
                        shot_boundaries.append(round(ts, 2))
                prev_hist = hist

                # DWPose Extraction (CPU)
                pose_data: Optional[FramePoseData] = None
                if self.config.enable_cv_topology and self.dwpose.is_ready():
                    try:
                        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                        pose_data = self.dwpose.extract_frame_pose(frame_rgb, curr_frame, ts)
                    except Exception:
                        pass

                # Face Detection & SFace Embedding (CPU)
                faces: List[FaceDetectionResult] = []
                if self.config.enable_face_check and self.face_engine.is_ready():
                    try:
                        faces = self.face_engine.detect_and_embed(frame_bgr)
                    except Exception:
                        pass

                sampled_data.append(
                    _SampledFrameData(
                        frame_index=curr_frame,
                        timestamp_sec=ts,
                        shot_index=current_shot_idx,
                        pose=pose_data,
                        faces=faces,
                    )
                )

            curr_frame += 1

        cap.release()

        # Build shot list
        shots_detected = current_shot_idx + 1

        # 2. Per-Shot Temporal Analysis
        all_defects: List[TemporalDefectRecord] = []
        for shot_id in range(shots_detected):
            shot_frames = [f for f in sampled_data if f.shot_index == shot_id]
            if len(shot_frames) < 2:
                continue

            start_sec = shot_frames[0].timestamp_sec
            end_sec = shot_frames[-1].timestamp_sec

            # Poses for this shot
            shot_poses = [
                (f.frame_index, f.timestamp_sec, f.pose)
                for f in shot_frames
                if f.pose is not None
            ]

            # Faces for this shot
            shot_faces = [
                (f.frame_index, f.timestamp_sec, f.faces)
                for f in shot_frames
            ]

            # A. Root-Compensated Keypoint Jitter
            all_defects.extend(self.analyze_keypoint_jitter(shot_poses, shot_id, start_sec, end_sec))

            # B. Dual-Direction Flickering Limbs
            all_defects.extend(self.analyze_flickering_limbs(shot_poses, shot_id, start_sec, end_sec))

            # C. Dropped Actor Glitch
            all_defects.extend(self.analyze_dropped_actors(shot_poses, shot_id, start_sec, end_sec))

            # D. Multi-Person Spatial Face Identity Drift
            all_defects.extend(self.analyze_identity_drift(shot_faces, shot_id, start_sec, end_sec))

        # 3. Calculate Overall Temporal Quality Score
        score = 100.0
        penalties = {
            "fatal": 40.0,
            "severe": 30.0,
            "moderate": 18.0,
            "minor": 8.0,
        }
        for d in all_defects:
            p = penalties.get(d.severity, 15.0) * d.confidence
            score -= p

        overall_score = max(0.0, min(100.0, round(score, 1)))
        has_severe = any(d.severity in ("fatal", "severe") for d in all_defects)

        if overall_score >= self.config.pass_threshold and not has_severe:
            status: DecisionStatus = "PASS"
        elif overall_score >= self.config.retry_threshold:
            status = "RETRY"
        else:
            status = "MANUAL_REVIEW"

        clean = len(all_defects) == 0 and status == "PASS"
        if clean:
            summary = f"PASS ({overall_score:.0f}/100): Video temporally stable, 0 motion artifacts across {shots_detected} shot(s)."
        else:
            cats = list({d.category for d in all_defects})
            summary = (
                f"{status} ({overall_score:.0f}/100): Found {len(all_defects)} temporal defect(s) "
                f"[{', '.join(cats)}] across {shots_detected} shot(s)."
            )

        return VideoQualityDecision(
            overall_score=overall_score,
            status=status,
            clean=clean,
            defects=all_defects,
            duration_sec=round(duration_sec, 2),
            total_frames=total_frames,
            fps=round(fps, 2),
            shots_detected=shots_detected,
            summary=summary,
            seconds=round(time.monotonic() - t0, 2),
        )

    def analyze_keypoint_jitter(
        self,
        poses: List[Tuple[int, float, FramePoseData]],
        shot_idx: int,
        start_sec: float,
        end_sec: float,
    ) -> List[TemporalDefectRecord]:
        """
        Detects unnatural physical joint acceleration spikes.
        Applies root-motion compensation (neck/hip) so camera pans and tracking do not trigger false alarms.
        """
        defects: List[TemporalDefectRecord] = []
        if len(poses) < 2:
            return defects

        max_thresh = self.config.jitter_velocity_threshold

        for i in range(len(poses) - 1):
            f_a, ts_a, pose_a = poses[i]
            f_b, ts_b, pose_b = poses[i + 1]

            if not pose_a.body or not pose_b.body:
                continue

            # Calculate camera / root movement displacement
            root_dx, root_dy = 0.0, 0.0
            # OpenPose joint 1 is Neck
            if len(pose_a.body) > 1 and len(pose_b.body) > 1:
                na = pose_a.body[1]
                nb = pose_b.body[1]
                if na[2] >= 0.35 and nb[2] >= 0.35:
                    root_dx = nb[0] - na[0]
                    root_dy = nb[1] - na[1]
            elif len(pose_a.body) > 11 and len(pose_b.body) > 11:
                # Fall back to mid-hip (joints 8 and 11)
                ha8, ha11 = pose_a.body[8], pose_a.body[11]
                hb8, hb11 = pose_b.body[8], pose_b.body[11]
                if ha8[2] >= 0.35 and hb8[2] >= 0.35:
                    root_dx = hb8[0] - ha8[0]
                    root_dy = hb8[1] - ha8[1]

            # Primary limb extremities to inspect
            # 4: RWrist, 7: LWrist, 10: RAnkle, 13: LAnkle
            joints_to_check = [
                (4, "Right Wrist"),
                (7, "Left Wrist"),
                (10, "Right Ankle"),
                (13, "Left Ankle"),
            ]

            for j_idx, joint_name in joints_to_check:
                if j_idx < len(pose_a.body) and j_idx < len(pose_b.body):
                    ja = pose_a.body[j_idx]
                    jb = pose_b.body[j_idx]
                    if ja[2] >= 0.40 and jb[2] >= 0.40:
                        raw_dx = jb[0] - ja[0]
                        raw_dy = jb[1] - ja[1]
                        # Relative motion after subtracting root displacement
                        rel_dx = raw_dx - root_dx
                        rel_dy = raw_dy - root_dy
                        rel_disp = math.hypot(rel_dx, rel_dy)

                        if rel_disp > max_thresh:
                            defects.append(
                                TemporalDefectRecord(
                                    category="temporal_jitter",
                                    start_sec=ts_a,
                                    end_sec=ts_b,
                                    frame_indices=[f_a, f_b],
                                    confidence=0.88,
                                    severity="moderate",
                                    evidence=(
                                        f"Shot {shot_idx}: {joint_name} teleported relative to body by "
                                        f"{rel_disp:.2f} norm size between frame {f_a} and {f_b}."
                                    ),
                                    recommended_action="redraw",
                                    details={
                                        "relative_displacement": rel_disp,
                                        "joint": joint_name,
                                        "shot": shot_idx,
                                    },
                                )
                            )
        return defects

    def analyze_flickering_limbs(
        self,
        poses: List[Tuple[int, float, FramePoseData]],
        shot_idx: int,
        start_sec: float,
        end_sec: float,
    ) -> List[TemporalDefectRecord]:
        """
        Detects both limb dropouts (1->0->1) and phantom limb pop-ins (0->1->0) across a 3-frame sliding window.
        """
        defects: List[TemporalDefectRecord] = []
        if len(poses) < 3:
            return defects

        limbs = [
            (4, "Right Hand"),
            (7, "Left Hand"),
            (10, "Right Foot"),
            (13, "Left Foot"),
        ]

        for i in range(len(poses) - 2):
            f_a, ts_a, p_a = poses[i]
            f_b, ts_b, p_b = poses[i + 1]
            f_c, ts_c, p_c = poses[i + 2]

            for j_idx, jname in limbs:
                if p_a.body and p_b.body and p_c.body:
                    ca = p_a.body[j_idx][2] if j_idx < len(p_a.body) else 0.0
                    cb = p_b.body[j_idx][2] if j_idx < len(p_b.body) else 0.0
                    cc = p_c.body[j_idx][2] if j_idx < len(p_c.body) else 0.0

                    # Pattern 1: Limb Dropout (visible -> vanishes -> visible)
                    if ca >= 0.40 and cb < 0.15 and cc >= 0.40:
                        defects.append(
                            TemporalDefectRecord(
                                category="flickering_limbs",
                                start_sec=ts_a,
                                end_sec=ts_c,
                                frame_indices=[f_a, f_b, f_c],
                                confidence=0.85,
                                severity="minor",
                                evidence=f"Shot {shot_idx}: {jname} dropped out at frame {f_b} and reappeared at frame {f_c}.",
                                recommended_action="inpaint",
                                details={"joint": jname, "flicker_type": "dropout", "frame": f_b},
                            )
                        )

                    # Pattern 2: Phantom Pop-In (missing -> sudden pop-in -> missing)
                    elif ca < 0.15 and cb >= 0.40 and cc < 0.15:
                        defects.append(
                            TemporalDefectRecord(
                                category="flickering_limbs",
                                start_sec=ts_a,
                                end_sec=ts_c,
                                frame_indices=[f_a, f_b, f_c],
                                confidence=0.85,
                                severity="minor",
                                evidence=f"Shot {shot_idx}: Phantom {jname} popped in at frame {f_b} and vanished at frame {f_c}.",
                                recommended_action="inpaint",
                                details={"joint": jname, "flicker_type": "phantom_popin", "frame": f_b},
                            )
                        )
        return defects

    def analyze_dropped_actors(
        self,
        poses: List[Tuple[int, float, FramePoseData]],
        shot_idx: int,
        start_sec: float,
        end_sec: float,
    ) -> List[TemporalDefectRecord]:
        """
        Detects sudden mid-shot disappearance of an actor whose body has not exited screen boundaries.
        """
        defects: List[TemporalDefectRecord] = []
        if len(poses) < 3:
            return defects

        for i in range(len(poses) - 2):
            f_a, ts_a, p_a = poses[i]
            f_b, ts_b, p_b = poses[i + 1]
            f_c, ts_c, p_c = poses[i + 2]

            joints_a = sum(1 for j in p_a.body if j[2] >= 0.35) if p_a.body else 0
            joints_b = sum(1 for j in p_b.body if j[2] >= 0.35) if p_b.body else 0
            joints_c = sum(1 for j in p_c.body if j[2] >= 0.35) if p_c.body else 0

            # Actor present in a and c (> 8 joints) but missing in b (<= 2 joints)
            if joints_a >= 8 and joints_b <= 2 and joints_c >= 8:
                # Check if actor in frame a was near image edge
                is_boundary = False
                if p_a.bbox:
                    bx1, by1, bx2, by2 = p_a.bbox
                    if bx1 <= 0.05 or by1 <= 0.05 or bx2 >= 0.95 or by2 >= 0.95:
                        is_boundary = True

                if not is_boundary:
                    defects.append(
                        TemporalDefectRecord(
                            category="dropped_actor",
                            start_sec=ts_a,
                            end_sec=ts_c,
                            frame_indices=[f_a, f_b, f_c],
                            confidence=0.92,
                            severity="severe",
                            evidence=(
                                f"Shot {shot_idx}: Character suddenly vanished at frame {f_b} "
                                f"({joints_b} joints vs {joints_a} in prior frame) without boundary exit."
                            ),
                            recommended_action="redraw",
                            details={"shot": shot_idx, "dropped_frame": f_b},
                        )
                    )
        return defects

    def analyze_identity_drift(
        self,
        frame_faces: List[Tuple[int, float, List[FaceDetectionResult]]],
        shot_idx: int,
        start_sec: float,
        end_sec: float,
    ) -> List[TemporalDefectRecord]:
        """
        Tracks character faces across frames using spatial IoU / centroid proximity before evaluating
        SFace cosine drift (< 0.55), preventing false alarms when multiple characters share the shot.
        """
        defects: List[TemporalDefectRecord] = []
        if len(frame_faces) < 2:
            return defects

        # Structure face tracks: track_id -> List[(frame, ts, bbox, embedding)]
        tracks: Dict[int, List[Tuple[int, float, Tuple[float, float, float, float], List[float]]]] = {}
        next_track_id = 0

        for f_idx, ts, faces in frame_faces:
            for face in faces:
                if not face.embedding:
                    continue

                matched_track_id: Optional[int] = None
                best_iou = 0.0

                for t_id, t_items in tracks.items():
                    last_item = t_items[-1]
                    iou = _bbox_iou(face.bbox, last_item[2])
                    if iou > 0.20 and iou > best_iou:
                        best_iou = iou
                        matched_track_id = t_id

                if matched_track_id is None:
                    # Spatial proximity fallback (center distance < 0.25)
                    fc_x = (face.bbox[0] + face.bbox[2]) / 2.0
                    fc_y = (face.bbox[1] + face.bbox[3]) / 2.0
                    min_dist = 0.25

                    for t_id, t_items in tracks.items():
                        last_bbox = t_items[-1][2]
                        tc_x = (last_bbox[0] + last_bbox[2]) / 2.0
                        tc_y = (last_bbox[1] + last_bbox[3]) / 2.0
                        d = math.hypot(fc_x - tc_x, fc_y - tc_y)
                        if d < min_dist:
                            min_dist = d
                            matched_track_id = t_id

                if matched_track_id is not None:
                    tracks[matched_track_id].append((f_idx, ts, face.bbox, face.embedding))
                else:
                    tracks[next_track_id] = [(f_idx, ts, face.bbox, face.embedding)]
                    next_track_id += 1

        # Evaluate identity drift per track against anchor embedding
        drift_thresh = 0.55
        for t_id, observations in tracks.items():
            if len(observations) < 2:
                continue

            anchor_frame, anchor_ts, _, anchor_emb = observations[0]

            for f_idx, ts, _, emb in observations[1:]:
                sim = self.face_engine.compute_similarity(anchor_emb, emb)
                if sim < drift_thresh:
                    defects.append(
                        TemporalDefectRecord(
                            category="identity_drift",
                            start_sec=anchor_ts,
                            end_sec=ts,
                            frame_indices=[anchor_frame, f_idx],
                            confidence=round(1.0 - sim, 2),
                            severity="severe",
                            evidence=(
                                f"Shot {shot_idx} (Track {t_id}): Character face drifted significantly "
                                f"(similarity {sim:.2f} < {drift_thresh:.2f} at frame {f_idx} vs anchor frame {anchor_frame})."
                            ),
                            recommended_action="redraw",
                            details={
                                "track_id": t_id,
                                "similarity": sim,
                                "anchor_frame": anchor_frame,
                                "drift_frame": f_idx,
                            },
                        )
                    )
                    break  # One drift flag per track per shot
        return defects
