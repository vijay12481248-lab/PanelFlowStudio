"""
Focus targets, captions, and annotations models for PanelFlow Motion Director.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid
from engine.motion.models.camera import NormalizedRect
from engine.motion.models.enums import FocusType


class FocusTarget(BaseModel):
    """
    Identifies the visual subject or region of interest for camera framing.
    """
    target_id: str = Field(default_factory=lambda: f"foc_{uuid.uuid4().hex[:8]}")
    focus_type: FocusType = FocusType.UNKNOWN
    character_id: Optional[str] = None
    speaker_id: Optional[str] = None
    bounding_box: Optional[NormalizedRect] = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    description: str = ""

    @classmethod
    def unknown(cls, desc: str = "Unknown focal area") -> "FocusTarget":
        return cls(focus_type=FocusType.UNKNOWN, bounding_box=None, confidence=0.0, description=desc)

    @classmethod
    def whole_panel(cls, desc: str = "Whole panel / environmental wide") -> "FocusTarget":
        return cls(
            focus_type=FocusType.ENVIRONMENT_WIDE,
            bounding_box=NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0),
            confidence=1.0,
            description=desc,
        )


class CaptionCue(BaseModel):
    """
    Presentation caption contract synchronised to speech intervals.
    """
    cue_id: str = Field(default_factory=lambda: f"cap_{uuid.uuid4().hex[:8]}")
    text: str
    speaker: Optional[str] = None
    speaker_character_id: Optional[str] = None
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    safe_region_hint: str = "BOTTOM_CENTER"  # BOTTOM_CENTER, TOP_CENTER, SUBTITLE_SAFE
    script_segment_id: Optional[str] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)


class AnnotationCue(BaseModel):
    """
    Extensible visual annotation or overlay cue (labels, callouts, highlights).
    """
    annotation_id: str = Field(default_factory=lambda: f"ann_{uuid.uuid4().hex[:8]}")
    annotation_type: str  # CHARACTER_LABEL, LOCATION_LABEL, OBJECT_HIGHLIGHT, CALLOUT, ARROW
    text: Optional[str] = None
    target_rect: Optional[NormalizedRect] = None
    start_time: float = Field(default=0.0, ge=0.0)
    end_time: float = Field(default=0.0, ge=0.0)
    style: Dict[str, Any] = Field(default_factory=dict)
