"""
Adobe After Effects Temporal Motion Blur Engine.
Implements After Effects composition motion blur:
- Shutter Angle: 180° cinematic standard (half frame exposure)
- Shutter Phase: -90° (centered exposure window)
- Sub-frame temporal supersampling and exposure accumulation
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional
from PIL import Image
import numpy as np


@dataclass
class AEMotionBlur:
    """
    After Effects Temporal Motion Blur configuration.
    """
    shutter_angle: float = 180.0       # Shutter angle in degrees [0.0, 360.0]
    shutter_phase: float = -90.0       # Shutter phase in degrees [-180.0, 180.0]
    samples_per_frame: int = 8         # Temporal sub-samples [2, 16]

    def render_blurred_frame(
        self,
        render_fn: Callable[[float], Image.Image],
        t_sec: float,
        fps: float = 60.0,
    ) -> Image.Image:
        """
        Renders a motion-blurred frame by accumulating sub-frame temporal evaluations
        across the shutter exposure interval.
        """
        # If motion blur is disabled or minimal, render directly
        if self.shutter_angle < 1.0 or self.samples_per_frame <= 1 or fps <= 0.0:
            return render_fn(t_sec)

        frame_duration = 1.0 / max(1.0, fps)
        exposure_duration = (self.shutter_angle / 360.0) * frame_duration
        phase_offset = (self.shutter_phase / 360.0) * frame_duration

        t_start = max(0.0, t_sec + phase_offset)
        num_samples = max(2, min(16, self.samples_per_frame))

        # Accumulate float32 buffer
        accum_buffer: Optional[np.ndarray] = None

        for s_idx in range(num_samples):
            # Uniform temporal sample points
            sample_t = t_start + (s_idx / (num_samples - 1)) * exposure_duration
            sample_img = render_fn(sample_t)

            arr = np.array(sample_img.convert("RGBA"), dtype=np.float32)

            if accum_buffer is None:
                accum_buffer = np.zeros_like(arr)

            accum_buffer += arr

        if accum_buffer is None:
            return render_fn(t_sec)

        # Average samples and clamp to uint8
        avg_arr = np.clip(accum_buffer / float(num_samples), 0, 255).astype(np.uint8)
        return Image.fromarray(avg_arr, mode="RGBA")
