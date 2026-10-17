import uuid
import logging
from pathlib import Path
from typing import Any
from PIL import Image

from engine.ocr.providers.base import OCREngine, RawOCRResult, OCRRegion, OCRProviderStatus

logger = logging.getLogger("panelflow.ocr.manga")

class MangaOCREngine(OCREngine):
    """
    Adapter for manga-ocr, providing state-of-the-art Japanese OCR for manga
    with robust handling of vertical text, varied fonts, and furigana.
    """

    def __init__(self):
        self._mocr = None
        self._initialized = False
        self._verified = False

    @property
    def engine_id(self) -> str:
        return "manga_ocr"

    @property
    def display_name(self) -> str:
        return "MangaOCR (Japanese)"

    @property
    def description(self) -> str:
        return "Specialized Japanese OCR for vertical/horizontal manga speech bubbles and furigana."

    def is_installed(self) -> bool:
        try:
            import manga_ocr  # noqa: F401
            return True
        except ImportError:
            return False

    def is_configured(self) -> bool:
        return self.is_installed()

    def is_available(self) -> bool:
        return self.is_installed() and self.is_configured()

    def is_verified(self) -> bool:
        return self._verified

    def set_verified(self, verified: bool = True) -> None:
        self._verified = verified

    def get_status(self) -> OCRProviderStatus:
        installed = self.is_installed()
        configured = self.is_configured()
        available = self.is_available()
        verified = self.is_verified()

        if verified:
            label = "Verified"
            msg = "MangaOCR active and verified on Japanese manga fixtures."
        elif available:
            label = "Available"
            msg = "MangaOCR installed and ready for execution."
        elif not installed:
            label = "Configuration required"
            msg = "Package 'manga-ocr' not installed. Install via: pip install manga-ocr"
        else:
            label = "Configuration required"
            msg = "MangaOCR model weights not downloaded or unconfigured."

        return OCRProviderStatus(
            provider_id=self.engine_id,
            display_name=self.display_name,
            description=self.description,
            registered=True,
            installed=installed,
            configured=configured,
            is_available=available,
            is_verified=verified,
            status_label=label,
            diagnostic_message=msg,
        )

    def _get_ocr(self):
        if not self._initialized:
            try:
                from manga_ocr import MangaOcr
                self._mocr = MangaOcr()
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize MangaOCR: {e}")
                raise RuntimeError(f"MangaOCR failed to initialize: {e}")
        return self._mocr

    def extract_text(
        self,
        image_path: Path,
        panel_id: str,
        language: str = "ja",
        extra_options: dict[str, Any] | None = None,
    ) -> RawOCRResult:
        if not self.is_available():
            raise RuntimeError("manga-ocr is not installed in the current environment.")

        mocr = self._get_ocr()
        with Image.open(image_path) as img:
            w, h = img.size
            text = mocr(img)

        regions: list[OCRRegion] = []
        if text and text.strip():
            regions.append(
                OCRRegion(
                    id=str(uuid.uuid4()),
                    panel_id=panel_id,
                    reading_order=1,
                    detected_text=text.strip(),
                    confidence=0.95,
                    bbox=[0, 0, w, h],
                    language="ja",
                )
            )

        return RawOCRResult(
            panel_id=panel_id,
            engine_id=self.engine_id,
            engine_version="manga-ocr-0.1",
            regions=regions,
            full_text=text.strip() if text else "",
            confidence_avg=0.95 if regions else 1.0,
        )
