"""
100% Procedural, Image-Free Background Motion Generators.
Zero external assets required.
"""

import math
import random
import numpy as np
from typing import Tuple, List, Optional
from PIL import Image, ImageDraw, ImageFilter


class FluidCausticsGenerator:
    """
    Renders undulating volumetric lighting orbs creating an organic ambient gradient field.
    """

    def __init__(
        self,
        bounds: Tuple[int, int] = (1280, 720),
        base_color: Tuple[int, int, int] = (4, 7, 16),
        blur_sigma: int = 110,
    ):
        self.w, self.h = bounds
        self.base_color = base_color
        self.blur_sigma = blur_sigma

    def render(
        self,
        t: float,
        orbs: Optional[List[Tuple[Tuple[int, int, int], float, float, int]]] = None,
    ) -> Image.Image:
        """
        Renders fluid caustics at timestamp t.
        orbs: List of ((R, G, B), speed_x, speed_y, radius)
        """
        bg = Image.new("RGBA", (self.w, self.h), (*self.base_color, 255))
        light_surf = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(light_surf)

        default_orbs = orbs or [
            ((124, 58, 237), 0.6, 0.4, 380),  # Violet
            ((6, 182, 212), 0.5, 0.7, 340),   # Cyan
            ((16, 185, 129), 0.8, 0.6, 300),  # Emerald
        ]

        for i, (col, sx, sy, rad) in enumerate(default_orbs):
            cx = int(self.w * 0.5 + (self.w * 0.22) * math.sin(t * sx + i * 1.4))
            cy = int(self.h * 0.5 + (self.h * 0.18) * math.cos(t * sy + i * 0.9))
            alpha = int(50 + 20 * math.sin(t * 1.2 + i))
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(*col, alpha))

        light_surf = light_surf.filter(ImageFilter.GaussianBlur(self.blur_sigma))
        return Image.alpha_composite(bg, light_surf)


class WaveRibbonMeshGenerator:
    """
    Generates 3D undulating silk wave ribbons with multi-frequency harmonic superposition.
    """

    def __init__(
        self,
        bounds: Tuple[int, int] = (1280, 720),
        num_ribbons: int = 8,
        color_start: Tuple[int, int, int] = (6, 182, 212),
        color_end: Tuple[int, int, int] = (168, 85, 247),
    ):
        self.w, self.h = bounds
        self.num_ribbons = num_ribbons
        self.color_start = color_start
        self.color_end = color_end

    def render_onto(self, canvas: Image.Image, t: float) -> Image.Image:
        """Renders undulating silk ribbons directly onto canvas."""
        ribbon_surf = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ribbon_surf)

        for r_i in range(self.num_ribbons):
            phase = r_i * 0.42
            pts = []
            for px in range(0, self.w + 25, 25):
                nx = px / self.w
                w1 = math.sin(nx * 3.5 + t * 1.2 + phase) * 85
                w2 = math.cos(nx * 6.2 - t * 0.8 + phase * 1.5) * 45
                w3 = math.sin(nx * 1.8 + t * 0.5) * 60
                py = int(self.h * 0.52 + w1 + w2 + w3 + (r_i - self.num_ribbons // 2) * 22)
                pts.append((px, py))

            f = r_i / max(1, self.num_ribbons - 1)
            col = tuple(
                int(self.color_start[c] + f * (self.color_end[c] - self.color_start[c]))
                for c in range(3)
            )
            alpha = int(45 + 30 * math.sin(t * 1.5 + r_i))

            for p_idx in range(len(pts) - 1):
                draw.line([pts[p_idx], pts[p_idx + 1]], fill=(*col, alpha), width=2)

        glow = ribbon_surf.filter(ImageFilter.GaussianBlur(14))
        out = Image.alpha_composite(canvas, glow)
        return Image.alpha_composite(out, ribbon_surf)


class CyberGrid3DGenerator:
    """
    Renders a 3D perspective floor grid receding toward a horizon vanishing point.
    """

    def __init__(
        self,
        bounds: Tuple[int, int] = (1280, 720),
        grid_color: Tuple[int, int, int] = (0, 220, 255),
        horizon_y: int = 380,
    ):
        self.w, self.h = bounds
        self.grid_color = grid_color
        self.horizon_y = horizon_y

    def render_onto(self, canvas: Image.Image, t: float) -> Image.Image:
        """Renders 3D perspective floor grid onto canvas."""
        grid_surf = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(grid_surf)

        # Perspective vanishing lines
        center_x = self.w // 2
        for angle_deg in range(-70, 75, 10):
            rad = math.radians(angle_deg)
            x_end = center_x + int(math.tan(rad) * (self.h - self.horizon_y) * 1.8)
            alpha = int(40 + 20 * math.cos(rad))
            draw.line([(center_x, self.horizon_y), (x_end, self.h)], fill=(*self.grid_color, alpha), width=1)

        # Receding horizontal lines (exponential spacing)
        speed_offset = (t * 45.0) % 30.0
        for i in range(16):
            p = (i * 25.0 + speed_offset) / 400.0
            if 0.0 <= p <= 1.0:
                y = int(self.horizon_y + math.pow(p, 1.8) * (self.h - self.horizon_y))
                alpha = int(15 + 85 * p)
                draw.line([(0, y), (self.w, y)], fill=(*self.grid_color, alpha), width=1)

        return Image.alpha_composite(canvas, grid_surf)


class ParticleStarfield3DGenerator:
    """
    Renders a depth-projected 3D starfield with motion parallax, depth scaling, and velocity trails.
    """

    def __init__(
        self,
        bounds: Tuple[int, int] = (1280, 720),
        num_stars: int = 180,
        speed: float = 140.0,
        fov: float = 420.0,
        max_depth: float = 1000.0,
        star_color: Tuple[int, int, int] = (220, 240, 255),
        seed: int = 42,
    ):
        self.w, self.h = bounds
        self.num_stars = num_stars
        self.speed = speed
        self.fov = fov
        self.max_depth = max_depth
        self.star_color = star_color
        
        # Initialize deterministic 3D star positions
        rng = random.Random(seed)
        self.stars = [
            (
                rng.uniform(-self.w * 0.8, self.w * 0.8),
                rng.uniform(-self.h * 0.8, self.h * 0.8),
                rng.uniform(10.0, self.max_depth),
            )
            for _ in range(num_stars)
        ]

    def render_onto(self, canvas: Image.Image, t: float) -> Image.Image:
        """Renders 3D starfield particles onto canvas."""
        star_surf = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(star_surf)
        cx, cy = self.w // 2, self.h // 2

        for sx, sy, init_z in self.stars:
            z = (init_z - t * self.speed) % self.max_depth + 1.0
            prev_z = min(self.max_depth, z + (self.speed * 0.035))

            # Screen coordinates
            px = int(cx + (sx / z) * self.fov)
            py = int(cy + (sy / z) * self.fov)

            # Previous coordinates for subtle motion streak
            old_px = int(cx + (sx / prev_z) * self.fov)
            old_py = int(cy + (sy / prev_z) * self.fov)

            if 0 <= px < self.w and 0 <= py < self.h:
                depth_factor = max(0.0, min(1.0, 1.0 - (z / self.max_depth)))
                alpha = int(max(20, min(255, 255 * (depth_factor ** 1.3))))
                radius = max(1, int(3.5 * depth_factor))

                # Streak line
                if (px != old_px or py != old_py) and depth_factor > 0.3:
                    trail_alpha = int(alpha * 0.5)
                    draw.line([(old_px, old_py), (px, py)], fill=(*self.star_color, trail_alpha), width=max(1, radius - 1))

                # Star point
                draw.ellipse(
                    [px - radius, py - radius, px + radius, py + radius],
                    fill=(*self.star_color, alpha)
                )

        return Image.alpha_composite(canvas, star_surf)
