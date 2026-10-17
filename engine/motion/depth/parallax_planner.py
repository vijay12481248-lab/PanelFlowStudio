"""
2.5D Multi-plane parallax planner for PanelFlow Motion Director.
Generates differential motion across visual layers when segmentation is available,
and provides a clean single flat image fallback when depth segmentation is absent.
"""
from typing import List, Optional, Tuple
from engine.motion.models.layers import ParallaxPlan, LayerInstruction
from engine.motion.models.camera import CameraState
from engine.motion.models.enums import LayerType, WarningType, WarningSeverity
from engine.motion.models.warnings import MotionWarning
from engine.motion.models.input_contract import VisualSource


class ParallaxPlanner:
    """
    Plans differential camera motion vectors for layered visual assets.
    """

    def plan_parallax(
        self,
        visual: VisualSource,
        camera_start: CameraState,
        camera_end: CameraState,
        parallax_strength: float = 0.5,
        existing_layers: Optional[List[LayerInstruction]] = None,
    ) -> Tuple[ParallaxPlan, Optional[MotionWarning]]:
        """
        Builds a ParallaxPlan. If layers exist, computes differential motion.
        If no layers exist, gracefully returns a flat fallback with an informational notice.
        """
        # If no explicit layers were provided for this visual asset
        if not existing_layers:
            fallback = ParallaxPlan.flat_fallback(visual.file_path)
            warning = MotionWarning(
                warning_type=WarningType.PARALLAX_UNAVAILABLE,
                severity=WarningSeverity.INFO,
                message=f"Visual asset '{visual.asset_id}' has no segmented layers. Fallback to flat camera pan/zoom.",
                source_asset_id=visual.asset_id,
            )
            return fallback, warning

        # Calculate base camera displacement vector
        dx = camera_end.center_x - camera_start.center_x
        dy = camera_end.center_y - camera_start.center_y

        planned_layers: List[LayerInstruction] = []
        for lay in existing_layers:
            # Multiplier based on layer type / depth
            if lay.layer_type == LayerType.FOREGROUND:
                factor = 1.0 + (0.4 * parallax_strength)
            elif lay.layer_type == LayerType.BACKGROUND:
                factor = 1.0 - (0.5 * parallax_strength)
            elif lay.layer_type == LayerType.CHARACTER:
                factor = 1.0
            else:
                factor = 1.0

            # Compute relative offsets
            offset_x = round(-dx * (factor - 1.0) * 0.1, 4)
            offset_y = round(-dy * (factor - 1.0) * 0.1, 4)

            updated = LayerInstruction(
                layer_id=lay.layer_id,
                layer_type=lay.layer_type,
                source_uri=lay.source_uri,
                depth=lay.depth,
                motion_factor=round(factor, 3),
                relative_scale=lay.relative_scale,
                relative_offset_x=offset_x,
                relative_offset_y=offset_y,
                opacity=lay.opacity,
                blend_mode=lay.blend_mode,
            )
            planned_layers.append(updated)

        plan = ParallaxPlan(
            enabled=True,
            layers=planned_layers,
            fallback_flat=False,
            max_parallax_offset=0.08 * parallax_strength,
        )
        return plan, None
