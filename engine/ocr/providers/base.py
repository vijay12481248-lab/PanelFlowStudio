from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

class OCRRegion(BaseModel):
    id: str = Field(..., description="Unique immutable region identifier")
    panel_id: str | None = Field(default=None, description="Associated panel identifier")
    reading_order: int = Field(default=1, description="Deterministic 1-based reading order")
    detected_text: str = Field(..., description="Raw text string recognized by OCR engine")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Recognition confidence score")
    bbox: list[int] = Field(..., description="[x, y, width, height] in pixel coordinates relative to panel/page")
    polygon: list[list[int]] | None = Field(default=None, description="Optional polygon contour coordinates [[x,y],...]")
    language: str = Field(default="en", description="Detected or requested language code")


class AdaptedTextBlock(BaseModel):
    id: str = Field(..., description="Adapted block identifier")
    raw_region_id: str = Field(..., description="Immutable pointer to raw OCRRegion id")
    speaker: str | None = Field(default=None, description="Assigned character speaker name")
    text: str = Field(..., description="Cleaned, translated, or human-corrected text")
    classification: str = Field(
        default="dialogue",
        description="Type: dialogue, narration, thought, sfx, caption"
    )
    notes: str = Field(default="", description="Adapter or director notes")


class RawOCRResult(BaseModel):
    panel_id: str
    engine_id: str
    engine_version: str = "1.0"
    regions: list[OCRRegion] = Field(default_factory=list)
    full_text: str = ""
    confidence_avg: float = 1.0


class OCRProviderStatus(BaseModel):
    provider_id: str
    display_name: str
    description: str
    registered: bool = True
    installed: bool = False
    configured: bool = False
    is_available: bool = False
    is_verified: bool = False
    status_label: str = "Configuration required"
    diagnostic_message: str = ""


class OCREngine(ABC):
    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Unique identifier of the OCR engine (e.g. 'mock_ocr', 'paddle_ocr', 'manga_ocr')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the OCR engine's strengths and target scripts."""
        pass

    def is_installed(self) -> bool:
        """Returns True if required native/python dependencies are installed."""
        return True

    def is_configured(self) -> bool:
        """Returns True if required models, weights, or server backends are present."""
        return self.is_available()

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if local binaries/libraries/models are available and callable."""
        pass

    def is_verified(self) -> bool:
        """Returns True if the engine successfully executed on real fixtures in this environment."""
        return False

    def get_status(self) -> OCRProviderStatus:
        installed = self.is_installed()
        configured = self.is_configured()
        available = self.is_available()
        verified = self.is_verified()

        if verified:
            label = "Verified"
        elif available:
            label = "Available"
        else:
            label = "Configuration required"

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
            diagnostic_message="" if available else "Configuration required before execution.",
        )

    @abstractmethod
    def extract_text(
        self,
        image_path: Path,
        panel_id: str,
        language: str = "en",
        extra_options: dict[str, Any] | None = None,
    ) -> RawOCRResult:
        """
        Extracts text regions immutably, preserving bounding boxes and confidence.
        Must never modify the source image.
        """
        pass

