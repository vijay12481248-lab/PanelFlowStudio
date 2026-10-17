"""
Diagnostic and safety warning models for PanelFlow Motion Director.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid
from engine.motion.models.enums import WarningType, WarningSeverity


class MotionWarning(BaseModel):
    """
    Non-crashing diagnostic notification emitted during motion planning or validation.
    """
    warning_id: str = Field(default_factory=lambda: f"mwarn_{uuid.uuid4().hex[:8]}")
    warning_type: WarningType
    severity: WarningSeverity = WarningSeverity.WARNING
    message: str
    shot_id: Optional[str] = None
    scene_id: Optional[str] = None
    source_asset_id: Optional[str] = None
    timestamp_sec: Optional[float] = None
    context: Dict[str, Any] = Field(default_factory=dict)
