"""
Chromatic aberration, scanline jitter, and glitch effects for impact hits and high-tech shockwaves.
"""

import math
import random
from typing import Tuple, Optional
from PIL import Image, ImageChops


def apply_chromatic_aberration(
    im: Image.Image,
    offset_x: int = 0,
    offset_y: int = 0,
    shift_px: Optional[int] = None,
) -> Image.Image:
    """
    Splits and offsets the Red and Blue channels to create optical chromatic aberration.

    Args:
        im: PIL RGB or RGBA Image.
        offset_x: Pixel displacement on X-axis.
        offset_y: Pixel displacement on Y-axis.
        shift_px: Alias for offset_x.

    Returns:
        New PIL Image with split channels.
    """
    ox = shift_px if shift_px is not None else offset_x
    oy = offset_y

    if ox == 0 and oy == 0:
        return im

    orig_mode = im.mode
    im_rgb = im.convert("RGB")
    r, g, b = im_rgb.split()

    r_shifted = ImageChops.offset(r, ox, oy)
    b_shifted = ImageChops.offset(b, -ox, -oy)

    glitched = Image.merge("RGB", (r_shifted, g, b_shifted))
    if orig_mode == "RGBA" and len(im.split()) == 4:
        glitched.putalpha(im.split()[3])
    return glitched


def apply_scanline_glitch(
    im: Image.Image,
    intensity: float = 0.5,
    num_slices: int = 6,
    seed: int = 42,
    glitch_intensity: Optional[float] = None,
) -> Image.Image:
    """
    Slices horizontal bands of the image and displaces them horizontally to simulate digital signal drop.

    Args:
        im: PIL Image.
        intensity: Glitch magnitude (0.0 to 1.0).
        num_slices: Number of displaced horizontal slices.
        seed: Random seed for deterministic playback.
        glitch_intensity: Alias for intensity.

    Returns:
        Glitched PIL Image.
    """
    inten = glitch_intensity if glitch_intensity is not None else intensity
    if inten <= 0.001 or num_slices <= 0:
        return im

    out = im.copy()
    w, h = im.size
    rng = random.Random(seed)

    max_shift = int(w * 0.05 * inten)
    if max_shift <= 0:
        return im

    for _ in range(num_slices):
        slice_y = rng.randint(0, max(0, h - 20))
        slice_h = rng.randint(4, 28)
        shift_x = rng.randint(-max_shift, max_shift)

        if slice_y + slice_h <= h and shift_x != 0:
            box = (0, slice_y, w, slice_y + slice_h)
            slice_crop = im.crop(box)
            shifted_slice = ImageChops.offset(slice_crop, shift_x, 0)
            out.paste(shifted_slice, (0, slice_y))

    return out


def compute_camera_shake(
    t: float = 0.0,
    impact_t: Optional[float] = None,
    decay_duration: float = 0.6,
    max_offset: float = 12.0,
    frequency: float = 55.0,
    trauma: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Computes camera shake displacement vector following an impact event or trauma level.

    Args:
        t: Current scene timestamp or trauma level (if impact_t is None and trauma is None).
        impact_t: Timestamp when the impact occurred.
        decay_duration: Seconds for the shake to decay to zero.
        max_offset: Maximum pixel shake distance.
        frequency: Oscillation frequency in Hz.
        trauma: Explicit trauma level in [0.0, 1.0].

    Returns:
        (shake_x, shake_y) offsets in pixels.
    """
    # Case 1: Called with explicit trauma or single scalar trauma (impact_t is None)
    if trauma is not None or impact_t is None:
        tr = trauma if trauma is not None else t
        if tr <= 0.001:
            return (0.0, 0.0)
        rng = random.Random(int(tr * 1000))
        envelope = tr * tr
        shake_x = (rng.random() * 2.0 - 1.0) * max_offset * envelope
        shake_y = (rng.random() * 2.0 - 1.0) * max_offset * 0.7 * envelope
        return (shake_x, shake_y)

    # Case 2: Called with timestamp t and impact_t
    dt = t - impact_t
    if dt < 0.0 or dt > decay_duration:
        return (0.0, 0.0)

    envelope = math.exp(-4.5 * (dt / decay_duration))
    shake_x = math.sin(dt * frequency) * max_offset * envelope
    shake_y = math.cos(dt * frequency * 0.85) * max_offset * 0.7 * envelope
    return (shake_x, shake_y)
