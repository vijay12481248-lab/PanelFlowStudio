"""
Manual override models for PanelFlow Motion Director.
Allows human directors to tweak and lock individual shots while preserving downstream regeneration.
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from engine.motion.models.camera import NormalizedRect, CameraState
from engine.motion.models.enums import MotionType
from engine.motion.models.cues import FocusTarget
from engine.motion.models.transitions import TransitionInstruction


class ShotOverride(BaseModel):
    """
    User-directed manual overrides applied to an individual shot.
    """
    shot_id: str
    override_source_asset_id: Optional[str] = None
    override_duration: Optional[float] = None
    override_crop: Optional[NormalizedRect] = None
    override_camera_start: Optional[CameraState] = None
    override_camera_end: Optional[CameraState] = None
    override_motion_type: Optional[MotionType] = None
    override_focus_target: Optional[FocusTarget] = None
    override_transition_in: Optional[TransitionInstruction] = None
    override_transition_out: Optional[TransitionInstruction] = None
    locked: bool = True
    user_note: str = ""


class MotionOverrides(BaseModel):
    """
    Collection of active project-level motion overrides.
    """
    shot_overrides: Dict[str, ShotOverride] = Field(default_factory=dict)
    scene_overrides: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    def add_shot_override(self, override: ShotOverride):
        self.shot_overrides[override.shot_id] = override

    def get_shot_override(self, shot_id: str) -> Optional[ShotOverride]:
        return self.shot_overrides.get(shot_id)

    def is_shot_locked(self, shot_id: str) -> bool:
        ov = self.shot_overrides.get(shot_id)
        return bool(ov and ov.locked)
