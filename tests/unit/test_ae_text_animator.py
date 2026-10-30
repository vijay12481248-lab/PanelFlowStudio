"""
Unit tests for Adobe After Effects Text Animator & Range Selector Engine.
"""

import pytest
from PIL import Image, ImageFont
from engine.render.motion.ae import (
    RangeSelector,
    TextAnimatorProperties,
    AETextAnimator,
)


def test_range_selector_ramp_up_shape():
    """RangeSelector with 'ramp_up' creates a linear gradient of influence across items."""
    selector = RangeSelector(start=0.0, end=100.0, shape="ramp_up")
    total_items = 5

    # First item at 0%
    assert selector.calculate_influence(0, total_items) == 0.0
    # Middle item at 50%
    assert selector.calculate_influence(2, total_items) == 0.5
    # Last item at 100%
    assert selector.calculate_influence(4, total_items) == 1.0


def test_range_selector_square_shape():
    """Square shape is binary (1.0 inside window, 0.0 outside)."""
    selector = RangeSelector(start=25.0, end=75.0, shape="square")
    total_items = 5

    # Index 0: 0% -> outside
    assert selector.calculate_influence(0, total_items) == 0.0
    # Index 2: 50% -> inside
    assert selector.calculate_influence(2, total_items) == 1.0
    # Index 4: 100% -> outside
    assert selector.calculate_influence(4, total_items) == 0.0


def test_range_selector_words_mode():
    """RangeSelector based on words creates per-word layout."""
    animator = AETextAnimator(
        range_selector=RangeSelector(start=0.0, end=100.0, based_on="words"),
        properties=TextAnimatorProperties(tracking=5.0),
    )
    font = ImageFont.load_default()
    layouts = animator.layout_text("HELLO WORLD AE", font, start_x=100, start_y=100)

    assert len(layouts) == 3
    assert "HELLO" in layouts[0].text
    assert "WORLD" in layouts[1].text
    assert "AE" in layouts[2].text


def test_text_animator_render_to_canvas():
    """Verify render_to_canvas draws onto a transparent image with non-zero alpha pixels."""
    animator = AETextAnimator(
        range_selector=RangeSelector(start=0.0, end=100.0, shape="smooth"),
        properties=TextAnimatorProperties(opacity=0.0, position_offset=(0.0, 20.0)),
    )
    font = ImageFont.load_default()
    canvas = Image.new("RGBA", (400, 200), (0, 0, 0, 0))

    res = animator.render_to_canvas(canvas, "AFTER EFFECTS", font, origin=(200, 100), fill_color=(255, 100, 50))
    assert res.size == (400, 200)

    # Canvas should contain drawn text pixels
    extrema = res.getextrema()
    # Alpha channel must have non-zero values
    assert extrema[3][1] > 0
