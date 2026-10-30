"""Kinetic typography animations and text motion tools."""

from engine.render.motion.typography.kinetic_text import (
    get_scramble_text,
    draw_word_stagger_reveal,
    draw_tracking_expansion_text,
    compute_rolling_counter,
    draw_typewriter_text,
    draw_extruded_text,
)
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

__all__ = [
    "get_scramble_text",
    "draw_word_stagger_reveal",
    "draw_tracking_expansion_text",
    "compute_rolling_counter",
    "draw_typewriter_text",
    "draw_extruded_text",
    "draw_smooth_kinetic_title",
    "draw_smooth_word_stagger",
    "draw_smooth_frosted_card",
    "draw_liquid_light_wipe_title",
    "draw_masked_baseline_reveal",
    "draw_3d_orbiting_text_ring",
]
