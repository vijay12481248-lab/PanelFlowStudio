"""
Specular gradient shimmer effect for kinetic typography and presentation elements.
Emulates Apple Keynote and Stripe specular sweep animations.
"""

from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont


def render_shimmer_text(
    target_surf: Image.Image,
    text: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    base_color: Tuple[int, int, int] = (255, 255, 255),
    shimmer_color: Tuple[int, int, int] = (147, 197, 253),
    shimmer_progress: float = 0.0,
    band_width: int = 100,
    shimmer_phase: Optional[float] = None,
) -> Image.Image:
    """
    Renders text with a moving specular highlight gradient wave across target_surf.

    Args:
        target_surf: RGBA image to paste the shimmering text onto.
        text: String to render.
        x: X-coordinate for text.
        y: Y-coordinate for text.
        font: PIL ImageFont.
        base_color: RGB tuple for ambient text color.
        shimmer_color: RGB tuple for the specular highlight center.
        shimmer_progress: 0.0 to 1.0 representing wave traversal across the text.
        band_width: Width of the specular beam in pixels.
        shimmer_phase: Alias for shimmer_progress.

    Returns:
        target_surf with shimmering text composited.
    """
    prog = shimmer_progress if shimmer_phase is None else shimmer_phase
    w, h = target_surf.size

    # 1. Create a binary alpha mask of the text
    mask_img = Image.new("L", (w, h), 0)
    m_draw = ImageDraw.Draw(mask_img)
    m_draw.text((x, y), text, font=font, fill=255)

    bbox = m_draw.textbbox((x, y), text, font=font)
    text_w = max(1, bbox[2] - bbox[0])

    # 2. Gradient highlight surface
    grad_surf = Image.new("RGBA", (w, h), (*base_color, 255))
    g_draw = ImageDraw.Draw(grad_surf)

    # Shimmer sweep position
    shimmer_x = bbox[0] - band_width + int((text_w + 2 * band_width) * prog)

    for i in range(-band_width, band_width):
        factor = 1.0 - abs(i) / band_width
        gx = shimmer_x + i
        if 0 <= gx < w:
            col = tuple(
                int(base_color[c] + (shimmer_color[c] - base_color[c]) * factor)
                for c in range(3)
            )
            g_draw.line([(gx, bbox[1] - 4), (gx, bbox[3] + 4)], fill=(*col, 255), width=1)

    target_surf.paste(grad_surf, (0, 0), mask=mask_img)
    return target_surf
