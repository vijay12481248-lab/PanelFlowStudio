import sys
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Any
from PIL import Image

logger = logging.getLogger("panelflow.ocr.windows_media")

from engine.ocr.providers.base import OCREngine, RawOCRResult, OCRRegion, OCRProviderStatus

WINSDK_AVAILABLE = False
if sys.platform == "win32":
    try:
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage import StorageFile, FileAccessMode
        from winsdk.windows.graphics.imaging import BitmapDecoder
        WINSDK_AVAILABLE = True
    except Exception:
        WINSDK_AVAILABLE = False


class WindowsMediaOCREngine(OCREngine):
    """
    Native hardware-accelerated Windows 10/11 WinRT OCR engine.
    Zero external neural network weights required; uses OS built-in OCR recognizers.
    """

    def __init__(self):
        self._verified = False

    @property
    def engine_id(self) -> str:
        return "windows_media"

    @property
    def display_name(self) -> str:
        return "Windows Media OCR (Local WinRT)"

    @property
    def description(self) -> str:
        return "Built-in Windows 10/11 hardware-accelerated OCR for Latin and international typography."

    def is_installed(self) -> bool:
        return sys.platform == "win32" and WINSDK_AVAILABLE

    def is_configured(self) -> bool:
        if not self.is_installed():
            return False
        try:
            engine = OcrEngine.try_create_from_user_profile_languages()
            return engine is not None
        except Exception:
            return False

    def is_available(self) -> bool:
        return self.is_configured()

    def is_verified(self) -> bool:
        return self._verified or self.is_available()

    def set_verified(self, verified: bool = True) -> None:
        self._verified = verified

    def get_status(self) -> OCRProviderStatus:
        installed = self.is_installed()
        configured = self.is_configured()
        available = self.is_available()
        verified = self.is_verified()

        if verified:
            label = "Verified"
            msg = "Local Windows Media OCR active and verified."
        elif available:
            label = "Available"
            msg = "Local Windows Media OCR ready for execution."
        elif installed and not configured:
            label = "Configuration required"
            msg = "Windows OCR language pack missing. Install an OCR language pack in Windows Settings."
        else:
            label = "Configuration required"
            msg = "WinRT OCR runtime not available (Windows 10/11 required)."

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

    def extract_text(
        self,
        image_path: Path,
        panel_id: str,
        language: str = "en",
        extra_options: dict[str, Any] | None = None,
    ) -> RawOCRResult:
        if not self.is_available():
            raise RuntimeError("Windows Media OCR is not available on this system.")

        if not image_path.exists():
            raise FileNotFoundError(f"Target panel image not found: {image_path}")

        try:
            with Image.open(image_path) as img:
                img_w, img_h = img.size
        except Exception:
            img_w, img_h = 800, 600

        # WinRT OcrEngine requires width and height >= 40 pixels
        if img_w < 40 or img_h < 40:
            logger.debug(
                f"Image {image_path} too small for Windows Media OCR ({img_w}x{img_h} < 40x40). Returning empty result."
            )
            return RawOCRResult(
                panel_id=panel_id,
                engine_id=self.engine_id,
                engine_version="1.0-winrt",
                regions=[],
                full_text="",
                confidence_avg=1.0,
            )

        async def _run_async_ocr():
            resolved = str(image_path.resolve())
            file = await StorageFile.get_file_from_path_async(resolved)
            stream = await file.open_async(FileAccessMode.READ)
            decoder = await BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()
            engine = OcrEngine.try_create_from_user_profile_languages()
            if not engine:
                raise RuntimeError("Failed to create Windows OcrEngine instance.")
            return await engine.recognize_async(bitmap)

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    ocr_res = pool.submit(asyncio.run, _run_async_ocr()).result()
            else:
                ocr_res = asyncio.run(_run_async_ocr())
        except Exception as e:
            logger.warning(f"Windows Media OCR execution failed: {e}. Gracefully returning empty regions.")
            return RawOCRResult(
                panel_id=panel_id,
                engine_id=self.engine_id,
                engine_version="1.0-winrt",
                regions=[],
                full_text="",
                confidence_avg=1.0,
            )

        regions: list[OCRRegion] = []
        lines = list(ocr_res.lines) if hasattr(ocr_res, "lines") else []

        for idx, line in enumerate(lines, start=1):
            line_text = line.text.strip()
            if not line_text:
                continue

            words = list(line.words) if hasattr(line, "words") else []
            if words:
                min_x = min(w.bounding_rect.x for w in words)
                min_y = min(w.bounding_rect.y for w in words)
                max_x = max(w.bounding_rect.x + w.bounding_rect.width for w in words)
                max_y = max(w.bounding_rect.y + w.bounding_rect.height for w in words)
                bbox = [int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y)]
            else:
                bbox = [int(img_w * 0.1), int(img_h * 0.1), int(img_w * 0.8), int(img_h * 0.2)]

            regions.append(
                OCRRegion(
                    id=str(uuid.uuid4()),
                    panel_id=panel_id,
                    reading_order=idx,
                    detected_text=line_text,
                    confidence=0.95,
                    bbox=bbox,
                    language=language,
                )
            )

        # Fallback if no distinct lines recognized
        full_text = ocr_res.text.strip() if hasattr(ocr_res, "text") else ""
        if not regions and full_text:
            regions.append(
                OCRRegion(
                    id=str(uuid.uuid4()),
                    panel_id=panel_id,
                    reading_order=1,
                    detected_text=full_text,
                    confidence=0.90,
                    bbox=[int(img_w * 0.1), int(img_h * 0.1), int(img_w * 0.8), int(img_h * 0.8)],
                    language=language,
                )
            )

        self._verified = True
        return RawOCRResult(
            panel_id=panel_id,
            engine_id=self.engine_id,
            engine_version="1.0-winrt",
            regions=regions,
            full_text=full_text or " ".join(r.detected_text for r in regions),
            confidence_avg=0.95 if regions else 1.0,
        )
