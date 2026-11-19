"""Data models and schemas for video watermark detection and removal."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional, Tuple
from pydantic import BaseModel, Field


class WatermarkMode(str, Enum):
    AUTO = "auto"
    INVERSE_ALPHA = "inverse_alpha"
    FLOW_GUIDED = "flow_guided"


class WatermarkBoundingBox(BaseModel):
    x: int = Field(default=0, description="X coordinate of top-left corner")
    y: int = Field(default=0, description="Y coordinate of top-left corner")
    width: int = Field(gt=0, description="Width of bounding box")
    height: int = Field(gt=0, description="Height of bounding box")

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    def clamp(self, max_width: int, max_height: int) -> "WatermarkBoundingBox":
        x = max(0, min(self.x, max_width - 1))
        y = max(0, min(self.y, max_height - 1))
        w = max(1, min(self.width, max_width - x))
        h = max(1, min(self.height, max_height - y))
        return WatermarkBoundingBox(x=x, y=y, width=w, height=h)

    def expand(self, margin: int, max_width: int, max_height: int) -> "WatermarkBoundingBox":
        x = max(0, self.x - margin)
        y = max(0, self.y - margin)
        x2 = min(max_width, self.x + self.width + margin)
        y2 = min(max_height, self.y + self.height + margin)
        return WatermarkBoundingBox(x=x, y=y, width=x2 - x, height=y2 - y)


class DetectionCandidate(BaseModel):
    box: WatermarkBoundingBox
    confidence: float = Field(ge=0.0, le=1.0)
    detection_type: str = Field(description="'temporal_variance', 'ocr_text', or 'user_defined'")
    sample_frame_sec: float = 0.0
    label: Optional[str] = None


class WatermarkRemovalParams(BaseModel):
    video_path: str
    output_path: Optional[str] = None
    box: WatermarkBoundingBox
    mode: WatermarkMode = WatermarkMode.AUTO
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None
    feather_px: int = Field(default=3, ge=0, le=32)
    context_margin_px: int = Field(default=32, ge=0, le=128)
    alpha_estimate: Optional[float] = Field(default=None, ge=0.01, le=0.99)
    watermark_color: Optional[Tuple[int, int, int]] = None  # RGB
    use_gpu: bool = True


class WatermarkPreviewResult(BaseModel):
    original_frame_base64: str
    preview_frame_base64: str
    mask_frame_base64: str
    box: WatermarkBoundingBox
    mode_used: WatermarkMode
    time_sec: float
