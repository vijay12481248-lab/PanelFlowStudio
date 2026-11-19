"""Video watermark detection and non-blur removal package."""
from engine.video.watermark.models import (
    DetectionCandidate,
    WatermarkBoundingBox,
    WatermarkMode,
    WatermarkPreviewResult,
    WatermarkRemovalParams,
)
from engine.video.watermark.pipeline import (
    preview_watermark_removal,
    remove_video_watermark,
)
from engine.video.watermark.static_detector import detect_static_watermarks

__all__ = [
    "DetectionCandidate",
    "WatermarkBoundingBox",
    "WatermarkMode",
    "WatermarkPreviewResult",
    "WatermarkRemovalParams",
    "detect_static_watermarks",
    "preview_watermark_removal",
    "remove_video_watermark",
]
