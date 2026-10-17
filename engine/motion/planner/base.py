from enum import Enum
from pydantic import BaseModel, Field

class MotionCameraAction(str, Enum):
    SLOW_ZOOM_IN = "slow_zoom_in"
    SLOW_ZOOM_OUT = "slow_zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"
    FACE_FOCUS = "face_focus"
    CHARACTER_FOCUS = "character_focus"
    PARALLAX = "parallax"
    IMPACT_SHAKE = "impact_shake"
    FLASH = "flash"
    PARTICLES = "particles"
    DIALOGUE_FOCUS = "dialogue_focus"
    CROSSFADE = "crossfade"
    FADE_BLACK = "fade_black"

class ShotBeat(BaseModel):
    id: str
    panel_id: str
    action: MotionCameraAction
    duration_seconds: float
    intensity: float = 1.0
    start_crop: list[int] | None = None
    end_crop: list[int] | None = None
    easing: str = "ease_in_out"

class ShotPlan(BaseModel):
    project_id: str
    version: str = "1.0"
    target_width: int = 1920
    target_height: int = 1080
    fps: int = 30
    beats: list[ShotBeat] = Field(default_factory=list)
