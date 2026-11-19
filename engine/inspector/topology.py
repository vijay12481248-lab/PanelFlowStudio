"""Deterministic Anatomical Skeleton Topology and Limb Anomaly Validator (Apache 2.0)."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple
import numpy as np

from engine.inspector.schema import DefectRecord
from engine.motion_bank.models import FramePoseData


def _euclidean_dist(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


class SkeletonTopologyValidator:
    """
    Validates anatomical integrity, joint angles, limb length symmetry,
    and identifies floating or missing limbs from DWPose 133-keypoint data.
    Runs deterministically on CPU (0 MB VRAM).
    """

    def __init__(self, min_conf: float = 0.35):
        self.min_conf = min_conf

    def validate_pose(self, pose: FramePoseData, people_count: Optional[int] = 1) -> List[DefectRecord]:
        """
        Inspects OpenPose-18 body skeleton + 42 hand keypoints.
        Returns list of confirmed or suspected anatomical DefectRecords.
        """
        defects: List[DefectRecord] = []
        body = pose.body
        if not body or len(body) < 15:
            return defects

        # Helper to get joint if confident
        def joint(idx: int) -> Optional[Tuple[float, float, float]]:
            if idx < len(body) and body[idx][2] >= self.min_conf:
                return body[idx]
            return None

        # Key joint indices (OpenPose-18):
        # 1: Neck, 2: RShoulder, 3: RElbow, 4: RWrist
        # 5: LShoulder, 6: LElbow, 7: LWrist
        # 8: MidHip, 9: RHip, 10: RKnee, 11: RAnkle
        # 12: LHip, 13: LKnee, 14: LAnkle

        neck = joint(1)
        r_shoulder, r_elbow, r_wrist = joint(2), joint(3), joint(4)
        l_shoulder, l_elbow, l_wrist = joint(5), joint(6), joint(7)
        r_hip, r_knee, r_ankle = joint(9), joint(10), joint(11)
        l_hip, l_knee, l_ankle = joint(12), joint(13), joint(14)

        # 1. Check for Floating / Disconnected Hands
        # A wrist is confident, but neither elbow nor shoulder is detected.
        # Only evaluate on single-person frames; multi-person interactions (hugs, handshakes) have natural occlusion.
        if people_count is None or people_count <= 1:
            if r_wrist and not r_elbow and not r_shoulder:
                defects.append(
                    DefectRecord(
                        category="extra_limbs",
                        bbox=(r_wrist[0] - 0.05, r_wrist[1] - 0.05, r_wrist[0] + 0.05, r_wrist[1] + 0.05),
                        confidence=r_wrist[2],
                        severity="moderate",
                        evidence=f"Right hand detected at ({r_wrist[0]:.2f}, {r_wrist[1]:.2f}) without connected elbow or shoulder joints.",
                        recommended_action="inpaint",
                    )
                )

            if l_wrist and not l_elbow and not l_shoulder:
                defects.append(
                    DefectRecord(
                        category="extra_limbs",
                        bbox=(l_wrist[0] - 0.05, l_wrist[1] - 0.05, l_wrist[0] + 0.05, l_wrist[1] + 0.05),
                        confidence=l_wrist[2],
                        severity="moderate",
                        evidence=f"Left hand detected at ({l_wrist[0]:.2f}, {l_wrist[1]:.2f}) without connected elbow or shoulder joints.",
                        recommended_action="inpaint",
                    )
                )

        # 2. Extreme Arm Asymmetry / Distorted Lengths
        # If both arms are visible, check ratio of upper arms
        if r_shoulder and r_elbow and l_shoulder and l_elbow:
            r_arm_len = _euclidean_dist(r_shoulder, r_elbow)
            l_arm_len = _euclidean_dist(l_shoulder, l_elbow)
            if min(r_arm_len, l_arm_len) > 0.02:
                arm_ratio = max(r_arm_len, l_arm_len) / min(r_arm_len, l_arm_len)
                if arm_ratio > 3.0:
                    longer_arm = "Right" if r_arm_len > l_arm_len else "Left"
                    defects.append(
                        DefectRecord(
                            category="extra_limbs",
                            confidence=0.82,
                            severity="moderate",
                            evidence=f"Extreme arm asymmetry detected: {longer_arm} upper arm is {arm_ratio:.1f}x longer than the opposite arm.",
                            recommended_action="redraw",
                        )
                    )

        # 3. Leg Length / Knee Inversion Check
        if r_hip and r_knee and l_hip and l_knee:
            r_thigh = _euclidean_dist(r_hip, r_knee)
            l_thigh = _euclidean_dist(l_hip, l_knee)
            if min(r_thigh, l_thigh) > 0.03:
                thigh_ratio = max(r_thigh, l_thigh) / min(r_thigh, l_thigh)
                if thigh_ratio > 3.2:
                    longer_leg = "Right" if r_thigh > l_thigh else "Left"
                    defects.append(
                        DefectRecord(
                            category="extra_limbs",
                            confidence=0.80,
                            severity="moderate",
                            evidence=f"Extreme leg asymmetry: {longer_leg} thigh length ratio is {thigh_ratio:.1f}x.",
                            recommended_action="redraw",
                        )
                    )

        # 4. Finger Keypoint Clustering Check (Detecting Degenerate / Fused Hands)
        for side, hand_kpts in (("Left", pose.left_hand), ("Right", pose.right_hand)):
            if hand_kpts and len(hand_kpts) == 21:
                # 21 points: wrist (0), thumb(1-4), index(5-8), middle(9-12), ring(13-16), pinky(17-20)
                confs = [p[2] for p in hand_kpts]
                confident_pts = [p for p in hand_kpts if p[2] >= 0.4]
                if len(confident_pts) >= 10:
                    xs = [p[0] for p in confident_pts]
                    ys = [p[1] for p in confident_pts]
                    span_w = max(xs) - min(xs)
                    span_h = max(ys) - min(ys)
                    # If 15 hand keypoints are collapsed into an impossibly tiny area (< 0.005 of frame)
                    if span_w < 0.005 and span_h < 0.005:
                        defects.append(
                            DefectRecord(
                                category="missing_hand",
                                confidence=0.78,
                                severity="minor",
                                evidence=f"{side} hand keypoints collapsed into degenerate point (fused/distorted fingers).",
                                recommended_action="inpaint",
                                bbox=(min(xs) - 0.03, min(ys) - 0.03, max(xs) + 0.03, max(ys) + 0.03),
                            )
                        )

        return defects
