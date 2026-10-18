"""
Image redaction and text blurring utilities for PanelFlow Studio.
Provides non-destructive Gaussian blurring over panels and text regions.
"""
from pathlib import Path
from typing import Optional, Tuple
import shutil
from PIL import Image, ImageDraw, ImageFilter


def get_backup_path(image_path: Path) -> Path:
    backup_dir = image_path.parent / ".originals"
    return backup_dir / image_path.name


def ensure_backup(image_path: Path) -> Path:
    backup_path = get_backup_path(image_path)
    if not backup_path.exists() and image_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, backup_path)
    return backup_path


def has_image_backup(image_path: Path) -> bool:
    return get_backup_path(image_path).exists()


def restore_image_backup(image_path: Path, delete_backup: bool = True) -> bool:
    backup_path = get_backup_path(image_path)
    if backup_path.exists():
        shutil.copy2(backup_path, image_path)
        if delete_backup:
            try:
                backup_path.unlink()
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

    with Image.open(image_path) as img:
        img_rgb = img.convert("RGB")
        w, h = img_rgb.size

        # Clamp box to image bounds
        x1 = max(0, min(x, w - 1))
        y1 = max(0, min(y, h - 1))
        x2 = max(x1 + 1, min(x + width, w))
        y2 = max(y1 + 1, min(y + height, h))

        box_w = x2 - x1
        box_h = y2 - y1

        if box_w <= 0 or box_h <= 0:
            return False

        # Extract region to blur
        region = img_rgb.crop((x1, y1, x2, y2))

        # Determine effective blur radius scaled to box size
        effective_radius = max(blur_radius, int(min(box_w, box_h) * 0.22))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=effective_radius))

        # Soft feathering mask for seamless border integration
        if feather > 0 and box_w > feather * 2 and box_h > feather * 2:
            feather_mask = Image.new("L", (box_w, box_h), 0)
            draw = ImageDraw.Draw(feather_mask)
            draw.rectangle(
                [feather, feather, box_w - feather, box_h - feather],
                fill=255,
            )
            feather_mask = feather_mask.filter(ImageFilter.GaussianBlur(radius=feather))
            img_rgb.paste(blurred, (x1, y1), feather_mask)
        else:
            img_rgb.paste(blurred, (x1, y1))

        # Save back in original format
        fmt = "JPEG" if image_path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
        img_rgb.save(image_path, format=fmt, quality=95)

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

    with Image.open(image_path) as img:
        img_rgb = img.convert("RGB")
        blurred = img_rgb.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        fmt = "JPEG" if image_path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
        blurred.save(image_path, format=fmt, quality=95)

    return True
