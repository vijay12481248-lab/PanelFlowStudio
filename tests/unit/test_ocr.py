import tempfile
from pathlib import Path
from PIL import Image

from engine.ocr.providers.mock_engine import MockOCREngine
from engine.ocr.providers.paddle_provider import PaddleOCREngine
from engine.ocr.providers.manga_ocr_provider import MangaOCREngine
from engine.ocr.providers.vision_llm_provider import VisionLLMOCREngine
from engine.ocr.providers.registry import OCRRegistry, get_default_ocr_registry
from engine.ocr.providers.base import OCRRegion, AdaptedTextBlock

def test_mock_ocr_engine_extraction():
    with tempfile.TemporaryDirectory() as tmp_dir:
        img_path = Path(tmp_dir) / "test_panel.jpg"
        img = Image.new("RGB", (600, 800), color=(255, 255, 255))
        img.save(img_path, "JPEG")

        engine = MockOCREngine()
        assert engine.is_available() is True
        assert engine.engine_id == "mock_ocr"

        result = engine.extract_text(img_path, panel_id="panel_123", language="en")
        assert result.panel_id == "panel_123"
        assert result.engine_id == "mock_ocr"
        assert len(result.regions) >= 1
        assert result.confidence_avg > 0.8
        assert "MEANWHILE" in result.full_text

        # Bounding box validity
        for region in result.regions:
            x, y, w, h = region.bbox
            assert x >= 0 and y >= 0
            assert w > 0 and h > 0
            assert region.confidence >= 0.0 and region.confidence <= 1.0

def test_ocr_registry_discovery():
    reg = get_default_ocr_registry()
    engines = reg.list_engines()
    ids = [e["engine_id"] for e in engines]
    assert "mock_ocr" in ids
    assert "paddle_ocr" in ids
    assert "manga_ocr" in ids
    assert "vision_llm" in ids

    # Default engine should fall back to mock_ocr if paddle is unavailable
    default_eng = reg.get_default_engine()
    assert default_eng.is_available() is True

def test_adapted_text_block_non_destructive_referencing():
    raw_region = OCRRegion(
        id="raw_uuid_001",
        reading_order=1,
        detected_text="I CANT BELIEVE WE SURVIVED THAT!",
        confidence=0.94,
        bbox=[50, 40, 200, 80],
        language="en",
    )

    adapted = AdaptedTextBlock(
        id="adapted_001",
        raw_region_id=raw_region.id,
        speaker="Captain Cosmos",
        text="I can't believe we survived that!",
        classification="dialogue",
        notes="Cleaned up capitalization",
    )

    # Immutability check: raw_region remains untouched
    assert adapted.raw_region_id == raw_region.id
    assert raw_region.detected_text == "I CANT BELIEVE WE SURVIVED THAT!"
    assert adapted.text == "I can't believe we survived that!"
    assert adapted.speaker == "Captain Cosmos"
