"""
Unit tests for the Motion Graphics Preset Registry.
"""

import pytest
from engine.render.motion.registry import MotionRegistry
from engine.render.motion.models import MotionPresetDefinition


def test_list_presets():
    presets = MotionRegistry.list_presets()
    assert len(presets) >= 6
    preset_ids = [p.id for p in presets]
    assert "keynote_showcase" in preset_ids
    assert "cyber_hud" in preset_ids
    assert "scifi_containment" in preset_ids
    assert "corporate_benchmark" in preset_ids
    assert "kinetic_editorial" in preset_ids
    assert "anime_battle_hud" in preset_ids


def test_get_preset():
    preset = MotionRegistry.get_preset("keynote_showcase")
    assert preset is not None
    assert preset.name == "Apple Keynote Showcase"
    assert "16:9" in preset.aspect_ratios
    assert "9:16" in preset.aspect_ratios


def test_create_scene_widescreen_and_vertical():
    # 16:9 widescreen
    scene_16_9 = MotionRegistry.create_scene("keynote_showcase", aspect_ratio="16:9")
    frame_16_9 = scene_16_9.render_frame(1.5)
    assert frame_16_9.size == (1280, 720)

    # 9:16 vertical shorts
    scene_9_16 = MotionRegistry.create_scene("keynote_showcase", aspect_ratio="9:16")
    frame_9_16 = scene_9_16.render_frame(1.5)
    assert frame_9_16.size == (720, 1280)


def test_create_all_six_preset_scenes():
    for preset in MotionRegistry.list_presets():
        scene = MotionRegistry.create_scene(preset.id, bounds=(640, 360), duration_sec=3.0)
        frame = scene.render_frame(1.0)
        assert frame.size == (640, 360)
        assert frame.mode == "RGB"


def test_invalid_preset_raises():
    with pytest.raises(ValueError, match="Unknown motion preset ID"):
        MotionRegistry.create_scene("non_existent_preset")
