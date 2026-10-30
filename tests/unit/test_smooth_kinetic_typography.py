"""
Unit tests for PanelFlow Studio Smooth Kinetic Typography Engine.
"""

import pytest
from PIL import Image, ImageFont, ImageDraw
from engine.render.motion.typography.smooth_kinetic import (
    draw_smooth_kinetic_title,
    draw_smooth_word_stagger,
    draw_smooth_frosted_card,
    draw_liquid_light_wipe_title,
    draw_masked_baseline_reveal,
)
from engine.render.motion.typography.orbital_kinetic import (
    draw_3d_orbiting_text_ring,
)


def test_draw_smooth_kinetic_title():
    canvas = Image.new("RGBA", (800, 400), (0, 0, 0, 255))
    font = ImageFont.load_default()

    # Pre-start: should remain blank
    draw_smooth_kinetic_title(canvas, "SYNTHESIS", cx=400, cy=200, font=font, t=0.0, start_t=1.0)
    assert canvas.size == (800, 400)

    # Active reveal at t=1.5s
    draw_smooth_kinetic_title(canvas, "SYNTHESIS", cx=400, cy=200, font=font, t=1.5, start_t=1.0)
    extrema = canvas.getextrema()
    # Should have drawn non-zero text pixels in white/accent channels
    assert extrema[0][1] > 200


def test_draw_smooth_word_stagger():
    canvas = Image.new("RGBA", (800, 400), (0, 0, 0, 255))
    font = ImageFont.load_default()

    draw_smooth_word_stagger(canvas, "REVOLUTIONARY ARCHITECTURE UNLOCKED", cx=400, cy=200, font=font, t=1.0, start_t=0.0)
    extrema = canvas.getextrema()
    assert extrema[0][1] > 100


def test_draw_3d_orbiting_text_ring():
    behind = Image.new("RGBA", (800, 400), (0, 0, 0, 0))
    front = Image.new("RGBA", (800, 400), (0, 0, 0, 0))
    font = ImageFont.load_default()

    draw_3d_orbiting_text_ring(
        behind_canvas=behind,
        front_canvas=front,
        text="AETHER VELOCITY ONE // 195 COUNTRIES",
        cx=400,
        cy=200,
        font=font,
        t=1.0,
    )
    # Both behind and front layers should receive characters sorted by depth
    assert behind.getextrema()[3][1] > 0
    assert front.getextrema()[3][1] > 0



def test_draw_liquid_light_wipe_title():
    canvas = Image.new("RGBA", (800, 400), (0, 0, 0, 255))
    font = ImageFont.load_default()

    # Pre-start
    draw_liquid_light_wipe_title(canvas, "NEXT GEN ENGINE", cx=400, cy=200, font=font, t=0.0, start_t=1.0)
    assert canvas.getextrema()[0] == (0, 0)

    # Active wipe reveal at t=1.6s
    draw_liquid_light_wipe_title(canvas, "NEXT GEN ENGINE", cx=400, cy=200, font=font, t=1.6, start_t=1.0)
    extrema = canvas.getextrema()
    assert extrema[0][1] > 200


def test_draw_masked_baseline_reveal():
    canvas = Image.new("RGBA", (800, 400), (0, 0, 0, 255))
    font = ImageFont.load_default()

    # Pre-start
    draw_masked_baseline_reveal(canvas, "SUPERIOR ACCURACY", cx=400, cy=200, font=font, t=0.0, start_t=1.0)
    assert canvas.getextrema()[0] == (0, 0)

    # Active baseline rise at t=1.5s
    draw_masked_baseline_reveal(canvas, "SUPERIOR ACCURACY", cx=400, cy=200, font=font, t=1.5, start_t=1.0)
    extrema = canvas.getextrema()
    assert extrema[0][1] > 200


def test_draw_smooth_frosted_card():
    canvas = Image.new("RGBA", (800, 400), (0, 0, 0, 255))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    draw_smooth_frosted_card(
        draw=draw,
        x=50,
        y=50,
        w=300,
        h=200,
        p_enter=0.8,
        border_color=(56, 189, 248),
        title="LATENCY",
        val_str="0.42 ms",
        desc1="Instantaneous",
        desc2="Zero perception lag",
        font_badge=font,
        font_metric=font,
        font_body_bold=font,
        font_body=font,
        t=1.0,
    )
    extrema = canvas.getextrema()
    assert extrema[0][1] > 100


def test_draw_3d_orbiting_text_ring():
    behind = Image.new("RGBA", (800, 400), (0, 0, 0, 0))
    front = Image.new("RGBA", (800, 400), (0, 0, 0, 0))
    font = ImageFont.load_default()

    draw_3d_orbiting_text_ring(
        behind_canvas=behind,
        front_canvas=front,
        text="AETHER VELOCITY ONE // 195 COUNTRIES",
        cx=400,
        cy=200,
        font=font,
        t=1.0,
    )
    # Both behind and front layers should receive characters sorted by depth
    assert behind.getextrema()[3][1] > 0
    assert front.getextrema()[3][1] > 0

