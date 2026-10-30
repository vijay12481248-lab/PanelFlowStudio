"""
Procedural Motion Graphics Transition Shaders.
High-impact transitions between motion graphic shots and manga panels:
1. WhipPanGlitchTransition
2. LightLeakBurnTransition
3. GeometricSliceWipeTransition
"""

import math
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageChops, ImageFilter
from engine.render.motion.effects.chromatic import apply_chromatic_aberration, apply_scanline_glitch
from engine.render.motion.effects.lighting import render_anamorphic_flare


def render_whip_pan_glitch(
    img_a: Image.Image,
    img_b: Image.Image,
    progress: float,
    direction: str = "right",
) -> Image.Image:
    """
    Directional camera whip-pan with high-speed chromatic aberration and scanline slices.
    progress: 0.0 (full img_a) -> 1.0 (full img_b).
    """
    p = max(0.0, min(1.0, progress))
    w, h = img_a.size

    # Exponential-in-out whip velocity curve
    whip_curve = math.sin(p * math.pi)
    offset_px = int(w * p) if direction == "right" else int(-w * p)

    # Shift frames
    composite = Image.new("RGB", (w, h), (0, 0, 0))
    if direction == "right":
        composite.paste(img_a, (-offset_px, 0))
        composite.paste(img_b, (w - offset_px, 0))
    else:
        composite.paste(img_a, (-offset_px, 0))
        composite.paste(img_b, (-w - offset_px, 0))

    # Apply chromatic aberration & glitch peaked at transition midpoint
    if whip_curve > 0.15:
        shift = int(18.0 * whip_curve)
        composite = apply_chromatic_aberration(composite, shift_px=shift)
        composite = apply_scanline_glitch(composite, intensity=0.35 * whip_curve, num_slices=8)

    return composite


def render_light_leak_burn(
    img_a: Image.Image,
    img_b: Image.Image,
    progress: float,
    flare_color: Tuple[int, int, int] = (251, 146, 60),  # Warm amber/orange
) -> Image.Image:
    """
    Analog 35mm optical light leak / film burn transition blowout.
    """
    p = max(0.0, min(1.0, progress))
    w, h = img_a.size

    # Crossfade base images
    blended = Image.blend(img_a.convert("RGB"), img_b.convert("RGB"), p)

    # Volumetric flare blowout curve peaking at p=0.5
    peak = math.sin(p * math.pi)
    if peak > 0.05:
        flare_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cx = int(w * p)
        cy = h // 2
        flare = render_anamorphic_flare(
            (w, h),
            center=(cx, cy),
            color=flare_color,
            length=int(w * 0.8),
            height=int(h * 0.4 * peak),
            alpha=int(240 * peak),
        )
        blended = Image.alpha_composite(blended.convert("RGBA"), flare).convert("RGB")

    return blended


def render_geometric_slice_wipe(
    img_a: Image.Image,
    img_b: Image.Image,
    progress: float,
    num_slices: int = 12,
    border_color: Tuple[int, int, int] = (6, 182, 212),  # Glowing Cyan
) -> Image.Image:
    """
    Diagonal / horizontal geometric shutter wipe with glowing neon edge borders.
    """
    p = max(0.0, min(1.0, progress))
    w, h = img_a.size

    out = img_a.convert("RGB").copy()
    b_rgb = img_b.convert("RGB")
    draw = ImageDraw.Draw(out)

    slice_h = h // num_slices

    for s_i in range(num_slices):
        stagger = (s_i / num_slices) * 0.3
        s_p = max(0.0, min(1.0, (p - stagger) / 0.7))
        slice_w = int(w * s_p)
        sy = s_i * slice_h

        if slice_w > 0:
            box = (0, sy, slice_w, sy + slice_h)
            crop_b = b_rgb.crop(box)
            out.paste(crop_b, (0, sy))

            # Glowing border line on leading edge
            if slice_w < w:
                draw.line([(slice_w, sy), (slice_w, sy + slice_h)], fill=(*border_color, 220), width=2)

    return out
