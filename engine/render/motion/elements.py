"""Motion graphic visual elements for procedural After Effects-style animations."""

from __future__ import annotations

import math
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from engine.render.motion.curves import clamp, interpolate_value, ease_out_back, ease_out_cubic, ease_out_expo


class MotionElement:
    """Base class for all procedural motion graphic elements."""

    def __init__(
        self,
        element_id: str,
        enter_time: float = 0.0,
        enter_duration: float = 0.6,
        exit_time: Optional[float] = None,
        easing: str = "ease_out_back",
        active_time_range: Optional[Tuple[float, float]] = None,
    ) -> None:
        self.element_id = element_id
        self.enter_time = float(enter_time)
        self.enter_duration = max(0.001, float(enter_duration))
        self.exit_time = float(exit_time) if exit_time is not None else None
        self.easing = easing
        self.active_time_range = active_time_range

    def get_enter_progress(self, t: float) -> float:
        """Returns clamped 0.0 to 1.0 progress through element entrance."""
        if t <= self.enter_time:
            return 0.0
        if t >= self.enter_time + self.enter_duration - 1e-9:
            return 1.0
        return clamp((t - self.enter_time) / self.enter_duration)

    def is_visible(self, t: float) -> bool:
        if t < self.enter_time:
            return False
        if self.exit_time is not None and t > self.exit_time:
            return False
        return True

    def is_active(self, t: float) -> bool:
        """Returns True if the element is currently highlighted by the narration spotlight."""
        if not self.active_time_range:
            return False
        start, end = self.active_time_range
        return start <= t <= end

    def render(self, canvas: Image.Image, draw: ImageDraw.Draw, t: float, w: int, h: int) -> None:
        raise NotImplementedError


class KineticTextElement(MotionElement):
    """Dynamic animated text with slide, fade, scale, and category pill."""

    def __init__(
        self,
        element_id: str,
        text: str,
        x: int,
        y: int,
        enter_time: float = 0.0,
        enter_duration: float = 0.6,
        category_badge: Optional[str] = None,
        font_size: int = 24,
        color: Tuple[int, int, int] = (255, 255, 255),
        badge_color: Tuple[int, int, int] = (0, 240, 255),
        motion_style: str = "slide_down_fade",
        easing: str = "ease_out_back",
    ) -> None:
        super().__init__(element_id, enter_time, enter_duration, easing=easing)
        self.text = text
        self.x = x
        self.y = y
        self.category_badge = category_badge
        self.font_size = font_size
        self.color = color
        self.badge_color = badge_color
        self.motion_style = motion_style

    def render(self, canvas: Image.Image, draw: ImageDraw.Draw, t: float, w: int, h: int) -> None:
        if not self.is_visible(t):
            return

        prog = self.get_enter_progress(t)
        eased = interpolate_value(0.0, 1.0, prog, self.easing)
        opacity = int(255 * ease_out_cubic(prog))

        # Motion displacement
        dy = 0
        if self.motion_style == "slide_down_fade":
            dy = int((1.0 - eased) * -40)
        elif self.motion_style == "slide_up_fade":
            dy = int((1.0 - eased) * 40)

        cur_y = self.y + dy

        # Category Badge
        if self.category_badge:
            badge_text = self.category_badge.upper()
            draw.text((self.x, cur_y - 22), badge_text, fill=(*self.badge_color, int(opacity * 0.9)))

        # Main Text
        draw.text((self.x, cur_y), self.text, fill=(*self.color, opacity))


class CardElement(MotionElement):
    """Staggered glassmorphic container card with elevation, glowing border, and badge."""

    def __init__(
        self,
        element_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str,
        subtitle: str,
        tag: Optional[str] = None,
        tag_color: Tuple[int, int, int] = (0, 240, 255),
        enter_time: float = 0.5,
        enter_duration: float = 0.6,
        active_time_range: Optional[Tuple[float, float]] = None,
        rise_distance: int = 70,
        easing: str = "ease_out_back",
    ) -> None:
        super().__init__(element_id, enter_time, enter_duration, easing=easing, active_time_range=active_time_range)
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title
        self.subtitle = subtitle
        self.tag = tag
        self.tag_color = tag_color
        self.rise_distance = rise_distance

    def render(self, canvas: Image.Image, draw: ImageDraw.Draw, t: float, w: int, h: int) -> None:
        if not self.is_visible(t):
            return

        prog = self.get_enter_progress(t)
        eased = interpolate_value(0.0, 1.0, prog, self.easing)
        opacity = ease_out_cubic(prog)

        # Rise from below
        cur_y = int(self.y + (1.0 - eased) * self.rise_distance)
        cur_x = self.x

        is_act = self.is_active(t)
        
        # High-tech card overlay
        card_surf = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(card_surf)

        border_col = self.tag_color if is_act else (45, 60, 95)
        border_w = 2 if is_act else 1
        bg_col = (18, 28, 52, int(230 * opacity)) if not is_act else (24, 38, 70, int(250 * opacity))

        c_draw.rounded_rectangle([0, 0, self.width - 1, self.height - 1], radius=12, fill=bg_col, outline=border_col, width=border_w)

        # Tag Pill
        if self.tag:
            tag_bg = (*self.tag_color, 45 if not is_act else 90)
            c_draw.rounded_rectangle([16, 16, 90, 46], radius=6, fill=tag_bg)
            c_draw.text((26, 23), self.tag, fill=self.tag_color)

        # Title
        c_draw.text((16, 68), self.title, fill=(255, 255, 255, int(255 * opacity)))

        # Subtitle / Details
        # Wrap subtitle lines simply if needed
        c_draw.text((16, 104), self.subtitle, fill=(150, 165, 195, int(220 * opacity)))

        # Active node indicator
        node_color = self.tag_color if is_act else (70, 90, 130)
        c_draw.ellipse([self.width // 2 - 5, self.height - 24, self.width // 2 + 5, self.height - 14], fill=node_color)

        canvas.alpha_composite(card_surf, (cur_x, cur_y))


class ConnectorTrackElement(MotionElement):
    """Animated SVG-style timeline track or connector cable that draws progressively."""

    def __init__(
        self,
        element_id: str,
        start_pt: Tuple[int, int],
        end_pt: Tuple[int, int],
        enter_time: float = 0.5,
        draw_duration: float = 2.0,
        color: Tuple[int, int, int] = (0, 240, 255),
        track_color: Tuple[int, int, int] = (30, 45, 75),
        stroke_width: int = 3,
        show_pulse_head: bool = True,
    ) -> None:
        super().__init__(element_id, enter_time, draw_duration, easing="ease_out_cubic")
        self.start_pt = start_pt
        self.end_pt = end_pt
        self.color = color
        self.track_color = track_color
        self.stroke_width = stroke_width
        self.show_pulse_head = show_pulse_head

    def render(self, canvas: Image.Image, draw: ImageDraw.Draw, t: float, w: int, h: int) -> None:
        if not self.is_visible(t):
            return

        prog = self.get_enter_progress(t)
        eased = ease_out_cubic(prog)

        x1, y1 = self.start_pt
        x2, y2 = self.end_pt

        # Current head position
        cur_x = x1 + (x2 - x1) * eased
        cur_y = y1 + (y2 - y1) * eased

        # Base track
        draw.line([self.start_pt, self.end_pt], fill=(*self.track_color, 160), width=self.stroke_width)

        # Active glowing progress
        draw.line([(x1, y1), (cur_x, cur_y)], fill=(*self.color, 240), width=self.stroke_width)

        # Pulsing tip
        if self.show_pulse_head and prog < 1.0:
            draw.ellipse([cur_x - 6, cur_y - 6, cur_x + 6, cur_y + 6], fill=(*self.color, 255))


class MetricCounterElement(MotionElement):
    """Rolling numerical counter with exponential decay landing and progress bar."""

    def __init__(
        self,
        element_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        label: str,
        target_value: int,
        suffix: str = "",
        enter_time: float = 2.0,
        count_duration: float = 1.8,
        accent_color: Tuple[int, int, int] = (0, 240, 255),
    ) -> None:
        super().__init__(element_id, enter_time, count_duration, easing="ease_out_expo")
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.label = label
        self.target_value = target_value
        self.suffix = suffix
        self.accent_color = accent_color

    def render(self, canvas: Image.Image, draw: ImageDraw.Draw, t: float, w: int, h: int) -> None:
        if not self.is_visible(t):
            return

        prog = self.get_enter_progress(t)
        eased = ease_out_expo(prog)
        current_val = int(eased * self.target_value)
        formatted = f"{current_val:,} {self.suffix}".strip()

        # Container card
        panel_surf = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(panel_surf)
        p_draw.rounded_rectangle(
            [0, 0, self.width - 1, self.height - 1],
            radius=12,
            fill=(15, 24, 45, 220),
            outline=(*self.accent_color, 80),
            width=1,
        )

        p_draw.text((25, 18), self.label.upper(), fill=(*self.accent_color, 220))
        p_draw.text((25, 45), formatted, fill=(255, 255, 255, 255))

        # Dynamic fill bar
        bar_w = int((self.width - 50) * ease_out_cubic(prog))
        p_draw.rounded_rectangle([25, self.height - 22, 25 + bar_w, self.height - 16], radius=3, fill=(*self.accent_color, 255))

        canvas.alpha_composite(panel_surf, (self.x, self.y))


class AttentionHeatmapElement(MotionElement):
    """Dynamic multi-token attention matrix where cells light up progressively."""

    def __init__(
        self,
        element_id: str,
        x: int,
        y: int,
        tokens: List[str],
        weights: List[List[float]],
        enter_time: float = 1.0,
        enter_duration: float = 1.5,
        active_token_idx: Optional[int] = None,
        base_color: Tuple[int, int, int] = (236, 72, 153),  # Neon Pink
    ) -> None:
        super().__init__(element_id, enter_time, enter_duration, easing="ease_out_cubic")
        self.x = x
        self.y = y
        self.tokens = tokens
        self.weights = weights
        self.active_token_idx = active_token_idx
        self.base_color = base_color

    def render(self, canvas: Image.Image, draw: ImageDraw.Draw, t: float, w: int, h: int) -> None:
        if not self.is_visible(t):
            return

        prog = self.get_enter_progress(t)
        n = len(self.tokens)
        cell_size = 52
        gap = 4

        surf = Image.new("RGBA", (n * (cell_size + gap) + 120, n * (cell_size + gap) + 60), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(surf)

        # Header label
        s_draw.text((10, 5), "SELF-ATTENTION WEIGHT MATRIX", fill=(0, 240, 255, int(220 * prog)))

        grid_offset_x = 100
        grid_offset_y = 35

        for i in range(n):
            # Row token label
            s_draw.text((10, grid_offset_y + i * (cell_size + gap) + 16), self.tokens[i], fill=(220, 230, 245, int(240 * prog)))
            for j in range(n):
                cell_prog = clamp((prog - (i * 0.05 + j * 0.03)) / 0.4)
                if cell_prog <= 0:
                    continue

                weight = self.weights[i][j]
                cx = grid_offset_x + j * (cell_size + gap)
                cy = grid_offset_y + i * (cell_size + gap)

                intensity = int(weight * 255 * cell_prog)
                cell_bg = (*self.base_color, int(max(30, intensity)))

                s_draw.rounded_rectangle([cx, cy, cx + cell_size, cy + cell_size], radius=6, fill=cell_bg)
                s_draw.text((cx + 12, cy + 18), f"{weight:.2f}", fill=(255, 255, 255, int(240 * cell_prog)))

        canvas.alpha_composite(surf, (self.x, self.y))
