"""
PanelFlow Studio - 3D Orbital Kinetic Typography Engine.
Renders text rings that physically curve and orbit around central 3D subjects
with authentic depth sorting, 3D Euler perspective scaling, upright cylinder banking,
and foreground/background depth occlusion.
"""

from __future__ import annotations

import math
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np


def draw_3d_orbiting_text_ring(
    behind_canvas: Image.Image,
    front_canvas: Image.Image,
    text: str,
    cx: float,
    cy: float,
    font: ImageFont.ImageFont,
    t: float,
    rx: float = 430.0,
    rz: float = 210.0,
    pitch_deg: float = 22.0,
    roll_deg: float = -14.0,
    tilt_rad: Optional[float] = None,
    omega: float = 0.22,
    y_offset: float = 0.0,
    base_color: Tuple[int, int, int] = (255, 255, 255),
    accent_color: Tuple[int, int, int] = (255, 215, 0),  # Radiant Solar Gold
    behind_color: Tuple[int, int, int] = (160, 130, 80), # Muted amber gold
    behind_alpha_range: Tuple[int, int] = (75, 140),
    front_alpha_range: Tuple[int, int] = (200, 255),
    scale_range: Tuple[float, float] = (0.65, 1.35),
    enable_tangent_rotation: bool = True,
    bank_amplitude_deg: float = 25.0,
) -> None:
    """
    Renders an elliptical 3D orbital kinetic text ring around a central anchor.
    Characters with Z < 0 are routed to behind_canvas (occluded behind the subject).
    Characters with Z >= 0 are routed to front_canvas (rendered in front of the subject).

    Features:
    - Left-to-right reading direction along the orbit ribbon.
    - Authentic 3D Euler rotation (Pitch & Roll) creating true spatial depth.
    - True per-glyph perspective scaling using bicubic resampling.
    - Upright cylinder banking (characters stand naturally upright and never flip upside-down).
    - Depth-of-field alpha and camera-facing specular sheen.
    """
    total_chars = len(text)
    if total_chars == 0:
        return

    # Handle backward-compatible tilt_rad parameter
    if tilt_rad is not None:
        pitch_deg = 22.0
        roll_deg = math.degrees(tilt_rad)

    pitch_rad = math.radians(pitch_deg)
    roll_rad = math.radians(roll_deg)

    dummy = Image.new("RGBA", (1, 1))
    d_dummy = ImageDraw.Draw(dummy)

    # Sort characters by Z depth to prevent rendering overlap artifacts
    char_render_queue = []

    for i, ch in enumerate(text):
        if ch == " ":
            continue

        # Left-to-right reading order: decreasing theta with increasing index i
        theta = omega * t - (2.0 * math.pi * i / total_chars)

        # 1. 3D coordinates on horizontal circle/ellipse
        x0 = rx * math.cos(theta)
        z0 = rz * math.sin(theta)
        y0 = 0.0

        # 2. Pitch rotation around X axis (opens the ellipse vertically into a true 3D cylinder)
        y1 = -z0 * math.sin(pitch_rad)
        z1 = z0 * math.cos(pitch_rad)
        x1 = x0

        # 3. Roll rotation around Z axis (athletic camera roll)
        x2 = x1 * math.cos(roll_rad) - y1 * math.sin(roll_rad)
        y2 = x1 * math.sin(roll_rad) + y1 * math.cos(roll_rad)
        z2 = z1

        # Screen coordinates
        scr_x = cx + x2
        scr_y = cy + y2 + y_offset

        # 4. Tangent vector along curve in reading direction:
        dx0 = rx * math.sin(theta)
        dz0 = -rz * math.cos(theta)
        dy0 = 0.0

        dy1 = -dz0 * math.sin(pitch_rad)
        dz1 = dz0 * math.cos(pitch_rad)
        dx1 = dx0

        dx2 = dx1 * math.cos(roll_rad) - dy1 * math.sin(roll_rad)
        dy2 = dx1 * math.sin(roll_rad) + dy1 * math.cos(roll_rad)

        raw_angle = math.degrees(math.atan2(dy2, dx2))
        upright_angle = (raw_angle + 90.0) % 180.0 - 90.0
        bank_deg = max(-bank_amplitude_deg, min(bank_amplitude_deg, upright_angle)) if enable_tangent_rotation else 0.0

        # 5. Normalized Z depth (-1.0 = extreme background, +1.0 = extreme foreground)
        z_norm = max(-1.0, min(1.0, z2 / max(1.0, rz)))
        t_depth = (z_norm + 1.0) / 2.0  # 0.0 to 1.0
        scale = scale_range[0] + (scale_range[1] - scale_range[0]) * t_depth

        char_render_queue.append({
            "ch": ch,
            "z2": z2,
            "z_norm": z_norm,
            "t_depth": t_depth,
            "scr_x": scr_x,
            "scr_y": scr_y,
            "bank_deg": bank_deg,
            "scale": scale,
        })

    # Sort queue ascending by Z (deepest background rendered first)
    char_render_queue.sort(key=lambda item: item["z2"])

    for item in char_render_queue:
        ch = item["ch"]
        z2 = item["z2"]
        z_norm = item["z_norm"]
        t_depth = item["t_depth"]
        scr_x = item["scr_x"]
        scr_y = item["scr_y"]
        bank_deg = item["bank_deg"]
        scale = item["scale"]

        bbox = d_dummy.textbbox((0, 0), ch, font=font)
        gw = max(1, bbox[2] - bbox[0])
        gh = max(1, bbox[3] - bbox[1])

        pad = 8
        tile_w = gw + 2 * pad
        tile_h = gh + 2 * pad
        tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
        d_tile = ImageDraw.Draw(tile)

        # Color and Alpha calculations based on depth
        if z2 < 0:
            # Occluded Behind Subject
            target_canvas = behind_canvas
            alpha = int(behind_alpha_range[0] + (behind_alpha_range[1] - behind_alpha_range[0]) * t_depth)
            fill_color = (*behind_color, alpha)
        else:
            # In Front of Subject
            target_canvas = front_canvas
            alpha = int(front_alpha_range[0] + (front_alpha_range[1] - front_alpha_range[0]) * z_norm)
            # Specular gold highlight when directly facing camera
            if z_norm > 0.65:
                fill_color = (*base_color, alpha)
            else:
                fill_color = (*accent_color, alpha)

        d_tile.text((pad - bbox[0], pad - bbox[1]), ch, font=font, fill=fill_color)

        # Sub-pixel scale transform
        scaled_w = max(1, int(round(tile_w * scale)))
        scaled_h = max(1, int(round(tile_h * scale)))
        if scaled_w != tile_w or scaled_h != tile_h:
            tile_scaled = tile.resize((scaled_w, scaled_h), Image.Resampling.BICUBIC)
        else:
            tile_scaled = tile

        # Upright banking rotation transform
        if abs(bank_deg) > 0.1:
            tile_final = tile_scaled.rotate(-bank_deg, resample=Image.Resampling.BICUBIC, expand=True)
        else:
            tile_final = tile_scaled

        # Paste onto target canvas with subpixel center alignment
        px = int(round(scr_x - tile_final.width / 2.0))
        py = int(round(scr_y - tile_final.height / 2.0))
        target_canvas.alpha_composite(tile_final, (px, py))
