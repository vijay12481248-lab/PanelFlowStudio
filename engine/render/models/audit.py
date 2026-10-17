"""
Audit and quality report models for PanelFlow Production Renderer.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


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


class RenderAuditReport(BaseModel):
    """
    Complete pre- and post-render validation audit report.
    """
    is_valid: bool = True
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
    warnings: List[str] = Field(default_factory=list)
    contact_sheet_path: Optional[str] = None
