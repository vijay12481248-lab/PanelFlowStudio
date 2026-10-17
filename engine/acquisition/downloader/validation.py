import io
import hashlib
import re
from pathlib import Path
from PIL import Image
import numpy as np
import cv2

class ImageValidationError(Exception):
    """Raised when an image file fails structural or safety validation."""
    pass


MAGIC_NUMBERS = {
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "webp": [b"RIFF"],  # WebP starts with RIFF and has WEBP at bytes 8-12
    "bmp": [b"BM"],
}

HTML_SNIPPETS = (
    b"<!doctype html",
    b"<html",
    b"<head",
    b"<body",
    b"<title",
    b"404 not found",
    b"access denied",
    b"error 403",
    b"cloudflare",
)

def compute_sha256(data: bytes) -> str:
    """Computes hex SHA-256 digest of binary data."""
    return hashlib.sha256(data).hexdigest()

def sanitize_filename(filename: str, fallback_sequence: int = 1, default_ext: str = ".jpg") -> str:
    """
    Sanitizes a filename to prevent path traversal and illegal characters.
    """
    clean_name = Path(filename).name
    # Strip illegal characters
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', clean_name)
    if not clean_name or not clean_name.strip("._"):
        clean_name = f"page_{fallback_sequence:04d}{default_ext}"
    return clean_name

def validate_image_bytes(data: bytes, original_filename: str = "") -> dict:
    """
    Validates image bytes using magic number inspection, HTML detection,
    Pillow integrity check, and OpenCV raster verification.

    Returns dict with width, height, format, mime_type, and sha256.
    Raises ImageValidationError if invalid, corrupt, or an HTML error response.
    """
    if not data or len(data) == 0:
        raise ImageValidationError(f"Empty data received for {original_filename or 'image'}")

    # Check for HTML error response spoofed as image
    prefix_lower = data[:1024].lower()
    for snippet in HTML_SNIPPETS:
        if snippet in prefix_lower:
            raise ImageValidationError(
                f"File appears to be an HTML error page rather than an image ({snippet.decode('ascii', errors='ignore')})"
            )

    # Magic number check
    matched_type = None
    for img_type, magic_list in MAGIC_NUMBERS.items():
        for magic in magic_list:
            if data.startswith(magic):
                if img_type == "webp" and b"WEBP" not in data[8:16]:
                    continue
                matched_type = img_type
                break
        if matched_type:
            break

    if not matched_type:
        raise ImageValidationError(
            f"File header does not match known image formats (JPEG, PNG, WebP, BMP)"
        )

    # Pillow validation
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception as e:
        raise ImageValidationError(f"Pillow verification failed: {e}")

    # Re-open to read dimensions and format (verify() closes/invalidates the stream)
    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            img_format = (img.format or matched_type).upper()
            mode = img.mode
            if width <= 0 or height <= 0:
                raise ImageValidationError(f"Invalid image dimensions: {width}x{height}")
    except ImageValidationError:
        raise
    except Exception as e:
        raise ImageValidationError(f"Failed to read image dimensions: {e}")

    # OpenCV raster decode check
    try:
        np_arr = np.frombuffer(data, dtype=np.uint8)
        decoded = cv2.imdecode(np_arr, cv2.IMREAD_UNCHANGED)
        if decoded is None:
            raise ImageValidationError("OpenCV failed to decode raster matrix from image bytes")
    except ImageValidationError:
        raise
    except Exception as e:
        raise ImageValidationError(f"OpenCV decode failed: {e}")

    mime_map = {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
        "BMP": "image/bmp",
    }
    mime_type = mime_map.get(img_format, f"image/{matched_type.lower()}")

    return {
        "width": width,
        "height": height,
        "format": img_format,
        "mime_type": mime_type,
        "mode": mode,
        "sha256": compute_sha256(data),
        "byte_size": len(data),
    }

def rotate_image_file(image_path: Path, degrees: int) -> dict:
    """
    Rotates an image file in-place by 90, 180, or 270 degrees clockwise.
    Returns the new metadata (width, height, sha256, byte_size).
    """
    if degrees not in (90, 180, 270, -90, -180, -270):
        raise ValueError(f"Unsupported rotation degrees: {degrees}")

    # Normalize to clockwise degrees (90, 180, 270)
    norm_deg = degrees % 360
    pil_rot = {
        90: Image.ROTATE_270,   # PIL rotate(angle) is counter-clockwise, transpose is CW
        180: Image.ROTATE_180,
        270: Image.ROTATE_90,
    }

    with Image.open(image_path) as img:
        img_format = img.format or "JPEG"
        rotated = img.transpose(pil_rot[norm_deg])
        rotated.save(image_path, format=img_format)

    with open(image_path, "rb") as f:
        data = f.read()

    return validate_image_bytes(data, image_path.name)
