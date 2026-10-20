"""
Image redaction and text blurring utilities for PanelFlow Studio.
Provides non-destructive Gaussian blurring over panels and text regions.
"""
from pathlib import Path
from typing import Optional, Tuple
import shutil
import io
from PIL import Image, ImageDraw, ImageFilter


def get_backup_path(image_path: Path) -> Path:
    backup_dir = image_path.parent / ".originals"
    return backup_dir / image_path.name


def ensure_backup(image_path: Path) -> Path:
    backup_path = get_backup_path(image_path)
    if not backup_path.exists() and image_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        from engine.security.paths import read_contained_bytes, open_contained_output
        original = read_contained_bytes(image_path.parent.parent, image_path)
        with open_contained_output(image_path.parent.parent, backup_path, exclusive=True) as output:
            output.write(original)
    return backup_path


def has_image_backup(image_path: Path) -> bool:
    return get_backup_path(image_path).exists()


def preview_blur_box(image: Image.Image, x: int, y: int, width: int, height: int,
                     blur_radius: int = 24, feather: int = 4) -> Image.Image:
    """Shared in-memory blur used for previews and committed cleanup."""
    result = image.convert("RGB").copy()
    w, h = result.size
    x1, y1 = max(0, min(x, w - 1)), max(0, min(y, h - 1))
    x2, y2 = max(x1 + 1, min(x + width, w)), max(y1 + 1, min(y + height, h))
    bw, bh = x2 - x1, y2 - y1
    region = result.crop((x1, y1, x2, y2))
    blurred = region.filter(ImageFilter.GaussianBlur(radius=max(blur_radius, int(min(bw, bh) * 0.22))))
    if feather > 0 and bw > feather * 2 and bh > feather * 2:
        mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mask).rectangle([feather, feather, bw - feather, bh - feather], fill=255)
        result.paste(blurred, (x1, y1), mask.filter(ImageFilter.GaussianBlur(radius=feather)))
    else:
        result.paste(blurred, (x1, y1))
    return result


def restore_image_backup(image_path: Path, delete_backup: bool = True) -> bool:
    backup_path = get_backup_path(image_path)
    if backup_path.exists():
        from engine.security.paths import read_contained_bytes, open_contained_output, unlink_contained_file
        original = read_contained_bytes(image_path.parent.parent, backup_path)
        with open_contained_output(image_path.parent.parent, image_path) as output:
            output.write(original)
        if delete_backup:
            try:
                unlink_contained_file(image_path.parent.parent, backup_path)
            except OSError:
                pass
        return True
    return False


def blur_image_box(
    image_path: Path,
    x: int,
    y: int,
    width: int,
    height: int,
    blur_radius: int = 24,
    feather: int = 4,
    backup: bool = True,
) -> bool:
    """
    Applies a smooth Gaussian blur over a rectangular box in the image.
    Backs up the original image before first modification.
    """
    if not image_path.exists() or width <= 0 or height <= 0:
        return False

    if backup:
        ensure_backup(image_path)

    from engine.security.paths import read_contained_bytes
    with Image.open(io.BytesIO(read_contained_bytes(image_path.parent.parent, image_path))) as img:
        # Use the same implementation as the non-mutating preview.
        img_rgb = preview_blur_box(img, x, y, width, height, blur_radius, feather)
        # Save back in original format
        fmt = "JPEG" if image_path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
        buffer = io.BytesIO()
        img_rgb.save(buffer, format=fmt, quality=95)
        from engine.security.paths import open_contained_output
        with open_contained_output(image_path.parent.parent, image_path) as output:
            output.write(buffer.getvalue())

    return True


def blur_entire_image(
    image_path: Path,
    blur_radius: int = 32,
    backup: bool = True,
) -> bool:
    """
    Applies Gaussian blur to the entire image.
    """
    if not image_path.exists():
        return False

    if backup:
        ensure_backup(image_path)

    from engine.security.paths import read_contained_bytes
    with Image.open(io.BytesIO(read_contained_bytes(image_path.parent.parent, image_path))) as img:
        img_rgb = img.convert("RGB")
        blurred = img_rgb.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        fmt = "JPEG" if image_path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
        buffer = io.BytesIO()
        blurred.save(buffer, format=fmt, quality=95)
        from engine.security.paths import open_contained_output
        with open_contained_output(image_path.parent.parent, image_path) as output:
            output.write(buffer.getvalue())

    return True
