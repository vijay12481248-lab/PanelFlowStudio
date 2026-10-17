"""
Visual repetition detector for PanelFlow Motion Director.
Flags excessive identical framing across consecutive shots to preserve visual interest.
"""
from typing import List
from engine.motion.models.timeline import Shot
from engine.motion.models.warnings import MotionWarning
from engine.motion.models.enums import WarningType, WarningSeverity


class RepetitionDetector:
    """
    Detects when identical source panels, crops, or camera motions repeat consecutively.
    """

    def detect_repetition(self, shots: List[Shot], max_consecutive_identical: int = 3) -> List[MotionWarning]:
        warnings: List[MotionWarning] = []
        if len(shots) < max_consecutive_identical:
            return warnings

        streak = 1
        for i in range(1, len(shots)):
            prev = shots[i - 1]
            curr = shots[i]

            same_asset = (prev.source_asset_id == curr.source_asset_id)
            same_motion = (prev.motion_type == curr.motion_type)
            same_zoom = abs(prev.camera_start.zoom - curr.camera_start.zoom) < 0.03
            same_center = (
                abs(prev.camera_start.center_x - curr.camera_start.center_x) < 0.03
                and abs(prev.camera_start.center_y - curr.camera_start.center_y) < 0.03
            )

            if same_asset and same_motion and same_zoom and same_center:
                streak += 1
                if streak >= max_consecutive_identical:
                    warnings.append(
                        MotionWarning(
                            warning_type=WarningType.VISUAL_REPETITION_WARNING,
                            severity=WarningSeverity.WARNING,
                            message=(
                                f"Visual repetition detected: Shot '{curr.shot_id}' repeats "
                                f"identical source '{curr.source_asset_id}' and camera framing for {streak} consecutive shots."
                            ),
                            shot_id=curr.shot_id,
                            scene_id=curr.scene_id,
                            source_asset_id=curr.source_asset_id,
                            timestamp_sec=curr.start_time,
                            context={"consecutive_count": streak},
                        )
                    )
            else:
                streak = 1

        return warnings
