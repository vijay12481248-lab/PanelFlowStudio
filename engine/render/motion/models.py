"""
Pydantic and data models for PanelFlow Studio Motion Graphics Subsystem.
"""

from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field


class MotionGraphicProps(BaseModel):
    """Configurable visual and textual parameters for a motion graphics scene."""
    headline: Optional[str] = None
    subtitle: Optional[str] = None
    badge_text: Optional[str] = None
    target_name: Optional[str] = None
    status: Optional[str] = None
    threat_level: Optional[str] = None
    facility: Optional[str] = None
    warning_text: Optional[str] = None
    telemetry: Optional[List[str]] = None
    metrics: Optional[List[Dict[str, Any]]] = None
    benchmarks: Optional[List[Dict[str, Any]]] = None
    kpis: Optional[List[Dict[str, Any]]] = None
    accent_color: Optional[Tuple[int, int, int]] = None
    secondary_color: Optional[Tuple[int, int, int]] = None
    aspect_ratio: str = Field(default="16:9", description="16:9 widescreen or 9:16 vertical shorts")
    extra_props: Dict[str, Any] = Field(default_factory=dict)


class MotionPresetDefinition(BaseModel):
    """Metadata and parameter schema for a registered motion preset."""
    id: str
    name: str
    description: str
    category: str  # e.g., "Keynote", "Cyberpunk", "Sci-Fi", "Enterprise", "Editorial", "Anime"
    default_duration: float = 6.0
    aspect_ratios: List[str] = Field(default_factory=lambda: ["16:9", "9:16"])
    default_props: Dict[str, Any] = Field(default_factory=dict)
    preview_description: str = ""


class MotionPreviewRequest(BaseModel):
    """Request payload to render a single preview frame."""
    preset_id: str
    timestamp: float = Field(default=2.0, ge=0.0)
    duration_sec: float = Field(default=6.0, gt=0.0)
    props: Optional[Dict[str, Any]] = None
    aspect_ratio: str = Field(default="16:9")
    width: int = Field(default=1280, ge=320, le=3840)
    height: int = Field(default=720, ge=240, le=2160)


class MotionPreviewResponse(BaseModel):
    """Response containing base64 rendered preview frame."""
    preset_id: str
    timestamp: float
    image_base64: str
    width: int
    height: int


class MotionRenderRequest(BaseModel):
    """Request payload to render a motion graphic video clip to disk."""
    preset_id: str
    duration_sec: float = Field(default=6.0, ge=1.0, le=120.0)
    props: Optional[Dict[str, Any]] = None
    fps: int = Field(default=30, ge=15, le=60)
    width: int = Field(default=1280, ge=640, le=3840)
    height: int = Field(default=720, ge=360, le=2160)
    output_filename: Optional[str] = None
    audio_file_path: Optional[str] = None


class MotionRenderResponse(BaseModel):
    """Response returned upon completion of motion render."""
    success: bool
    preset_id: str
    output_path: str
    duration_sec: float
    file_size_mb: float
    message: str = "Render completed successfully"
