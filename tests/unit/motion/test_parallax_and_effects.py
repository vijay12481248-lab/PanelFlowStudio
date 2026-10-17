"""
Unit tests for ParallaxPlanner and EffectDirector in engine.motion.
"""
import pytest
from engine.motion.depth.parallax_planner import ParallaxPlanner
from engine.motion.effects.effect_director import EffectDirector
from engine.motion.models.effects import EffectBudget
from engine.motion.models.camera import CameraState
from engine.motion.models.enums import EffectType, LayerType, WarningType
from engine.motion.models.layers import LayerInstruction
from engine.motion.models.input_contract import VisualSource


def test_parallax_planner_flat_fallback():
    planner = ParallaxPlanner()
    visual = VisualSource(asset_id="v1", file_path="/dummy/flat.png", width=1920, height=1080)

    start = CameraState(center_x=0.5, center_y=0.5, zoom=1.0)
    end = CameraState(center_x=0.6, center_y=0.5, zoom=1.1)

    plan, warning = planner.plan_parallax(visual, start, end, existing_layers=None)

    assert plan.fallback_flat is True
    assert plan.enabled is False
    assert len(plan.layers) == 1
    assert warning is not None
    assert warning.warning_type == WarningType.PARALLAX_UNAVAILABLE


def test_parallax_planner_differential_layers():
    planner = ParallaxPlanner()
    visual = VisualSource(asset_id="v1", file_path="/dummy/layered.png", width=1920, height=1080)

    start = CameraState(center_x=0.4, center_y=0.5, zoom=1.0)
    end = CameraState(center_x=0.6, center_y=0.5, zoom=1.0)

    input_layers = [
        LayerInstruction(layer_id="l_bg", layer_type=LayerType.BACKGROUND, source_uri="/bg.png", depth=0.1),
        LayerInstruction(layer_id="l_char", layer_type=LayerType.CHARACTER, source_uri="/char.png", depth=0.5),
        LayerInstruction(layer_id="l_fg", layer_type=LayerType.FOREGROUND, source_uri="/fg.png", depth=0.9),
    ]

    plan, warning = planner.plan_parallax(visual, start, end, parallax_strength=0.5, existing_layers=input_layers)

    assert plan.fallback_flat is False
    assert plan.enabled is True
    assert len(plan.layers) == 3
    assert warning is None

    # Foreground should move faster than background
    fg_layer = [lay for lay in plan.layers if lay.layer_type == LayerType.FOREGROUND][0]
    bg_layer = [lay for lay in plan.layers if lay.layer_type == LayerType.BACKGROUND][0]
    assert fg_layer.motion_factor > bg_layer.motion_factor


def test_effect_director_budget_enforcement():
    budget = EffectBudget(max_effects_per_scene=2, min_shake_interval_sec=4.0, max_shake_duration_sec=0.5)
    director = EffectDirector(budget=budget)

    # Shake 1 at t=1.0s, dur=0.3s -> allowed
    eff1 = director.build_impact_shake("sc_1", start_time=1.0, duration=0.3, intensity=0.5)
    assert eff1 is not None
    assert eff1.effect_type == EffectType.IMPACT_SHAKE

    # Shake 2 at t=2.0s -> blocked because interval is only 1.0s (less than min 4.0s)
    eff2 = director.build_impact_shake("sc_1", start_time=2.0, duration=0.3, intensity=0.5)
    assert eff2 is None

    # Flash at t=2.5s -> allowed (scene count reaches 2)
    eff3 = director.build_flash("sc_1", start_time=2.5, duration=0.2, intensity=0.4)
    assert eff3 is not None
    assert eff3.effect_type == EffectType.FLASH

    # Any 3rd effect at t=6.0s -> blocked by max_effects_per_scene (2)
    eff4 = director.build_impact_shake("sc_1", start_time=6.0, duration=0.3, intensity=0.5)
    assert eff4 is None
