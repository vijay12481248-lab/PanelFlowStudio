"""
Adobe After Effects Motion Architecture for PanelFlow Studio.
Full programmatic implementation of After Effects motion systems:
- Keyframe Velocity & Speed Graph (Speed + Influence -> Bezier handles)
- Expressions Engine (wiggle, inertia_bounce, loop_out, value_at_time)
- Text Animators & Range Selectors (Square, Ramp Up, Ramp Down, Smooth, Words/Characters)
- Temporal Motion Blur (180° shutter angle, sub-frame supersampling)
- Layer Transforms, Anchor Points, Parenting & Track Mattes
"""

from engine.render.motion.ae.velocity import (
    KeyframeVelocity,
    ae_velocity_to_bezier,
    evaluate_ae_segment,
    EASY_EASE_OUT_HANDLE,
    EASY_EASE_IN_HANDLE,
    AE_HERO_OUT_HANDLE,
    AE_HERO_IN_HANDLE,
    AE_EXPLOSIVE_OUT_HANDLE,
    AE_EXPLOSIVE_IN_HANDLE,
    AE_ELEGANT_OUT_HANDLE,
    AE_ELEGANT_IN_HANDLE,
)

from engine.render.motion.ae.expressions import (
    wiggle,
    inertia_bounce,
    loop_out,
    linear,
    ease,
    value_at_time,
)

from engine.render.motion.ae.text_animator import (
    RangeSelector,
    TextAnimatorProperties,
    AETextAnimator,
    GlyphLayout,
)

from engine.render.motion.ae.motion_blur import AEMotionBlur
from engine.render.motion.ae.layer import AELayer

__all__ = [
    # Velocity & Speed Graph
    "KeyframeVelocity",
    "ae_velocity_to_bezier",
    "evaluate_ae_segment",
    "EASY_EASE_OUT_HANDLE",
    "EASY_EASE_IN_HANDLE",
    "AE_HERO_OUT_HANDLE",
    "AE_HERO_IN_HANDLE",
    "AE_EXPLOSIVE_OUT_HANDLE",
    "AE_EXPLOSIVE_IN_HANDLE",
    "AE_ELEGANT_OUT_HANDLE",
    "AE_ELEGANT_IN_HANDLE",
    # Expressions
    "wiggle",
    "inertia_bounce",
    "loop_out",
    "linear",
    "ease",
    "value_at_time",
    # Text Animators
    "RangeSelector",
    "TextAnimatorProperties",
    "AETextAnimator",
    "GlyphLayout",
    # Motion Blur
    "AEMotionBlur",
    # Layers & Mattes
    "AELayer",
]
