"""Motion graphics visual effects and shaders."""

from engine.render.motion.effects.shimmer import render_shimmer_text
from engine.render.motion.effects.chromatic import (
    apply_chromatic_aberration,
    apply_scanline_glitch,
    compute_camera_shake,
)
from engine.render.motion.effects.particles import ParticleEmitter, Particle
from engine.render.motion.effects.lighting import (
    render_volumetric_glow,
    render_anamorphic_flare,
    render_vignette,
    apply_bloom,
    apply_film_grain,
    apply_radial_blur,
)

__all__ = [
    "render_shimmer_text",
    "apply_chromatic_aberration",
    "apply_scanline_glitch",
    "compute_camera_shake",
    "ParticleEmitter",
    "Particle",
    "render_volumetric_glow",
    "render_anamorphic_flare",
    "render_vignette",
    "apply_bloom",
    "apply_film_grain",
    "apply_radial_blur",
]
