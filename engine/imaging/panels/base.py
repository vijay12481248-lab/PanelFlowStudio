from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field

class DetectionProfile(str, Enum):
    AUTO = "AUTO"
    MANGA_PAGE = "MANGA_PAGE"
    WESTERN_COMIC = "WESTERN_COMIC"
    WEBTOON = "WEBTOON"
    SIMPLE_GRID = "SIMPLE_GRID"

class ReadingDirection(str, Enum):
    LTR = "ltr"
    RTL = "rtl"
    VERTICAL = "vertical"
    AUTO = "auto"
    CUSTOM = "custom"

class PanelType(str, Enum):
    STANDARD = "STANDARD"
    FULL_PAGE = "FULL_PAGE"
    INSET = "INSET"
    OVERLAPPING = "OVERLAPPING"
    BORDERLESS = "BORDERLESS"
    SPLASH = "SPLASH"
    WEBTOON_SEGMENT = "WEBTOON_SEGMENT"
    UNKNOWN = "UNKNOWN"

class PanelStatus(str, Enum):
    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    IGNORED = "IGNORED"
    MANUAL = "MANUAL"

class PanelBox(BaseModel):
    id: str
    page_id: str
    sequence: int = 1
    page_sequence: int = 1
    x: int
    y: int
    width: int
    height: int
    normalized_x: float = 0.0
    normalized_y: float = 0.0
    normalized_width: float = 0.0
    normalized_height: float = 0.0
    polygon_json: str | None = None
    confidence: float = 1.0
    panel_type: str = PanelType.STANDARD.value
    status: str = PanelStatus.DETECTED.value
    detection_method: str = "AUTO"
    manually_modified: bool = False

class BasePanelDetector(ABC):
    @abstractmethod
    def detect_panels(
        self,
        page_image_path: Path | str,
        reading_direction: str = "ltr",
        page_id: str = "",
        profile: str = "AUTO",
    ) -> list[PanelBox]:
        """Detects panel bounding boxes in reading sequence."""
        pass

    @abstractmethod
    def extract_crop(
        self,
        source_image_path: Path | str,
        panel_box: PanelBox,
        target_path: Path | str,
    ) -> dict:
        """Extracts and saves a high-quality panel crop."""
        pass
