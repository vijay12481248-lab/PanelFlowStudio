import sys
from typing import Dict, List
from engine.ocr.providers.base import OCREngine
from engine.ocr.providers.mock_engine import MockOCREngine
from engine.ocr.providers.paddle_provider import PaddleOCREngine
from engine.ocr.providers.manga_ocr_provider import MangaOCREngine
from engine.ocr.providers.vision_llm_provider import VisionLLMOCREngine
from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine

class OCRRegistry:
    """Registry of pluggable OCR providers conforming to OCREngine interface."""

    def __init__(self):
        self._engines: Dict[str, OCREngine] = {}

    def register(self, engine: OCREngine) -> None:
        self._engines[engine.engine_id] = engine

    def get_engine(self, engine_id: str) -> OCREngine:
        if engine_id not in self._engines:
            raise KeyError(f"OCR engine '{engine_id}' not found in registry.")
        return self._engines[engine_id]

    def list_engines(self) -> List[dict]:
        results = []
        for eng_id, eng in self._engines.items():
            status = eng.get_status().model_dump()
            status["engine_id"] = eng_id
            results.append(status)
        return results

    def get_default_engine(self) -> OCREngine:
        # Check for native hardware-accelerated Windows Media OCR first on Windows
        if "windows_media" in self._engines and self._engines["windows_media"].is_available():
            return self._engines["windows_media"]
        # Check for PaddleOCR if available
        if "paddle_ocr" in self._engines and self._engines["paddle_ocr"].is_available():
            return self._engines["paddle_ocr"]
        # Fallback to Mock / built-in OCR
        return self._engines.get("mock_ocr", list(self._engines.values())[0])

def get_default_ocr_registry() -> OCRRegistry:
    registry = OCRRegistry()
    registry.register(MockOCREngine())
    if sys.platform == "win32":
        try:
            registry.register(WindowsMediaOCREngine())
        except Exception:
            pass
    registry.register(PaddleOCREngine())
    registry.register(MangaOCREngine())
    registry.register(VisionLLMOCREngine())
    return registry


ocr_registry = get_default_ocr_registry()

