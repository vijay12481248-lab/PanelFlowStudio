from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel

class NormalizationConfig(BaseModel):
    target_width: int = 1920
    target_height: int | None = None
    color_space: str = "sRGB"
    auto_contrast: bool = False

class BasePageNormalizer(ABC):
    @abstractmethod
    def normalize_page(self, input_path: Path, output_path: Path, config: NormalizationConfig) -> dict:
        """Normalizes dimensions and color space of a page."""
        pass
