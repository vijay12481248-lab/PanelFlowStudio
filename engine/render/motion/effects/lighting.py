"""
Volumetric lighting, anamorphic lens flares, and vignette shaders.
"""

import math
import numpy as np
from typing import Tuple, Union, Optional
from PIL import Image, ImageDraw, ImageFilter


def render_volumetric_glow(
    target: Union[Tuple[int, int], Image.Image],
    center: Tuple[int, int],
    color: Tuple[int, int, int],
    radius: int = 250,
    alpha: int = 60,
    blur_sigma: int = 70,
) -> Image.Image:
    """
    Creates an atmospheric soft volumetric glow orb with Gaussian blur.
    If target is an Image, returns the composited image or glow overlay.
    """
    w, h = target.size if isinstance(target, Image.Image) else target
    cx, cy = center
    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(surf)

    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(*color, alpha))
    if blur_sigma > 0:
        surf = surf.filter(ImageFilter.GaussianBlur(blur_sigma))

    if isinstance(target, Image.Image):
        return Image.alpha_composite(target.convert("RGBA"), surf)
    return surf


def render_anamorphic_flare(
    target: Union[Tuple[int, int], Image.Image],
    center: Tuple[int, int],
    color: Tuple[int, int, int] = (56, 189, 248),
    streak_width: int = 500,
    streak_height: int = 8,
    alpha: int = 180,
    length: Optional[int] = None,
    height: Optional[int] = None,
) -> Image.Image:
    """
    Renders a Hollywood-style horizontal anamorphic light streak lens flare.
    """
    w, h = target.size if isinstance(target, Image.Image) else target
    cx, cy = center
    sw = length if length is not None else streak_width
    sh = height if height is not None else streak_height

    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(surf)

    # Core bright hotspot
    draw.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], fill=(255, 255, 255, alpha))
    # Wide horizontal anamorphic streak
    draw.ellipse(
        [cx - sw, cy - sh, cx + sw, cy + sh],
        fill=(*color, alpha // 2),
    )
    # Extra wide diffused flare
    draw.ellipse(
        [cx - sw * 2, cy - sh * 2, cx + sw * 2, cy + sh * 2],
        fill=(*color, alpha // 4),
    )

    filtered = surf.filter(ImageFilter.GaussianBlur(6))
    if isinstance(target, Image.Image):
        return Image.alpha_composite(target.convert("RGBA"), filtered)
    return filtered


def render_vignette(
    target: Union[Tuple[int, int], Image.Image],
    intensity: float = 0.4,
    strength: Optional[float] = None,
) -> Image.Image:
    """
    Creates a smooth corner vignette to draw focus to the center.
    """
    w, h = target.size if isinstance(target, Image.Image) else target
    eff_strength = strength if strength is not None else intensity

    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(surf)

    # Dark border ellipse with inverse fill
    cx, cy = w // 2, h // 2
    rx, ry = int(w * 0.75), int(h * 0.75)
    max_alpha = int(255 * min(1.0, max(0.0, eff_strength)))

    draw.rectangle([0, 0, w, h], fill=(0, 0, 0, max_alpha))
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(0, 0, 0, 0))

    vig = surf.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.18)))

    if isinstance(target, Image.Image):
        return Image.alpha_composite(target.convert("RGBA"), vig)
    return vig


def apply_bloom(
    im: Image.Image,
    threshold: int = 210,
    blur_sigma: int = 14,
    intensity: float = 0.8,
) -> Image.Image:
    """
    Extracts high-luminance highlights, applies Gaussian blur, and screens back over original image.
    """
    from PIL import ImageChops
    orig_rgb = im.convert("RGB")
    gray = orig_rgb.convert("L")
    mask = gray.point(lambda p: 255 if p >= threshold else 0)

    bright_only = Image.new("RGB", orig_rgb.size, (0, 0, 0))
    bright_only.paste(orig_rgb, (0, 0), mask=mask)

    blurred_glow = bright_only.filter(ImageFilter.GaussianBlur(blur_sigma))
    screened = ImageChops.screen(orig_rgb, blurred_glow)

    if intensity < 1.0:
        return Image.blend(orig_rgb, screened, max(0.0, min(1.0, intensity)))
    return screened


def apply_film_grain(
    im: Image.Image,
    intensity: float = 0.08,
    seed: int = 42,
) -> Image.Image:
    """
    Simulates organic 35mm film grain texture using fast NumPy random noise.
    """
    if intensity <= 0.005:
        return im

    w, h = im.size
    rng = np.random.RandomState(seed)
    noise = rng.normal(loc=128, scale=35, size=(h, w)).astype(np.uint8)
    noise_img = Image.fromarray(noise, mode="L").convert("RGB")

    orig_rgb = im.convert("RGB")
    # Soft blend noise over image
    grain_blend = Image.blend(orig_rgb, noise_img, min(0.35, intensity))
    return grain_blend


def apply_radial_blur(
    im: Image.Image,
    center: Optional[Tuple[int, int]] = None,
    strength: float = 0.04,
    num_samples: int = 6,
) -> Image.Image:
    """
    Creates an explosive radial zoom blur shockwave radiating from center.
    """
    if strength <= 0.001:
        return im

    w, h = im.size
    cx, cy = center if center is not None else (w // 2, h // 2)
    orig_rgb = im.convert("RGB")
    accum = orig_rgb.copy()

    for i in range(1, num_samples + 1):
        scale = 1.0 + (strength * (i / num_samples))
        sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
        scaled = orig_rgb.resize((sw, sh), Image.Resampling.BILINEAR)

        # Crop to original bounds centered on cx, cy
        crop_x = max(0, int((sw - w) * (cx / w)))
        crop_y = max(0, int((sh - h) * (cy / h)))
        sample = scaled.crop((crop_x, crop_y, crop_x + w, crop_y + h))

        if sample.size == (w, h):
            accum = Image.blend(accum, sample, 1.0 / (i + 1))

    return accum


