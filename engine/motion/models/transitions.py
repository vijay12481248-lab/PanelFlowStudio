"""
Transition models for PanelFlow Motion Director.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid
from engine.motion.models.enums import TransitionType, EasingFunction


class TransitionInstruction(BaseModel):
    """
    Renderer-neutral transition instruction between adjacent shots or scenes.
    """
    transition_id: str = Field(default_factory=lambda: f"trans_{uuid.uuid4().hex[:8]}")
    transition_type: TransitionType = TransitionType.CUT
    duration_sec: float = Field(default=0.0, ge=0.0)
    easing: EasingFunction = EasingFunction.EASE_IN_OUT
    color_hex: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def hard_cut(cls) -> "TransitionInstruction":
        return cls(transition_type=TransitionType.CUT, duration_sec=0.0)

    @classmethod
    def dissolve(cls, duration_sec: float = 0.5) -> "TransitionInstruction":
        return cls(transition_type=TransitionType.CROSS_DISSOLVE, duration_sec=duration_sec)

    @classmethod
    def fade_black(cls, duration_sec: float = 0.6) -> "TransitionInstruction":
        return cls(transition_type=TransitionType.FADE_OUT, duration_sec=duration_sec, color_hex="#000000")

    @classmethod
    def match_hold(cls) -> "TransitionInstruction":
        return cls(transition_type=TransitionType.MATCH_HOLD, duration_sec=0.0)
