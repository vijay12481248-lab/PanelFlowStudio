import io

from PIL import Image, ImageDraw

from engine.imaging.redaction import blur_image_box, preview_blur_box


def test_preview_matches_applied_blur_without_mutation(tmp_path):
    directory = tmp_path / "panels"
    directory.mkdir()
    path = directory / "panel.jpg"
    image = Image.new("RGB", (200, 120), "white")
    draw = ImageDraw.Draw(image)
    for x in range(30, 170, 8):
        draw.rectangle((x, 20, x + 3, 90), fill="black")
    image.save(path, quality=95)
    original = path.read_bytes()
    with Image.open(path) as source:
        original_pixels = source.tobytes()
        preview = preview_blur_box(source, 25, 15, 150, 80)
        assert source.tobytes() == original_pixels
    assert path.read_bytes() == original
    assert not (directory / ".originals").exists()
    encoded = io.BytesIO()
    preview.save(encoded, format="JPEG", quality=95)
    assert blur_image_box(path, 25, 15, 150, 80)
    assert path.read_bytes() == encoded.getvalue()
    assert (directory / ".originals" / "panel.jpg").read_bytes() == original
