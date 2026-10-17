"""
Effect Director for generating bounded, renderer-neutral visual effects.
"""
from typing import Optional, Dict, Any
from engine.motion.models.effects import EffectInstruction, EffectBudget
from engine.motion.models.enums import EffectType


class EffectDirector:
    """
    Constructs deterministic effect instructions while enforcing safety budgets.
    """

    def __init__(self, budget: Optional[EffectBudget] = None):
        self.budget = budget or EffectBudget()

    def build_impact_shake(
        self,
        scene_id: str,
        start_time: float,
        duration: float = 0.35,
        intensity: float = 0.6,
    ) -> Optional[EffectInstruction]:
        if not self.budget.can_apply(EffectType.IMPACT_SHAKE, scene_id, start_time, duration):
            return None

        self.budget.record_usage(EffectType.IMPACT_SHAKE, scene_id, start_time)
        return EffectInstruction(
            effect_type=EffectType.IMPACT_SHAKE,
            start_time=start_time,
            end_time=start_time + duration,
            intensity=min(1.0, max(0.0, intensity)),
            parameters={"amplitude_px": round(intensity * 12.0, 1), "frequency_hz": 24.0},
        )

    def build_flash(
        self,
        scene_id: str,
        start_time: float,
        duration: float = 0.2,
        intensity: float = 0.5,
        color_hex: str = "#FFFFFF",
    ) -> Optional[EffectInstruction]:
        if not self.budget.can_apply(EffectType.FLASH, scene_id, start_time, duration):
            return None

        self.budget.record_usage(EffectType.FLASH, scene_id, start_time)
        return EffectInstruction(
            effect_type=EffectType.FLASH,
            start_time=start_time,
            end_time=start_time + duration,
            intensity=min(self.budget.max_flash_intensity, intensity),
            parameters={"color": color_hex},
        )

    def build_vignette(
        self,
        start_time: float,
        end_time: float,
        intensity: float = 0.4,
    ) -> EffectInstruction:
        return EffectInstruction(
            effect_type=EffectType.VIGNETTE,
            start_time=start_time,
            end_time=end_time,
            intensity=intensity,
            parameters={"radius": 0.75, "softness": 0.45},
        )
