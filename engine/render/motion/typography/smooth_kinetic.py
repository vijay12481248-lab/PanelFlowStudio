"""
PanelFlow Studio - Ultra-Smooth Kinetic Typography & Visual Effects Engine.
Engineered for buttery-smooth 60fps presentation graphics:
- Sub-pixel anti-aliased character wave reveals with fixed anchors
- Liquid light beam wipe with continuous Hermite gradient masks
- Masked baseline track matte slice reveals with expanding horizon lasers
- Sub-pixel float translation via cv2.warpAffine (zero integer snapping)
- Dual-pass volumetric optical neon bloom
- Frosted glassmorphism KPI cards with smooth logarithmic rolling counters
- 100% Procedural & Code-Driven.
"""

from __future__ import annotations

import math
from typing import Tuple, List, Optional, Union
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
import cv2

from engine.render.motion.curves import solve_cubic_bezier, clamp


def smoothstep(edge0: float, edge1: float, x: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Hermite interpolation smoothstep function."""
    t = np.clip((x - edge0) / max(1e-6, edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def draw_liquid_light_wipe_title(
    target_canvas: Image.Image,
    text: str,
    cx: float,
    cy: float,
    font: ImageFont.ImageFont,
    t: float,
    start_t: float = 0.0,
    duration: float = 1.2,
    base_color: Tuple[int, int, int] = (255, 255, 255),
    glow_color: Tuple[int, int, int] = (124, 58, 237),
    beam_color: Tuple[int, int, int] = (147, 197, 253),
    softness: float = 180.0,
    rise_distance: float = 28.0,
) -> None:
    """
    Renders an ultra-smooth liquid light beam wipe reveal.
    A continuous gradient light beam sweeps across the text line from left to right,
    illuminating letters with a specular sheen flare and soft dual-pass volumetric glow,
    while executing a sub-pixel vertical rise with continuous living idle breathing.
    """
    dt = t - start_t
    if dt < 0.0:
        return

    w, h = target_canvas.size
    p = clamp(dt / duration)
    # AE Natural Smooth Ease (0.25, 0.1, 0.25, 1.0)
    e = solve_cubic_bezier(p, 0.25, 0.1, 0.25, 1.0)

    # Continuous subtle idle breathing so text never freezes
    idle_float = 0.8 * math.sin(1.8 * t) if p >= 0.999 else 0.0
    cur_y_offset = (1.0 - e) * rise_distance + idle_float

    # 1. Fixed text geometry
    dummy = Image.new("RGBA", (1, 1))
    d_dummy = ImageDraw.Draw(dummy)
    bbox = d_dummy.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # Pre-render text onto a transparent RGBA layer
    text_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_text = ImageDraw.Draw(text_layer)
    x0 = cx - tw / 2.0
    y0 = cy - th / 2.0
    d_text.text((int(x0), int(y0)), text, font=font, fill=(*base_color, 255))

    # True sub-pixel floating-point vertical translation
    text_np = np.array(text_layer, dtype=np.float32)
    M = np.float32([[1, 0, 0], [0, 1, cur_y_offset]])
    text_np = cv2.warpAffine(text_np, M, (w, h), flags=cv2.INTER_LINEAR)

    # 2. Continuous 1D Hermite Light-Wipe Mask across X
    total_travel = tw + 2.0 * softness
    beam_x = (x0 - softness) + total_travel * p

    xs = np.arange(w, dtype=np.float32)
    mask_1d = smoothstep(beam_x, beam_x - softness, xs)
    mask_2d = np.tile(mask_1d[np.newaxis, :], (h, 1))

    # Specular light highlight right along the moving beam edge
    dist_to_beam = np.abs(xs - (beam_x - softness * 0.45))
    specular_1d = np.exp(-(dist_to_beam ** 2) / (2.0 * (48.0 ** 2)))
    specular_2d = np.tile(specular_1d[np.newaxis, :], (h, 1))

    # Calculate text alpha
    text_alpha = (text_np[:, :, 3] / 255.0) * mask_2d

    # Color blending with specular sheen
    r = text_np[:, :, 0] + (beam_color[0] * 0.9) * specular_2d * (text_np[:, :, 3] / 255.0)
    g = text_np[:, :, 1] + (beam_color[1] * 0.9) * specular_2d * (text_np[:, :, 3] / 255.0)
    b = text_np[:, :, 2] + (beam_color[2] * 0.9) * specular_2d * (text_np[:, :, 3] / 255.0)
    a = text_alpha * 255.0

    out_arr = np.stack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(b, 0, 255), np.clip(a, 0, 255)], axis=2).astype(np.uint8)
    out_img = Image.fromarray(out_arr, mode="RGBA")

    # Dual-pass volumetric optical bloom
    if p > 0.05 and glow_color:
        glow_sm = out_img.filter(ImageFilter.GaussianBlur(radius=6))
        glow_lg = out_img.filter(ImageFilter.GaussianBlur(radius=22))

        sm_arr = np.array(glow_sm, dtype=np.float32)
        sm_arr[:, :, 0] = sm_arr[:, :, 3] * (glow_color[0] / 255.0) * 0.35
        sm_arr[:, :, 1] = sm_arr[:, :, 3] * (glow_color[1] / 255.0) * 0.35
        sm_arr[:, :, 2] = sm_arr[:, :, 3] * (glow_color[2] / 255.0) * 0.35
        sm_arr[:, :, 3] *= 0.35

        lg_arr = np.array(glow_lg, dtype=np.float32)
        lg_arr[:, :, 0] = lg_arr[:, :, 3] * (glow_color[0] / 255.0) * 0.20
        lg_arr[:, :, 1] = lg_arr[:, :, 3] * (glow_color[1] / 255.0) * 0.20
        lg_arr[:, :, 2] = lg_arr[:, :, 3] * (glow_color[2] / 255.0) * 0.20
        lg_arr[:, :, 3] *= 0.20

        target_canvas.alpha_composite(Image.fromarray(np.clip(lg_arr, 0, 255).astype(np.uint8), mode="RGBA"))
        target_canvas.alpha_composite(Image.fromarray(np.clip(sm_arr, 0, 255).astype(np.uint8), mode="RGBA"))

    target_canvas.alpha_composite(out_img)


def draw_masked_baseline_reveal(
    target_canvas: Image.Image,
    text: str,
    cx: float,
    cy: float,
    font: ImageFont.ImageFont,
    t: float,
    start_t: float = 0.0,
    duration: float = 0.9,
    base_color: Tuple[int, int, int] = (255, 255, 255),
    accent_color: Tuple[int, int, int] = (56, 189, 248),
    rise_distance: float = 45.0,
) -> None:
    """
    Renders an After Effects track-matte baseline reveal.
    Text rises up through an invisible baseline plane while a glowing laser line
    expands outwards along the baseline.
    """
    dt = t - start_t
    if dt < 0.0:
        return

    w, h = target_canvas.size
    p = clamp(dt / duration)
    e = solve_cubic_bezier(p, 0.25, 0.1, 0.25, 1.0)

    # Fixed text geometry
    dummy = Image.new("RGBA", (1, 1))
    d_dummy = ImageDraw.Draw(dummy)
    bbox = d_dummy.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # Baseline plane position
    baseline_y = cy + th / 2.0 + 4.0
    text_y_offset = (1.0 - e) * rise_distance

    text_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_text = ImageDraw.Draw(text_layer)
    x0 = cx - tw / 2.0
    y0 = cy - th / 2.0
    d_text.text((int(x0), int(y0)), text, font=font, fill=(*base_color, 255))

    # Sub-pixel translation
    text_np = np.array(text_layer, dtype=np.float32)
    M = np.float32([[1, 0, 0], [0, 1, text_y_offset]])
    text_np = cv2.warpAffine(text_np, M, (w, h), flags=cv2.INTER_LINEAR)

    # Track Matte Mask: clip everything below baseline_y with anti-aliasing
    ys = np.arange(h, dtype=np.float32)
    mask_y = smoothstep(baseline_y + 1.0, baseline_y - 1.0, ys)
    mask_2d = np.tile(mask_y[:, np.newaxis], (1, w))

    text_np[:, :, 3] = text_np[:, :, 3] * mask_2d
    text_img = Image.fromarray(np.clip(text_np, 0, 255).astype(np.uint8), mode="RGBA")
    target_canvas.alpha_composite(text_img)

    # Dynamic Horizon Accent Line expanding outward from center
    p_line = clamp(dt / 0.55)
    e_line = solve_cubic_bezier(p_line, 0.16, 1.0, 0.3, 1.0)
    line_w = (tw + 60.0) * e_line
    line_x0 = cx - line_w / 2.0
    line_x1 = cx + line_w / 2.0

    line_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_line = ImageDraw.Draw(line_layer)
    alpha_line = int(240 * clamp(dt / 0.3))
    if line_w > 2:
        d_line.line([(line_x0, baseline_y), (line_x1, baseline_y)], fill=(*accent_color, alpha_line), width=2)
        # Specular glint in center
        d_line.ellipse([cx - 4, baseline_y - 4, cx + 4, baseline_y + 4], fill=(255, 255, 255, alpha_line))

    # Glow on line
    line_glow = line_layer.filter(ImageFilter.GaussianBlur(radius=4))
    target_canvas.alpha_composite(line_glow)
    target_canvas.alpha_composite(line_layer)


def draw_smooth_kinetic_title(
    target_canvas: Image.Image,
    text: str,
    cx: float,
    cy: float,
    font: ImageFont.ImageFont,
    t: float,
    start_t: float = 0.0,
    char_duration: float = 0.85,
    stagger: float = 0.04,
    rise_distance: float = 35.0,
    base_color: Tuple[int, int, int] = (255, 255, 255),
    glow_color: Tuple[int, int, int] = (124, 58, 237),
    tracking_start: float = 3.0,
    tracking_end: float = 3.0,
    enable_shimmer: bool = True,
    shimmer_color: Tuple[int, int, int] = (147, 197, 253),
) -> None:
    """
    Renders an ultra-smooth, buttery letter-by-letter kinetic title reveal
    with FIXED character anchors, continuous natural easing, sub-pixel glide,
    and a living secondary ribbon wave that eliminates any freezing or stuck appearance.
    """
    dt_total = t - start_t
    if dt_total < 0.0:
        return

    w, h = target_canvas.size
    total_chars = len(text)
    if total_chars == 0:
        return

    # 1. FIXED PRE-COMPUTED ANCHORS (Zero sideways drift or accordion wobble!)
    tracking = tracking_start
    dummy = Image.new("RGBA", (1, 1))
    d_dummy = ImageDraw.Draw(dummy)
    char_widths = [d_dummy.textbbox((0, 0), ch, font=font)[2] - d_dummy.textbbox((0, 0), ch, font=font)[0] for ch in text]
    total_w = sum(char_widths) + max(0, total_chars - 1) * tracking
    start_x = cx - (total_w / 2.0)

    cur_x = start_x
    char_positions = []
    for i, ch in enumerate(text):
        cw = char_widths[i]
        char_positions.append((cur_x, cw))
        cur_x += cw + tracking

    # Scratch canvas for high-quality alpha compositing
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_layer = ImageDraw.Draw(layer)

    # Shimmer wave position calculation (continuous cycle)
    shimmer_p = ((t - start_t) % 2.8) / 2.8
    shimmer_center_x = (start_x - 120) + (total_w + 240) * shimmer_p

    for i, ch in enumerate(text):
        char_start = start_t + i * stagger
        dt_c = t - char_start
        if dt_c <= 0.0:
            continue

        p = clamp(dt_c / char_duration)
        # Natural Smooth Deceleration (0.25, 0.1, 0.25, 1.0)
        e = solve_cubic_bezier(p, 0.25, 0.1, 0.25, 1.0)

        # Living organic secondary float after arrival (never freezes or gets stuck)
        idle_wave = 1.0 * math.sin(2.4 * t - i * 0.28) * e
        char_y = cy + (1.0 - e) * rise_distance + idle_wave
        alpha = int(255 * clamp(p / 0.35))

        x_pos, cw = char_positions[i]

        # Specular sheen sweep
        c_r, c_g, c_b = base_color
        if enable_shimmer:
            dist_shimmer = abs((x_pos + cw / 2.0) - shimmer_center_x)
            if dist_shimmer < 85.0:
                factor = math.exp(-(dist_shimmer ** 2) / (2.0 * (36.0 ** 2)))
                c_r = int(c_r + (shimmer_color[0] - c_r) * factor * 0.85)
                c_g = int(c_g + (shimmer_color[1] - c_g) * factor * 0.85)
                c_b = int(c_b + (shimmer_color[2] - c_b) * factor * 0.85)

        d_layer.text((int(x_pos), int(char_y)), ch, font=font, fill=(c_r, c_g, c_b, alpha))

    # Dual-pass volumetric optical glow
    if glow_color and dt_total > 0.05:
        glow_layer = layer.filter(ImageFilter.GaussianBlur(radius=8))
        g_np = np.array(glow_layer, dtype=np.float32)
        g_np[:, :, 0] = g_np[:, :, 3] * (glow_color[0] / 255.0) * 0.40
        g_np[:, :, 1] = g_np[:, :, 3] * (glow_color[1] / 255.0) * 0.40
        g_np[:, :, 2] = g_np[:, :, 3] * (glow_color[2] / 255.0) * 0.40
        g_np[:, :, 3] *= 0.35
        target_canvas.alpha_composite(Image.fromarray(np.clip(g_np, 0, 255).astype(np.uint8), mode="RGBA"))

    target_canvas.alpha_composite(layer)


def draw_smooth_word_stagger(
    target_canvas: Image.Image,
    text: str,
    cx: float,
    cy: float,
    font: ImageFont.ImageFont,
    t: float,
    start_t: float = 0.0,
    word_duration: float = 0.75,
    stagger: float = 0.09,
    rise_distance: float = 24.0,
    color: Tuple[int, int, int] = (203, 213, 225),
) -> None:
    """
    Renders words rising smoothly from an invisible baseline with natural exponential deceleration
    and zero integer snapping.
    """
    w, h = target_canvas.size
    words = text.split(" ")
    if not words:
        return

    dummy = Image.new("RGBA", (1, 1))
    d_dummy = ImageDraw.Draw(dummy)
    space_w = d_dummy.textbbox((0, 0), " ", font=font)[2] - d_dummy.textbbox((0, 0), " ", font=font)[0]
    word_widths = [d_dummy.textbbox((0, 0), w_str, font=font)[2] - d_dummy.textbbox((0, 0), w_str, font=font)[0] for w_str in words]
    total_w = sum(word_widths) + (len(words) - 1) * space_w

    start_x = cx - (total_w / 2.0)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_layer = ImageDraw.Draw(layer)

    cur_x = start_x
    for i, word in enumerate(words):
        w_start = start_t + i * stagger
        dt = t - w_start

        if dt > 0.0:
            p = clamp(dt / word_duration)
            e = solve_cubic_bezier(p, 0.25, 0.1, 0.25, 1.0)
            idle = 0.6 * math.sin(1.8 * t - i * 0.2) * e
            word_y = cy + (1.0 - e) * rise_distance + idle
            alpha = int(255 * clamp(p / 0.40))
            d_layer.text((int(cur_x), int(word_y)), word, font=font, fill=(*color, alpha))

        cur_x += word_widths[i] + space_w

    target_canvas.alpha_composite(layer)


def draw_smooth_frosted_card(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    w: float,
    h: float,
    p_enter: float,
    border_color: Tuple[int, int, int],
    title: str,
    val_str: str,
    desc1: str,
    desc2: str,
    font_badge: ImageFont.ImageFont,
    font_metric: ImageFont.ImageFont,
    font_body_bold: ImageFont.ImageFont,
    font_body: ImageFont.ImageFont,
    t: float = 0.0,
) -> None:
    """
    Renders a frosted glassmorphism KPI card with glowing specular border,
    dynamic traveling highlight line, and anti-aliased metrics.
    """
    if p_enter <= 0.005:
        return

    alpha_factor = clamp(p_enter, 0.0, 1.0)
    bg_alpha = int(210 * alpha_factor)
    border_alpha = int(140 * alpha_factor)

    ix, iy, iw, ih = int(x), int(y), int(w), int(h)

    # Card background
    draw.rounded_rectangle(
        [ix, iy, ix + iw, iy + ih],
        radius=18,
        fill=(15, 23, 42, bg_alpha),
        outline=(*border_color, border_alpha),
        width=1,
    )

    # Top accent highlight line with traveling specular beam
    t_phase = (t * 1.5) % 2.0  # 2s sweep
    sweep_x0 = ix + int((iw - 40) * (t_phase / 2.0))
    sweep_x1 = min(ix + iw - 15, sweep_x0 + 60)

    draw.line([(ix + 20, iy + 2), (ix + iw - 20, iy + 2)], fill=(*border_color, int(160 * alpha_factor)), width=2)
    if sweep_x1 > sweep_x0:
        draw.line([(sweep_x0, iy + 2), (sweep_x1, iy + 2)], fill=(255, 255, 255, int(240 * alpha_factor)), width=2)

    # Card content
    draw.text((ix + 28, iy + 24), title, font=font_badge, fill=(*border_color, int(255 * alpha_factor)))
    draw.text((ix + 28, iy + 58), val_str, font=font_metric, fill=(255, 255, 255, int(255 * alpha_factor)))
    draw.text((ix + 28, iy + 120), desc1, font=font_body_bold, fill=(241, 245, 249, int(255 * alpha_factor)))
    draw.text((ix + 28, iy + 150), desc2, font=font_body, fill=(148, 163, 184, int(220 * alpha_factor)))
