"""
Unit tests for the Cinema Universe motion graphics presets:
- MatrixDigitalRainScene
- SynthwaveSunsetScene
- LuxuryGoldMonogramScene
- CosmicNebulaWarpScene
"""

import pytest
from PIL import Image
from engine.render.motion.registry import MotionRegistry
from engine.render.motion.presentation.cinema_templates import (
    MatrixDigitalRainScene,
    SynthwaveSunsetScene,
    LuxuryGoldMonogramScene,
    CosmicNebulaWarpScene,
)


def test_matrix_digital_rain_scene():
    scene = MatrixDigitalRainScene(
        headline="ACCESS GRANTED",
        subtitle="Initializing neural kernel",
        bounds=(640, 360),
        duration_sec=4.0,
    )
    frame_early = scene.render_frame(0.4)
    frame_mid = scene.render_frame(2.0)
    assert frame_early.size == (640, 360)
    assert frame_early.mode == "RGB"
    assert frame_mid.size == (640, 360)


def test_synthwave_sunset_scene():
    scene = SynthwaveSunsetScene(
        headline="OUTRUN 84",
        subtitle="Neon Horizon",
        bounds=(640, 360),
        duration_sec=4.0,
    )
    frame = scene.render_frame(1.5)
    assert frame.size == (640, 360)
    assert frame.mode == "RGB"


def test_luxury_gold_monogram_scene():
    scene = LuxuryGoldMonogramScene(
        headline="AURELIA",
        subtitle="Cinematic Grand Prix",
        bounds=(640, 360),
        duration_sec=4.0,
    )
    frame = scene.render_frame(1.8)
    assert frame.size == (640, 360)
    assert frame.mode == "RGB"


def test_cosmic_nebula_warp_scene():
    scene = CosmicNebulaWarpScene(
        headline="WARP 9.9",
        subtitle="Hyperspace Jump Active",
        bounds=(640, 360),
        duration_sec=4.0,
    )
    frame_glitch = scene.render_frame(0.3)
    frame_stable = scene.render_frame(2.5)
    assert frame_glitch.size == (640, 360)
    assert frame_stable.size == (640, 360)


def test_cinema_presets_via_registry():
    cinema_ids = ["matrix_rain", "synthwave_sunset", "luxury_gold", "cosmic_warp"]
    for cid in cinema_ids:
        preset_def = MotionRegistry.get_preset(cid)
        assert preset_def is not None
        assert preset_def.id == cid

        # Verify 16:9 and 9:16 vertical render
        scene_16_9 = MotionRegistry.create_scene(cid, bounds=(640, 360))
        assert scene_16_9.render_frame(1.0).size == (640, 360)

        scene_9_16 = MotionRegistry.create_scene(cid, aspect_ratio="9:16", bounds=(360, 640))
        assert scene_9_16.render_frame(1.0).size == (360, 640)
