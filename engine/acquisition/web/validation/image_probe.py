"""
Image byte probing, magic bytes verification, format validation, and decompression-bomb safety.
"""
import hashlib
import io
from typing import Optional, Tuple
from pydantic import BaseModel
from PIL import Image

MAX_ALLOWED_PIXELS = 100_000_000  # 100 Megapixels safety guard against decompression bombs
MIN_IMAGE_BYTES = 64


class ImageProbeResult(BaseModel):
    is_valid: bool
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    byte_size: int = 0
    sha256: Optional[str] = None
    error: Optional[str] = None


def detect_magic_bytes(data: bytes) -> Optional[str]:
    """Detect image MIME type based on leading magic bytes."""
    if len(data) < 12:
        return None

    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "image/avif"

    return None


def probe_image_bytes(data: bytes, expected_mime: Optional[str] = None) -> ImageProbeResult:
    """
    Validates downloaded bytes as a legitimate, non-corrupt image.
    Guards against HTML error pages masquerading as images, broken files, and oversized decompression bombs.
    """
    byte_size = len(data)
    if byte_size < MIN_IMAGE_BYTES:
        return ImageProbeResult(
            is_valid=False,
            byte_size=byte_size,
            error=f"Payload too small to be a valid image ({byte_size} bytes)",
        )

    # Check for HTML masquerading as image
    prefix = data[:1024].lower()
    if (
        b"<html" in prefix
        or b"<!doctype html" in prefix
        or b"<body" in prefix
        or b"<title>access denied" in prefix
        or b"<title>403" in prefix
        or b"<title>404" in prefix
        or b"<title>just a moment" in prefix
    ):
        return ImageProbeResult(
            is_valid=False,
            byte_size=byte_size,
            error="HTML error or challenge page received instead of image binary",
        )

    # Check for JSON error masquerading as image
    if prefix.strip().startswith(b"{") and (b'"error"' in prefix or b'"message"' in prefix or b'"status"' in prefix):
        return ImageProbeResult(
            is_valid=False,
            byte_size=byte_size,
            error="JSON API error response received instead of image binary",
        )

    # Magic byte inspection
    detected_mime = detect_magic_bytes(data)
    if not detected_mime:
        return ImageProbeResult(
            is_valid=False,
            byte_size=byte_size,
            error="Unrecognized or corrupt image header (magic bytes mismatch)",
        )

    # SHA-256 calculation
    sha256_hash = hashlib.sha256(data).hexdigest()

    # Image decoding and dimension inspection
    try:
        # Enforce PIL decompression bomb limit
        Image.MAX_IMAGE_PIXELS = MAX_ALLOWED_PIXELS
        with Image.open(io.BytesIO(data)) as img:
            img.verify()

        # Re-open for size / mode info after verify()
        with Image.open(io.BytesIO(data)) as img:
            w, h = img.size
            if w <= 0 or h <= 0:
                return ImageProbeResult(
                    is_valid=False,
                    byte_size=byte_size,
                    sha256=sha256_hash,
                    error=f"Invalid image dimensions: {w}x{h}",
                )

            if (w * h) > MAX_ALLOWED_PIXELS:
                return ImageProbeResult(
                    is_valid=False,
                    byte_size=byte_size,
                    sha256=sha256_hash,
                    error=f"Image area {w*h} pixels exceeds safety decompression limit ({MAX_ALLOWED_PIXELS})",
                )

            aspect = round(float(w) / float(h), 4)

            return ImageProbeResult(
                is_valid=True,
                mime_type=detected_mime,
                width=w,
                height=h,
                aspect_ratio=aspect,
                byte_size=byte_size,
                sha256=sha256_hash,
            )

    except Image.DecompressionBombError as dbe:
        return ImageProbeResult(
            is_valid=False,
            byte_size=byte_size,
            sha256=sha256_hash,
            error=f"Decompression bomb detected: {dbe}",
        )
    except Exception as e:
        return ImageProbeResult(
            is_valid=False,
            byte_size=byte_size,
            sha256=sha256_hash,
            error=f"Corrupt image file or decoding failure: {e}",
        )
