"""
Adobe After Effects Layer Model, Parenting & Track Mattes.
Implements:
- Hierarchical parenting transforms (translation, rotation, scale from anchor point)
- 3D / 2D Null Object controllers
- Track Mattes: Alpha Matte, Alpha Inverted, Luma Matte, Luma Inverted
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image
import numpy as np


@dataclass
class AELayer:
    """
    After Effects Layer Transform & Compositing Node.
    """
    name: str = "Layer"
    anchor_point: Tuple[float, float] = (0.0, 0.0)    # Local origin pivot (px)
    position: Tuple[float, float] = (0.0, 0.0)        # (x, y) in canvas or parent space
    scale: Tuple[float, float] = (1.0, 1.0)           # (sx, sy)
    rotation: float = 0.0                             # degrees
    opacity: float = 1.0                              # [0.0, 1.0]
    parent: Optional[AELayer] = None                  # Parent controller node
    track_matte_mode: str = "none"                    # none, alpha, alpha_inverted, luma, luma_inverted

    def compute_world_transform(self) -> Tuple[float, float, float, float, float]:
        """
        Computes the world transformation matrix taking the parent hierarchy into account.
        Returns: (world_x, world_y, world_rot_deg, world_sx, world_sy)
        """
        lx, ly = self.position
        ax, ay = self.anchor_point
        # Offset position by anchor point
        rel_x = lx - ax
        rel_y = ly - ay

        if self.parent is None:
            return (rel_x, rel_y, self.rotation, self.scale[0], self.scale[1])

        # Recursively evaluate parent world transform
        px, py, prot, psx, psy = self.parent.compute_world_transform()

        rad = math.radians(prot)
        cos_t = math.cos(rad)
        sin_t = math.sin(rad)

        scaled_x = rel_x * psx
        scaled_y = rel_y * psy

        rot_x = scaled_x * cos_t - scaled_y * sin_t
        rot_y = scaled_x * sin_t + scaled_y * cos_t

        world_x = px + rot_x
        world_y = py + rot_y
        world_rot = prot + self.rotation
        world_sx = psx * self.scale[0]
        world_sy = psy * self.scale[1]

        return (world_x, world_y, world_rot, world_sx, world_sy)

    @staticmethod
    def apply_track_matte(
        layer_img: Image.Image,
        matte_img: Image.Image,
        mode: str = "alpha",
    ) -> Image.Image:
        """
        Applies After Effects Track Matte compositing:
        - 'alpha': Mask by matte alpha channel
        - 'alpha_inverted': Mask where matte alpha channel is zero
        - 'luma': Mask by matte luminance Y = 0.299R + 0.587G + 0.114B
        - 'luma_inverted': Inverted luminance mask
        """
        if mode == "none":
            return layer_img

        layer_rgba = np.array(layer_img.convert("RGBA"), dtype=np.float32)
        matte_rgba = np.array(matte_img.convert("RGBA").resize(layer_img.size), dtype=np.float32)

        if mode == "alpha":
            matte_mask = matte_rgba[:, :, 3] / 255.0
        elif mode == "alpha_inverted":
            matte_mask = 1.0 - (matte_rgba[:, :, 3] / 255.0)
        elif mode == "luma":
            # Rec. 601 luma formula
            luma = (
                0.299 * matte_rgba[:, :, 0] +
                0.587 * matte_rgba[:, :, 1] +
                0.114 * matte_rgba[:, :, 2]
            ) / 255.0
            matte_mask = luma * (matte_rgba[:, :, 3] / 255.0)
        elif mode == "luma_inverted":
            luma = (
                0.299 * matte_rgba[:, :, 0] +
                0.587 * matte_rgba[:, :, 1] +
                0.114 * matte_rgba[:, :, 2]
            ) / 255.0
            matte_mask = 1.0 - (luma * (matte_rgba[:, :, 3] / 255.0))
        else:
            return layer_img

        # Modulate layer alpha
        layer_rgba[:, :, 3] *= np.clip(matte_mask, 0.0, 1.0)
        result_arr = np.clip(layer_rgba, 0, 255).astype(np.uint8)

        return Image.fromarray(result_arr, mode="RGBA")
