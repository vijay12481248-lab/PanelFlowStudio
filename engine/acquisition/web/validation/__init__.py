"""
Validation package for web acquisition.
"""
from engine.acquisition.web.validation.ssrf_guard import is_safe_url
from engine.acquisition.web.validation.image_probe import (
    probe_image_bytes,
    detect_magic_bytes,
    ImageProbeResult,
)
from engine.acquisition.web.validation.placeholder_detector import is_placeholder_candidate
from engine.acquisition.web.validation.duplicate_detector import DuplicateDetector
from engine.acquisition.web.validation.completeness_validator import CompletenessValidator
from engine.acquisition.web.validation.chapter_validator import ChapterValidator

__all__ = [
    "is_safe_url",
    "probe_image_bytes",
    "detect_magic_bytes",
    "ImageProbeResult",
    "is_placeholder_candidate",
    "DuplicateDetector",
    "CompletenessValidator",
    "ChapterValidator",
]
