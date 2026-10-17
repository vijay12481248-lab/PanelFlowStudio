from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field
import uuid


class TextRegionType(str, Enum):
    SPEECH = "SPEECH"
    NARRATION = "NARRATION"
    THOUGHT = "THOUGHT"
    SFX = "SFX"
    CAPTION = "CAPTION"
    UNKNOWN = "UNKNOWN"


class TextRegionStatus(str, Enum):
    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    MANUAL = "MANUAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    IGNORED = "IGNORED"


class TextCorrectionStatus(str, Enum):
    UNEDITED = "UNEDITED"
    EDITED = "EDITED"
    VERIFIED = "VERIFIED"


class SpeakerAssignmentMethod(str, Enum):
    MANUAL = "MANUAL"
    RULE_BASED = "RULE_BASED"
    LLM_INFERRED = "LLM_INFERRED"


class TextRegionBox(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    page_id: str = ""
    panel_id: str = ""

    # Bounding box relative to panel crop
    x: int
    y: int
    width: int
    height: int
    normalized_x: float = 0.0
    normalized_y: float = 0.0
    normalized_width: float = 0.0
    normalized_height: float = 0.0

    # Bounding box relative to parent page
    page_x: int = 0
    page_y: int = 0
    page_width: int = 0
    page_height: int = 0

    region_type: str = TextRegionType.SPEECH.value
    confidence: float = 1.0
    sequence_in_panel: int = 1
    sequence_global: int = 1
    status: str = TextRegionStatus.DETECTED.value
    detection_method: str = "AUTO"  # AUTO, MANUAL, FALLBACK_PANEL

    crop_filename: str = ""
    crop_sha256: str = ""

    # Layer 1: Raw Machine OCR (Immutable)
    raw_text: str = ""
    raw_confidence: float = 0.0
    raw_polygon: list[list[int]] = Field(default_factory=list)
    ocr_engine: str = ""
    ocr_engine_version: str = ""

    # Layer 2: Corrected Text (Human Revision)
    corrected_text: str = ""
    corrected_by: str = ""
    correction_status: str = TextCorrectionStatus.UNEDITED.value

    # Layer 3: Speaker Attribution Preparation (Milestone 4 ready)
    speaker_character_id: str | None = None
    speaker_confidence: float | None = None
    speaker_assignment_method: str | None = None
