import pytest

from engine.ocr.providers.mock_engine import MockOCREngine
from engine.ocr.providers.registry import OCRRegistry


def test_unnamed_engine_never_silently_resolves_to_mock_text():
    registry = OCRRegistry()
    registry.register(MockOCREngine())
    with pytest.raises(ValueError, match="No real OCR engine"):
        registry.resolve(None)
    # Mock stays available when a caller asks for it by name (tests, demos).
    assert registry.resolve("mock_ocr").engine_id == "mock_ocr"
