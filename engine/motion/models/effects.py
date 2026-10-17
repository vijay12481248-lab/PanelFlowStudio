"""
Effect instructions and safety budget models for PanelFlow Motion Director.
"""
from typing import Dict, Any, List
from pydantic import BaseModel, Field
import uuid
from engine.motion.models.enums import EffectType


class EffectInstruction(BaseModel):
    """
    Renderer-neutral effect instruction for visual impact, mood, and focus cues.
    """
    effect_id: str = Field(default_factory=lambda: f"eff_{uuid.uuid4().hex[:8]}")
    effect_type: EffectType
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)


class EffectBudget(BaseModel):
    """
    Enforces restraint on cinematic effects so they never become noisy or distracting.
    """
    max_effects_per_scene: int = 3
    min_shake_interval_sec: float = 4.0
    max_shake_duration_sec: float = 0.6
    max_flash_intensity: float = 0.8
    allow_flashes: bool = True
    enabled: bool = True

    # Runtime tracking
    _last_shake_time: float = -999.0
    _scene_effect_counts: Dict[str, int] = {}

    def can_apply(self, effect_type: EffectType, scene_id: str, start_time: float, requested_duration: float) -> bool:
        if not self.enabled:
            return False

        current_count = self._scene_effect_counts.get(scene_id, 0)
        if current_count >= self.max_effects_per_scene:
            return False

        if effect_type == EffectType.IMPACT_SHAKE:
            if start_time - self._last_shake_time < self.min_shake_interval_sec:
                return False
            if requested_duration > self.max_shake_duration_sec:
                return False

        if effect_type == EffectType.FLASH and not self.allow_flashes:
            return False

        return True

    def record_usage(self, effect_type: EffectType, scene_id: str, start_time: float):
        self._scene_effect_counts[scene_id] = self._scene_effect_counts.get(scene_id, 0) + 1
        if effect_type == EffectType.IMPACT_SHAKE:
            self._last_shake_time = start_time

    def reset_scene(self, scene_id: str):
        self._scene_effect_counts.pop(scene_id, None)

    def reset_all(self):
        self._scene_effect_counts.clear()
        self._last_shake_time = -999.0
