from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np

from engine.imaging.redaction import (
    ensure_backup,
    has_image_backup,
    restore_image_backup,
    blur_image_box,
    blur_entire_image,
)


def _create_sample_image(path: Path, width: int = 400, height: int = 300) -> Path:
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Draw high contrast shapes to test blurring
    draw.rectangle([50, 50, 150, 150], fill=(0, 0, 0))
    draw.rectangle([200, 50, 350, 120], fill=(255, 0, 0))
    draw.text((60, 60), "WATERMARK PROMO", fill=(255, 255, 255))
    img.save(path, format="PNG")
    return path


def test_backup_and_restore_cycle(tmp_path: Path):
    img_path = tmp_path / "panel_01.png"
    _create_sample_image(img_path)
    orig_bytes = img_path.read_bytes()

    assert not has_image_backup(img_path)

    # 1. Ensure backup
    backup_path = ensure_backup(img_path)
    assert backup_path.exists()
    assert has_image_backup(img_path)
    assert backup_path.read_bytes() == orig_bytes

    # 2. Modify image
    img_path.write_bytes(b"modified dummy content")
    assert img_path.read_bytes() != orig_bytes

    # 3. Restore image
    restored = restore_image_backup(img_path, delete_backup=True)
    assert restored is True
    assert img_path.read_bytes() == orig_bytes
    assert not has_image_backup(img_path)

    # Restoring again when no backup exists returns False
    assert restore_image_backup(img_path) is False


def test_blur_image_box_success(tmp_path: Path):
    img_path = tmp_path / "panel_blur.png"
    _create_sample_image(img_path)

    with Image.open(img_path) as im:
        orig_arr = np.array(im)

    # Blur the text / watermark box
    success = blur_image_box(img_path, x=50, y=50, width=100, height=100, blur_radius=12, feather=4)
    assert success is True
    assert has_image_backup(img_path)

    with Image.open(img_path) as im_blurred:
        blurred_arr = np.array(im_blurred)

    # Pixels inside the box should have changed significantly
    inside_orig = orig_arr[60:140, 60:140]
    inside_blur = blurred_arr[60:140, 60:140]
    assert not np.array_equal(inside_orig, inside_blur)

    # Pixels far outside the box should remain identical
    outside_orig = orig_arr[220:280, 220:280]
    outside_blur = blurred_arr[220:280, 220:280]
    assert np.array_equal(outside_orig, outside_blur)


def test_blur_image_box_boundary_clamping(tmp_path: Path):
    img_path = tmp_path / "panel_clamp.png"
    _create_sample_image(img_path, width=200, height=150)

    # Out of bounds coordinates should clamp safely without exception
    success = blur_image_box(img_path, x=-50, y=-50, width=500, height=500, blur_radius=8, feather=0)
    assert success is True


def test_blur_image_box_invalid_inputs(tmp_path: Path):
    nonexistent = tmp_path / "does_not_exist.png"
    assert blur_image_box(nonexistent, 10, 10, 50, 50) is False

    img_path = tmp_path / "valid.png"
    _create_sample_image(img_path)
    assert blur_image_box(img_path, 10, 10, 0, 50) is False
    assert blur_image_box(img_path, 10, 10, 50, -10) is False


def test_blur_entire_image(tmp_path: Path):
    img_path = tmp_path / "promo_panel.jpg"
    img = Image.new("RGB", (300, 300), color=(100, 150, 200))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 250, 250], fill=(255, 0, 0))
    img.save(img_path, format="JPEG")

    with Image.open(img_path) as im:
        orig_arr = np.array(im)

    success = blur_entire_image(img_path, blur_radius=20, backup=True)
    assert success is True
    assert has_image_backup(img_path)

    with Image.open(img_path) as im_blurred:
        blurred_arr = np.array(im_blurred)
        assert im_blurred.size == (300, 300)

    assert not np.array_equal(orig_arr, blurred_arr)
