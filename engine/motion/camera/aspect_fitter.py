"""
Aspect ratio fitting and canvas resolution utilities.
"""
from typing import Tuple
from engine.motion.models.camera import CameraState, NormalizedRect, TargetResolution


class AspectFitter:
    """
    Utilities for fitting heterogeneous comic panel formats into cinematic output canvases.
    """

    @staticmethod
    def parse_aspect_ratio(aspect_str: str) -> float:
        try:
            if ":" in aspect_str:
                w_str, h_str = aspect_str.split(":", 1)
                return float(w_str.strip()) / max(float(h_str.strip()), 1e-4)
            return float(aspect_str)
        except Exception:
            return 16.0 / 9.0

    @classmethod
    def default_safe_framing(
        cls,
        source_width: int,
        source_height: int,
        target_res: TargetResolution,
    ) -> CameraState:
        """
        Returns a balanced default camera state centered on the source visual.
        Calculates safe initial zoom so that letterboxing/pillarboxing does not create border gaps.
        """
        src_aspect = source_width / max(source_height, 1)
        tgt_aspect = target_res.numeric_aspect

        # Minimum zoom factor that fully covers target aspect without border gaps
        if src_aspect >= tgt_aspect:
            # Source is wider than target: zoom of 1.0 covers height completely
            min_zoom = 1.0
        else:
            # Source is taller than target: zoom of 1.0 covers width completely
            min_zoom = 1.0

        return CameraState(
            center_x=0.5,
            center_y=0.5,
            zoom=min_zoom,
            rotation=0.0,
            crop=NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0),
        )
