"""
Unit tests for procedural motion graphics transition shaders.
"""

import pytest
from PIL import Image
from engine.render.motion.transitions.shaders import (
    render_whip_pan_glitch,
    render_light_leak_burn,
    render_geometric_slice_wipe,
)
from engine.render.motion.effects.lighting import apply_film_grain, apply_radial_blur


@pytest.fixture
def test_frames():
    img_a = Image.new("RGB", (320, 240), (220, 38, 38))  # Red
    img_b = Image.new("RGB", (320, 240), (37, 99, 235))  # Blue
    return img_a, img_b


def test_whip_pan_glitch(test_frames):
    img_a, img_b = test_frames
    for p in [0.0, 0.5, 1.0]:
        res = render_whip_pan_glitch(img_a, img_b, progress=p)
        assert res.size == (320, 240)
        assert res.mode == "RGB"


def test_light_leak_burn(test_frames):
    img_a, img_b = test_frames
    for p in [0.0, 0.5, 1.0]:
        res = render_light_leak_burn(img_a, img_b, progress=p)
        assert res.size == (320, 240)
        assert res.mode == "RGB"


def test_geometric_slice_wipe(test_frames):
    img_a, img_b = test_frames
    for p in [0.0, 0.5, 1.0]:
        res = render_geometric_slice_wipe(img_a, img_b, progress=p, num_slices=6)
        assert res.size == (320, 240)
        assert res.mode == "RGB"


def test_film_grain_and_radial_blur():
    img = Image.new("RGB", (200, 200), (80, 80, 90))
    grained = apply_film_grain(img, intensity=0.10)
    assert grained.size == (200, 200)

    blurred = apply_radial_blur(img, center=(100, 100), strength=0.06)
    assert blurred.size == (200, 200)
