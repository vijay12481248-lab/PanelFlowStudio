"""
Placeholder and tracking pixel detection for lazy-loaded reader images.
"""
import io
import re
from typing import Tuple, Optional
from PIL import Image

PLACEHOLDER_REGEX = re.compile(
    r"(placeholder|loading|spinner|blank|spacer|pixel|transparent|1x1|thumb_placeholder|lazy_default)",
    re.IGNORECASE,
)

KNOWN_TINY_GIF_HASHES = {
    # 1x1 transparent GIF
    "4bf6122e205973715c61304543452103f6f164b97fae7b9e691244e311f99b25",
}


def is_placeholder_candidate(
    url: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    image_bytes: Optional[bytes] = None,
    attributes: Optional[dict] = None,
) -> Tuple[bool, str]:
    """
    Evaluates whether an image candidate is a lazy-loading placeholder or tracking pixel.
    Returns (is_placeholder, reason).
    """
    # 1. URL pattern check
    if PLACEHOLDER_REGEX.search(url):
        return True, f"URL matches known placeholder pattern: {url}"

    # 2. Known attribute indicators
    if attributes:
        for attr, val in attributes.items():
            if attr.lower() in ("class", "data-class", "id") and PLACEHOLDER_REGEX.search(str(val)):
                return True, f"Element attribute '{attr}' indicates placeholder: {val}"

    # 3. Micro-dimensions check
    if width is not None and height is not None:
        if width <= 5 or height <= 5:
            return True, f"Micro-dimensions indicate tracking pixel or placeholder ({width}x{height})"
        # 1x1 pixel check
        if width == 1 and height == 1:
            return True, "1x1 pixel detected"

    # 4. Byte inspection
    if image_bytes:
        if len(image_bytes) < 120:
            return True, f"Extremely tiny payload ({len(image_bytes)} bytes) indicates dummy pixel"

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                w, h = img.size
                if w <= 5 or h <= 5:
                    return True, f"Decoded micro-dimensions ({w}x{h})"

                # Check if entire image is uniform single solid color (e.g. solid gray placeholder)
                if w <= 64 and h <= 64:
                    colors = img.getcolors(maxcolors=2)
                    if colors and len(colors) == 1:
                        return True, f"Single-color thumbnail placeholder ({w}x{h})"
        except Exception:
            pass

    return False, "Legitimate content candidate"
