from pathlib import Path
from PIL import Image
from engine.imaging.normalization.normalizer import PageNormalizer
from engine.imaging.normalization.base import NormalizationConfig

def test_page_normalizer_scaling(tmp_path: Path):
    normalizer = PageNormalizer()

    # Create a 800x1200 RGBA test image
    src_img = tmp_path / "raw_page.png"
    img = Image.new("RGBA", (800, 1200), (255, 0, 0, 200))
    img.save(src_img, "PNG")

    dest_img = tmp_path / "norm_page.jpg"
    config = NormalizationConfig(target_width=1920)

    result = normalizer.normalize_page(src_img, dest_img, config)

    assert dest_img.exists()
    assert result["width"] == 1920
    # Aspect ratio 800:1200 is 1:1.5 -> 1920 * 1.5 = 2880
    assert result["height"] == 2880
    assert result["scale_factor"] == 2.4
    assert result["byte_size"] > 0
    assert len(result["sha256"]) == 64

    # Verify saved format is RGB JPEG
    with Image.open(dest_img) as out_pil:
        assert out_pil.format == "JPEG"
        assert out_pil.mode == "RGB"

def test_page_normalizer_with_max_height(tmp_path: Path):
    normalizer = PageNormalizer()

    src_img = tmp_path / "tall_page.jpg"
    img = Image.new("RGB", (1000, 3000), "blue")
    img.save(src_img, "JPEG")

    dest_img = tmp_path / "clamped_page.jpg"
    # Target width 1920 but clamp height to 2000
    config = NormalizationConfig(target_width=1920, target_height=2000)

    result = normalizer.normalize_page(src_img, dest_img, config)
    assert result["height"] == 2000
    assert result["width"] == int(round(1000 * (2000 / 3000)))
