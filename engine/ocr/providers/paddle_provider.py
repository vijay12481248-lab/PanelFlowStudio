import uuid
import logging
from pathlib import Path
from typing import Any

from engine.ocr.providers.base import OCREngine, RawOCRResult, OCRRegion, OCRProviderStatus

logger = logging.getLogger("panelflow.ocr.paddle")

class PaddleOCREngine(OCREngine):
    """
    Adapter for PaddleOCR, providing high-accuracy multilingual OCR
    for English, Chinese, and European languages.
    """

    def __init__(self):
        self._ocr_instance = None
        self._initialized = False
        self._verified = False

    @property
    def engine_id(self) -> str:
        return "paddle_ocr"

    @property
    def display_name(self) -> str:
        return "PaddleOCR Multilingual"

    @property
    def description(self) -> str:
        return "Deep-learning text recognition supporting English, Chinese, and 80+ languages."

    def is_installed(self) -> bool:
        try:
            import paddleocr  # noqa: F401
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
            msg = "PaddleOCR active and verified on benchmark fixtures."
        elif available:
            label = "Available"
            msg = "PaddleOCR installed and ready for execution."
        elif not installed:
            label = "Configuration required"
            msg = "Package 'paddleocr' or 'paddlepaddle' not installed. Install via: pip install paddleocr"
        else:
            label = "Configuration required"
            msg = "PaddleOCR model weights not downloaded or unconfigured."

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

    def _get_ocr(self, language: str = "en"):
        if not self._initialized:
            try:
                from paddleocr import PaddleOCR
                lang_code = "ch" if language in ("zh", "chinese") else "en"
                self._ocr_instance = PaddleOCR(use_angle_cls=True, lang=lang_code, show_log=False)
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize PaddleOCR: {e}")
                raise RuntimeError(f"PaddleOCR failed to initialize: {e}")
        return self._ocr_instance

    def extract_text(
        self,
        image_path: Path,
        panel_id: str,
        language: str = "en",
        extra_options: dict[str, Any] | None = None,
    ) -> RawOCRResult:
        if not self.is_available():
            raise RuntimeError("PaddleOCR is not installed in the current environment.")

        ocr = self._get_ocr(language)
        result = ocr.ocr(str(image_path), cls=True)

        regions: list[OCRRegion] = []
        if result and len(result) > 0 and result[0]:
            for idx, line in enumerate(result[0], start=1):
                poly, (text, conf) = line
                # poly is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                xs = [int(pt[0]) for pt in poly]
                ys = [int(pt[1]) for pt in poly]
                min_x = min(xs)
                min_y = min(ys)
                width = max(xs) - min_x
                height = max(ys) - min_y

                regions.append(
                    OCRRegion(
                        id=str(uuid.uuid4()),
                        panel_id=panel_id,
                        reading_order=idx,
                        detected_text=text.strip(),
                        confidence=round(float(conf), 4),
                        bbox=[min_x, min_y, width, height],
                        polygon=[[int(pt[0]), int(pt[1])] for pt in poly],
                        language=language,
                    )
                )

        full_text = " ".join(r.detected_text for r in regions)
        avg_conf = sum(r.confidence for r in regions) / len(regions) if regions else 1.0

        return RawOCRResult(
            panel_id=panel_id,
            engine_id=self.engine_id,
            engine_version="paddleocr-2.x",
            regions=regions,
            full_text=full_text,
            confidence_avg=round(avg_conf, 3),
        )
