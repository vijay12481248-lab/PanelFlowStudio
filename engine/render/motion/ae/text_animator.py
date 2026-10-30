"""
Adobe After Effects Text Animator & Range Selector Engine.
Implements After Effects per-character and per-word kinetic typography:
- Range Selectors: Start, End, Offset, Shapes (Square, Ramp Up, Ramp Down, Triangle, Smooth, Round)
- Units: Characters, Words
- Animated Properties: Position offset, Scale, Rotation, Opacity, Tracking, Blur
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from engine.render.motion.curves import clamp


@dataclass
class RangeSelector:
    """
    After Effects Range Selector model.
    Governs glyph influence using Start, End, Offset, and Shape curves.
    """
    start: float = 0.0       # Percentage [0.0, 100.0]
    end: float = 100.0       # Percentage [0.0, 100.0]
    offset: float = 0.0      # Percentage [-100.0, 100.0]
    shape: str = "smooth"    # square, ramp_up, ramp_down, triangle, round, smooth
    based_on: str = "characters"  # characters, words, lines
    randomize_order: bool = False
    random_seed: int = 1337

    def calculate_influence(self, item_index: int, total_items: int) -> float:
        """
        Calculates the influence factor in [0.0, 1.0] for the given item index.
        """
        if total_items <= 0:
            return 0.0

        # Permute index if randomized
        eval_idx = item_index
        if self.randomize_order:
            rng = random.Random(self.random_seed + item_index * 13)
            perm = list(range(total_items))
            random.Random(self.random_seed).shuffle(perm)
            eval_idx = perm[item_index]

        # Normalized item center in percentage [0.0, 100.0]
        item_pct = (eval_idx / max(1, total_items - 1)) * 100.0 if total_items > 1 else 50.0

        # Effective window after offset
        w_start = self.start + self.offset
        w_end = self.end + self.offset

        if w_start == w_end:
            return 1.0 if item_pct <= w_start else 0.0

        # Fraction across selector window [0.0, 1.0]
        if item_pct <= min(w_start, w_end):
            frac = 0.0 if w_start < w_end else 1.0
        elif item_pct >= max(w_start, w_end):
            frac = 1.0 if (item_pct == max(w_start, w_end) and w_start < w_end) else 0.0
        else:
            frac = (item_pct - w_start) / (w_end - w_start)

        frac = clamp(frac, 0.0, 1.0)

        # Apply After Effects shape transfer function
        if self.shape == "square":
            return 1.0 if (min(w_start, w_end) <= item_pct <= max(w_start, w_end)) else 0.0

        elif self.shape == "ramp_up":
            return frac

        elif self.shape == "ramp_down":
            return 1.0 - frac

        elif self.shape == "triangle":
            # Peaks at 0.5
            return 2.0 * frac if frac < 0.5 else 2.0 * (1.0 - frac)

        elif self.shape == "round":
            # Cosine bell curve
            return 0.5 * (1.0 - math.cos(frac * math.pi))

        elif self.shape == "smooth":
            # Cubic Hermite smoothstep 3x^2 - 2x^3
            return frac * frac * (3.0 - 2.0 * frac)

        return frac


@dataclass
class TextAnimatorProperties:
    """Properties animated by the After Effects Text Animator."""
    position_offset: Tuple[float, float] = (0.0, 0.0)  # (dx, dy)
    scale: Tuple[float, float] = (1.0, 1.0)            # (sx, sy)
    rotation: float = 0.0                              # degrees
    opacity: float = 1.0                               # [0.0, 1.0]
    tracking: float = 0.0                              # Extra pixel space between glyphs
    blur: float = 0.0                                  # Gaussian blur radius in pixels


@dataclass
class GlyphLayout:
    text: str
    index: int
    char_x: float
    char_y: float
    char_w: float
    char_h: float
    influence: float = 0.0
    # Final transformed values
    render_x: float = 0.0
    render_y: float = 0.0
    render_scale_x: float = 1.0
    render_scale_y: float = 1.0
    render_rotation: float = 0.0
    render_opacity: float = 1.0
    render_blur: float = 0.0


class AETextAnimator:
    """
    Evaluates and composites After Effects kinetic typography.
    """

    def __init__(
        self,
        range_selector: Optional[RangeSelector] = None,
        properties: Optional[TextAnimatorProperties] = None,
    ):
        self.range_selector = range_selector or RangeSelector()
        self.properties = properties or TextAnimatorProperties()

    def layout_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        start_x: float,
        start_y: float,
        anchor: str = "center",
    ) -> List[GlyphLayout]:
        """
        Lays out glyphs or words and applies the Range Selector influence to each item.
        """
        items: List[str] = []
        if self.range_selector.based_on == "words":
            # Split by words preserving spacing
            items = text.split(" ")
        else:
            items = list(text)

        total_items = len(items)
        layouts: List[GlyphLayout] = []

        # Measure dimensions
        dummy_img = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(dummy_img)

        # Baseline measurement
        total_w = 0.0
        max_h = 0.0
        item_widths: List[float] = []

        for it in items:
            repr_str = it if self.range_selector.based_on != "words" else (it + " ")
            bbox = draw.textbbox((0, 0), repr_str, font=font)
            w = float(bbox[2] - bbox[0])
            h = float(bbox[3] - bbox[1])
            item_widths.append(w)
            total_w += w + self.properties.tracking
            max_h = max(max_h, h)

        # Apply anchor alignment
        cur_x = start_x
        if anchor == "center":
            cur_x = start_x - (total_w / 2.0)
        elif anchor == "right":
            cur_x = start_x - total_w

        cur_y = start_y
        if anchor == "center":
            cur_y = start_y - (max_h / 2.0)

        # Layout each item and compute AE transforms
        for idx, it in enumerate(items):
            infl = self.range_selector.calculate_influence(idx, total_items)
            w = item_widths[idx]
            h = max_h

            gl = GlyphLayout(
                text=it if self.range_selector.based_on != "words" else (it + " "),
                index=idx,
                char_x=cur_x,
                char_y=cur_y,
                char_w=w,
                char_h=h,
                influence=infl,
            )

            # Interpolate transformed properties by influence
            gl.render_x = cur_x + (self.properties.position_offset[0] * (1.0 - infl))
            gl.render_y = cur_y + (self.properties.position_offset[1] * (1.0 - infl))
            gl.render_scale_x = 1.0 + (self.properties.scale[0] - 1.0) * (1.0 - infl)
            gl.render_scale_y = 1.0 + (self.properties.scale[1] - 1.0) * (1.0 - infl)
            gl.render_rotation = self.properties.rotation * (1.0 - infl)
            gl.render_opacity = self.properties.opacity + (1.0 - self.properties.opacity) * infl
            gl.render_blur = self.properties.blur * (1.0 - infl)

            layouts.append(gl)
            cur_x += w + self.properties.tracking

        return layouts

    def render_to_canvas(
        self,
        canvas: Image.Image,
        text: str,
        font: ImageFont.FreeTypeFont,
        origin: Tuple[int, int] = (640, 360),
        fill_color: Tuple[int, int, int] = (255, 255, 255),
        anchor: str = "center",
    ) -> Image.Image:
        """
        Renders the kinetic text with AE transforms and tracking onto canvas.
        """
        layouts = self.layout_text(text, font, origin[0], origin[1], anchor=anchor)

        for gl in layouts:
            if gl.render_opacity <= 0.01:
                continue

            # Render glyph into localized transparent scratch buffer for rotation/scale
            margin = 32
            pad_w = int(gl.char_w + margin * 2)
            pad_h = int(gl.char_h + margin * 2)

            glyph_img = Image.new("RGBA", (max(16, pad_w), max(16, pad_h)), (0, 0, 0, 0))
            g_draw = ImageDraw.Draw(glyph_img)

            # Color with evaluated opacity
            alpha = int(clamp(gl.render_opacity, 0.0, 1.0) * 255)
            rgba = (fill_color[0], fill_color[1], fill_color[2], alpha)

            g_draw.text((margin, margin), gl.text, font=font, fill=rgba)

            # Optional glyph blur
            if gl.render_blur > 0.5:
                glyph_img = glyph_img.filter(ImageFilter.GaussianBlur(radius=gl.render_blur))

            # Apply scale & rotation from glyph anchor
            if abs(gl.render_rotation) > 0.1 or abs(gl.render_scale_x - 1.0) > 0.01 or abs(gl.render_scale_y - 1.0) > 0.01:
                scaled_w = max(1, int(glyph_img.width * max(0.01, gl.render_scale_x)))
                scaled_h = max(1, int(glyph_img.height * max(0.01, gl.render_scale_y)))
                glyph_img = glyph_img.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
                if abs(gl.render_rotation) > 0.1:
                    glyph_img = glyph_img.rotate(gl.render_rotation, resample=Image.Resampling.BICUBIC, expand=True)

            # Composite onto canvas
            paste_x = int(gl.render_x - (glyph_img.width / 2.0) + (gl.char_w / 2.0))
            paste_y = int(gl.render_y - (glyph_img.height / 2.0) + (gl.char_h / 2.0))
            canvas.alpha_composite(glyph_img, (paste_x, paste_y))

        return canvas
