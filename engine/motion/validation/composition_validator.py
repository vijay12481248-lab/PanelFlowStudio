"""
Composition and timeline coverage validator for PanelFlow Motion Director.
Audits the complete visual timeline for temporal gaps, overlaps, camera bounds, and provenance.
"""
from typing import List, Dict, Any, Tuple, Optional
from engine.motion.models.timeline import VisualTimeline, Shot
from engine.motion.models.warnings import MotionWarning
from engine.motion.models.enums import WarningType, WarningSeverity
from engine.motion.camera.bounds_validator import CameraBoundsValidator


class CompositionValidator:
    """
    Validates render-readiness, visual continuity, and temporal coverage across the entire timeline.
    """

    def __init__(self):
        self.bounds_validator = CameraBoundsValidator()

    def validate_timeline(
        self,
        timeline: VisualTimeline,
        known_visual_asset_ids: Optional[List[str]] = None,
        max_allowed_gap_sec: float = 0.05,
    ) -> Tuple[bool, List[MotionWarning]]:
        """
        Performs comprehensive pre-render audit of the VisualTimeline.
        Returns (is_valid, warnings).
        """
        warnings: List[MotionWarning] = []
        is_valid = True

        all_shots = timeline.all_shots()
        if not all_shots:
            warnings.append(
                MotionWarning(
                    warning_type=WarningType.TIMELINE_MISSING,
                    severity=WarningSeverity.ERROR,
                    message="Visual timeline contains zero planned shots.",
                )
            )
            return False, warnings

        # 1. Timeline start check
        first_shot = all_shots[0]
        if first_shot.start_time > max_allowed_gap_sec:
            warnings.append(
                MotionWarning(
                    warning_type=WarningType.VISUAL_TIMELINE_GAP,
                    severity=WarningSeverity.ERROR,
                    message=f"Timeline start gap: First shot starts at {first_shot.start_time:.3f}s instead of 0.000s.",
                    shot_id=first_shot.shot_id,
                    timestamp_sec=0.0,
                )
            )
            is_valid = False

        # 2. Sequential timing, bounds, and asset verification
        known_assets = set(known_visual_asset_ids) if known_visual_asset_ids else None

        for idx, shot in enumerate(all_shots):
            # A. Duration validity
            if shot.duration <= 0.0:
                warnings.append(
                    MotionWarning(
                        warning_type=WarningType.INVALID_AUDIO_RANGE,
                        severity=WarningSeverity.ERROR,
                        message=f"Shot '{shot.shot_id}' has non-positive duration: {shot.duration:.4f}s",
                        shot_id=shot.shot_id,
                        timestamp_sec=shot.start_time,
                    )
                )
                is_valid = False

            # B. Asset existence
            if known_assets and shot.source_asset_id not in known_assets:
                warnings.append(
                    MotionWarning(
                        warning_type=WarningType.SOURCE_VISUAL_MISSING,
                        severity=WarningSeverity.ERROR,
                        message=f"Shot '{shot.shot_id}' references unknown source visual '{shot.source_asset_id}'.",
                        shot_id=shot.shot_id,
                        source_asset_id=shot.source_asset_id,
                        timestamp_sec=shot.start_time,
                    )
                )
                is_valid = False

            # C. Camera bounds check
            _, _, modified, reasons = self.bounds_validator.validate_trajectory(
                shot.camera_start,
                shot.camera_end,
                source_aspect=shot.frame_region.aspect_ratio,
                target_aspect=timeline.target_resolution.numeric_aspect,
            )
            if modified:
                warnings.append(
                    MotionWarning(
                        warning_type=WarningType.CAMERA_BOUNDS_INVALID,
                        severity=WarningSeverity.WARNING,
                        message=f"Shot '{shot.shot_id}' camera required clamping: {'; '.join(reasons)}",
                        shot_id=shot.shot_id,
                        timestamp_sec=shot.start_time,
                    )
                )

            # D. Temporal continuity between consecutive shots
            if idx > 0:
                prev_shot = all_shots[idx - 1]
                delta = shot.start_time - prev_shot.end_time

                # Gap check
                if delta > max_allowed_gap_sec:
                    warnings.append(
                        MotionWarning(
                            warning_type=WarningType.VISUAL_TIMELINE_GAP,
                            severity=WarningSeverity.ERROR,
                            message=f"Temporal gap of {delta:.3f}s detected between shot '{prev_shot.shot_id}' and '{shot.shot_id}'.",
                            shot_id=shot.shot_id,
                            timestamp_sec=prev_shot.end_time,
                        )
                    )
                    is_valid = False

                # Overlap check
                elif delta < -max_allowed_gap_sec:
                    warnings.append(
                        MotionWarning(
                            warning_type=WarningType.VISUAL_TIMELINE_OVERLAP,
                            severity=WarningSeverity.ERROR,
                            message=f"Temporal overlap of {-delta:.3f}s detected between shot '{prev_shot.shot_id}' and '{shot.shot_id}'.",
                            shot_id=shot.shot_id,
                            timestamp_sec=shot.start_time,
                        )
                    )
                    is_valid = False

            # E. Caption timing validity
            for cap in shot.caption_cues:
                if cap.start_time < shot.start_time - 0.05 or cap.end_time > shot.end_time + 0.05:
                    warnings.append(
                        MotionWarning(
                            warning_type=WarningType.INVALID_AUDIO_RANGE,
                            severity=WarningSeverity.WARNING,
                            message=f"Caption cue '{cap.cue_id}' exceeds shot boundaries [{shot.start_time:.2f}s - {shot.end_time:.2f}s].",
                            shot_id=shot.shot_id,
                            timestamp_sec=cap.start_time,
                        )
                    )

        # 3. Timeline completion check
        last_shot = all_shots[-1]
        clock_discrepancy = abs(timeline.total_duration_sec - last_shot.end_time)
        if clock_discrepancy > 0.1:
            warnings.append(
                MotionWarning(
                    warning_type=WarningType.VISUAL_TIMELINE_GAP,
                    severity=WarningSeverity.WARNING,
                    message=f"Timeline end discrepancy: last shot ends at {last_shot.end_time:.2f}s, expected {timeline.total_duration_sec:.2f}s.",
                    shot_id=last_shot.shot_id,
                    timestamp_sec=last_shot.end_time,
                )
            )

        return is_valid, warnings
