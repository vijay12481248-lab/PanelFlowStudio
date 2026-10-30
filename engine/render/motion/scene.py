"""Motion scene container and compositor for procedural motion graphics."""

from __future__ import annotations

import math
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFilter

from engine.render.motion.elements import (
    MotionElement,
    KineticTextElement,
    CardElement,
    ConnectorTrackElement,
    MetricCounterElement,
    AttentionHeatmapElement,
)


class MotionScene:
    """A self-contained procedural motion graphics scene rendered frame-by-frame."""

    def __init__(
        self,
        scene_id: str,
        duration_sec: float = 10.0,
        bg_color: Tuple[int, int, int] = (10, 15, 28),
        ambient_glow_color: Tuple[int, int, int] = (20, 45, 90),
        elements: Optional[List[MotionElement]] = None,
    ) -> None:
        self.scene_id = scene_id
        self.duration_sec = float(duration_sec)
        self.bg_color = bg_color
        self.ambient_glow_color = ambient_glow_color
        self.elements: List[MotionElement] = elements or []

    def add_element(self, element: MotionElement) -> None:
        self.elements.append(element)

    def render_frame(self, t: float, size: Tuple[int, int] = (1280, 720)) -> Image.Image:
        """Renders the motion graphics scene at time t (in seconds)."""
        w, h = size

        # 1. Base Canvas & Ambient Radial Spotlight
        canvas = Image.new("RGBA", (w, h), (*self.bg_color, 255))
        draw = ImageDraw.Draw(canvas)

        # Dynamic breathing ambient light
        pulse = 0.5 + 0.5 * math.sin(t * 2.0)
        glow_alpha = int(70 + 25 * pulse)
        
        glow_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(glow_surf)
        g_draw.ellipse([w // 2 - 350, -120, w // 2 + 350, 480], fill=(*self.ambient_glow_color, glow_alpha))
        glow_surf = glow_surf.filter(ImageFilter.GaussianBlur(75))
        canvas = Image.alpha_composite(canvas, glow_surf)
        draw = ImageDraw.Draw(canvas)

        # 2. Render all active motion elements
        for el in self.elements:
            el.render(canvas, draw, t, w, h)

        return canvas.convert("RGB")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize scene to dictionary for timeline plan compilation."""
        return {
            "scene_id": self.scene_id,
            "duration_sec": self.duration_sec,
            "bg_color": list(self.bg_color),
            "ambient_glow_color": list(self.ambient_glow_color),
            "elements_count": len(self.elements),
        }
