"""
Audit and quality report models for PanelFlow Production Renderer.
Includes technical stream checks and semantic storytelling quality gates.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ProductionGateStatus(str, Enum):
    TECHNICALLY_VALID = "TECHNICALLY_VALID"
    STORY_VALIDATED = "STORY_VALIDATED"
    VISUALLY_VALIDATED = "VISUALLY_VALIDATED"
    AUDIO_VALIDATED = "AUDIO_VALIDATED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    PRODUCTION_READY = "PRODUCTION_READY"
    FAILED_SEMANTIC_QA = "FAILED_SEMANTIC_QA"


class FrameSampleAudit(BaseModel):
    """
    Quality metrics sampled at key milestones across the rendered video (0%, 25%, 50%, 75%, 100%).
    """
    timestamp_sec: float
    frame_index: int
    is_black: bool = False
    mean_luminance: float = 0.0
    caption_rendered: bool = False
    source_visible: bool = True
    active_shot_id: Optional[str] = None
    sample_image_path: Optional[str] = None


class SemanticQualityReport(BaseModel):
    """
    Evaluates storytelling, narrative pacing, caption readability,
    non-story contamination, and proper-noun consistency.
    """
    story_event_coverage_pct: float = 100.0
    visual_panel_coverage_pct: float = 100.0
    max_caption_wpm: float = 0.0
    consecutive_duplicate_captions: int = 0
    max_shot_duration_sec: float = 0.0
    max_static_hold_duration_sec: float = 0.0
    non_story_contamination_count: int = 0
    proper_noun_consistency: bool = True
    tts_transcript_agreement_pct: float = 95.0
    gate_status: ProductionGateStatus = ProductionGateStatus.TECHNICALLY_VALID
    failed_checks: List[str] = Field(default_factory=list)


class RenderAuditReport(BaseModel):
    """
    Complete pre- and post-render validation audit report.
    """
    is_valid: bool = True
    gate_status: str = "TECHNICALLY_VALID"
    output_mp4_path: str = ""
    file_size_bytes: int = 0
    planned_duration_sec: float = 0.0
    actual_duration_sec: float = 0.0
    duration_diff_sec: float = 0.0
    ffprobe_meta: Dict[str, Any] = Field(default_factory=dict)
    frame_samples: List[FrameSampleAudit] = Field(default_factory=list)
    quality_flags: Dict[str, int] = Field(
        default_factory=lambda: {
            "black_frames": 0,
            "duplicate_consecutive_frames": 0,
            "camera_bound_violations": 0,
            "timeline_gaps": 0,
            "unsupported_effects": 0,
            "missing_captions": 0,
            "audio_clipping_events": 0,
            "av_sync_offset_ms": 0,
            "missing_assets": 0,
        }
    )
    semantic_qa: Optional[SemanticQualityReport] = None
    warnings: List[str] = Field(default_factory=list)
    contact_sheet_path: Optional[str] = None
