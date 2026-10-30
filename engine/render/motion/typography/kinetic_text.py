"""
Kinetic typography animations for high-impact titles, subtitles, and telemetry.
"""

import math
import random
from typing import List, Tuple, Optional, Union
from PIL import Image, ImageDraw, ImageFont
from engine.render.motion.curves import ease_out_back, ease_out_expo, ease_out_cubic


GLYPH_SET = list("!@#$%^&*()_+-=[]{}|;:,.<>?/~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ01")


def get_scramble_text(
    target: str,
    progress: float,
    seed: int = 42,
    glyph_pool: Optional[List[str]] = None,
) -> str:
    """
    Computes a hacker/cyberpunk scramble-decryption string.
    progress: 0.0 (all random glyphs) -> 1.0 (fully resolved target string).
    """
    if progress >= 1.0:
        return target

    pool = glyph_pool or GLYPH_SET
    n = len(target)
    prog = max(0.0, progress)
    resolved_count = int(prog * n)
    rng = random.Random(seed + int(prog * 120))

    result = []
    for i in range(n):
        if target[i] == " ":
            result.append(" ")
        elif i < resolved_count:
            result.append(target[i])
        else:
            result.append(rng.choice(pool))
    return "".join(result)


def draw_word_stagger_reveal(
    draw: ImageDraw.ImageDraw,
    text: Optional[Union[str, List[str]]] = None,
    cx: Optional[int] = None,
    y: Optional[int] = None,
    font: Optional[ImageFont.ImageFont] = None,
    t: Optional[float] = None,
    progress: Optional[float] = None,
    center_x: Optional[int] = None,
    baseline_y: Optional[int] = None,
    start_t: float = 0.0,
    stagger_delay: float = 0.12,
    rise_distance: int = 40,
    fill_color: Tuple[int, int, int] = (255, 255, 255),
    color: Optional[Tuple[int, int, int]] = None,
    words: Optional[List[str]] = None,
) -> None:
    """
    Renders words rising from an invisible baseline with staggered spring overshoot.
    """
    raw = words if words is not None else text
    if raw is None:
        return
    words_list = raw if isinstance(raw, list) else raw.split()
    if not words_list:
        return

    eff_cx = center_x if center_x is not None else (cx if cx is not None else 0)
    eff_y = baseline_y if baseline_y is not None else (y if y is not None else 0)
    eff_col = color if color is not None else fill_color
    eff_font = font or ImageFont.load_default()

    # Calculate word dimensions
    space_w = draw.textbbox((0, 0), " ", font=eff_font)[2] - draw.textbbox((0, 0), " ", font=eff_font)[0]
    word_boxes = [draw.textbbox((0, 0), w, font=eff_font) for w in words_list]
    word_widths = [b[2] - b[0] for b in word_boxes]
    total_w = sum(word_widths) + (len(words_list) - 1) * space_w

    cur_x = eff_cx - total_w // 2

    for i, w in enumerate(words_list):
        if progress is not None:
            # Progress based stagger
            word_start = i * stagger_delay
            p = min(1.0, max(0.0, (progress - word_start) / max(0.001, 1.0 - word_start)))
        else:
            cur_t = t if t is not None else 0.0
            w_enter = start_t + i * stagger_delay
            dt = cur_t - w_enter
            p = min(1.0, max(0.0, dt / 0.5)) if dt > 0.0 else 0.0

        if p > 0.0:
            e = ease_out_back(p)
            word_y = int(eff_y + (1.0 - e) * rise_distance)
            alpha = int(255 * min(1.0, p * 1.5))
            draw.text((cur_x, word_y), w, font=eff_font, fill=(*eff_col, alpha))

        cur_x += word_widths[i] + space_w


def draw_tracking_expansion_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    cx: Optional[int] = None,
    y: int = 0,
    font: Optional[ImageFont.ImageFont] = None,
    letter_spacing: Optional[int] = None,
    center_x: Optional[int] = None,
    progress: Optional[float] = None,
    min_tracking: int = 0,
    max_tracking: int = 16,
    color: Optional[Tuple[int, int, int]] = None,
    fill: Optional[Tuple[int, int, int]] = None,
) -> None:
    """
    Draws text with mathematically centered kerning/letter-spacing and expansion animation.
    """
    eff_cx = center_x if center_x is not None else (cx if cx is not None else 0)
    eff_font = font or ImageFont.load_default()
    eff_color = color if color is not None else (fill if fill is not None else (255, 255, 255))

    if letter_spacing is not None:
        tracking = letter_spacing
    elif progress is not None:
        tracking = int(min_tracking + (max_tracking - min_tracking) * progress)
    else:
        tracking = 0

    char_widths = [
        draw.textbbox((0, 0), ch, font=eff_font)[2] - draw.textbbox((0, 0), ch, font=eff_font)[0]
        for ch in text
    ]
    total_w = sum(char_widths) + max(0, len(text) - 1) * tracking
    cur_x = eff_cx - total_w // 2

    for ch, cw in zip(text, char_widths):
        draw.text((cur_x, y), ch, font=eff_font, fill=eff_color)
        cur_x += cw + tracking


def compute_rolling_counter(
    arg1: float,
    arg2: float,
    arg3: float,
    arg4: Optional[float] = None,
    start_value: float = 0.0,
    easing: str = "ease_out_expo",
) -> float:
    """
    Computes smooth momentum deceleration for rolling metric numbers.
    Supports:
        compute_rolling_counter(start_val, target_val, progress, easing="ease_out_expo")
    and:
        compute_rolling_counter(t, start_t, duration, target_value, start_value=0.0)
    """
    if arg4 is not None:
        # Style B: (t, start_t, duration, target_value)
        t, start_t, duration, target_value = arg1, arg2, arg3, arg4
        if t <= start_t:
            return start_value
        p = min(1.0, max(0.0, (t - start_t) / max(0.001, duration)))
        e = ease_out_expo(p)
        return start_value + (target_value - start_value) * e
    else:
        # Style A: (start_val, target_val, progress)
        start_val, target_val, prog = arg1, arg2, arg3
        p = min(1.0, max(0.0, prog))
        if easing == "ease_out_back":
            e = ease_out_back(p)
        elif easing == "ease_out_cubic":
            e = ease_out_cubic(p)
        else:
            e = ease_out_expo(p)
        return start_val + (target_val - start_val) * e


def draw_typewriter_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    cx: int,
    y: int,
    font: Optional[ImageFont.ImageFont] = None,
    progress: float = 1.0,
    show_cursor: bool = True,
    fill: Tuple[int, int, int] = (255, 255, 255),
    cursor_char: str = "_",
) -> None:
    """
    Renders typewriter-style character reveal with optional blinking cursor block.
    """
    eff_font = font or ImageFont.load_default()
    n_chars = max(0, min(len(text), int(len(text) * max(0.0, min(1.0, progress)))))
    revealed = text[:n_chars]

    cursor = cursor_char if (show_cursor and progress < 1.0) else ""
    full_str = revealed + cursor

    bbox = draw.textbbox((0, 0), full_str, font=eff_font)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw // 2, y), full_str, font=eff_font, fill=fill)


def draw_extruded_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: Optional[ImageFont.ImageFont] = None,
    depth: int = 4,
    fill: Tuple[int, int, int] = (255, 255, 255),
    extrusion_color: Tuple[int, int, int] = (15, 23, 42),
    angle_deg: float = 45.0,
) -> None:
    """
    Renders multi-pass 3D extruded bevel shadows to create physical depth on typography.
    """
    eff_font = font or ImageFont.load_default()
    rad = math.radians(angle_deg)
    dx = math.cos(rad)
    dy = math.sin(rad)

    # Render extrusion passes from deepest to closest
    for step in range(depth, 0, -1):
        ox = int(x + dx * step)
        oy = int(y + dy * step)
        draw.text((ox, oy), text, font=eff_font, fill=extrusion_color)

    # Front face
    draw.text((x, y), text, font=eff_font, fill=fill)

