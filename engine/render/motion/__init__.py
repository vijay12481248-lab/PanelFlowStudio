"""
PanelFlow Studio - Super Motion Graphics Engine
Advanced, high-performance, procedural motion graphics, kinetic typography, and visual effects.
"""

# Models & Registry
from engine.render.motion.models import (
    MotionPresetDefinition,
    MotionGraphicProps,
    MotionPreviewRequest,
    MotionPreviewResponse,
    MotionRenderRequest,
    MotionRenderResponse,
)
from engine.render.motion.registry import MotionRegistry

# Audio-Reactive Engine
from engine.render.motion.audio import AudioFeatureExtractor

# Core Scene & Curves
from engine.render.motion.curves import (
    ease_out_expo,
    ease_out_back,
    ease_out_cubic,
    spring_interpolate,
    solve_cubic_bezier,
    ease_catmull_rom,
    BEZIER_EASE_IN_OUT,
    BEZIER_FAST_OUT_SLOW_IN,
)
from engine.render.motion.scene import MotionScene
from engine.render.motion.elements import (
    MotionElement,
    KineticTextElement,
    CardElement,
    ConnectorTrackElement,
    MetricCounterElement,
    AttentionHeatmapElement,
)

# Visual Effects & Shaders
from engine.render.motion.effects import (
    render_shimmer_text,
    apply_chromatic_aberration,
    apply_scanline_glitch,
    compute_camera_shake,
    ParticleEmitter,
    Particle,
    render_volumetric_glow,
    render_anamorphic_flare,
    render_vignette,
    apply_bloom,
    apply_film_grain,
    apply_radial_blur,
)

# Procedural Transitions
from engine.render.motion.transitions import (
    render_whip_pan_glitch,
    render_light_leak_burn,
    render_geometric_slice_wipe,
)

# Kinetic Typography
from engine.render.motion.typography import (
    get_scramble_text,
    draw_word_stagger_reveal,
    draw_tracking_expansion_text,
    compute_rolling_counter,
    draw_typewriter_text,
    draw_extruded_text,
    draw_smooth_kinetic_title,
    draw_smooth_word_stagger,
    draw_smooth_frosted_card,
    draw_liquid_light_wipe_title,
    draw_masked_baseline_reveal,
)

# Generative Backgrounds
from engine.render.motion.backgrounds import (
    FluidCausticsGenerator,
    WaveRibbonMeshGenerator,
    CyberGrid3DGenerator,
    ParticleStarfield3DGenerator,
)

# Presentation Templates (Full Universe of 10 Production Presets)
from engine.render.motion.presentation import (
    KeynoteShowcaseScene,
    CyberHUDScene,
    SciFiContainmentScene,
    CorporateBenchmarkScene,
    KineticEditorialScene,
    AnimeBattleHUDScene,
    MatrixDigitalRainScene,
    SynthwaveSunsetScene,
    LuxuryGoldMonogramScene,
    CosmicNebulaWarpScene,
    AEDynamicKineticScene,
)

# Adobe After Effects Motion Architecture Engine
from engine.render.motion.ae import (
    KeyframeVelocity,
    ae_velocity_to_bezier,
    evaluate_ae_segment,
    wiggle,
    inertia_bounce,
    loop_out,
    RangeSelector,
    TextAnimatorProperties,
    AETextAnimator,
    AEMotionBlur,
    AELayer,
)

# Normalized Choreography & Animora Bridge
from engine.render.motion.choreography import MotionChoreographer
from engine.render.motion.bridge import AnimoraAssetBridge

__all__ = [
    # Models & Registry
    "MotionPresetDefinition",
    "MotionGraphicProps",
    "MotionPreviewRequest",
    "MotionPreviewResponse",
    "MotionRenderRequest",
    "MotionRenderResponse",
    "MotionRegistry",
    # Audio-Reactive
    "AudioFeatureExtractor",
    # Curves
    "ease_out_expo",
    "ease_out_back",
    "ease_out_cubic",
    "spring_interpolate",
    "solve_cubic_bezier",
    "ease_catmull_rom",
    "BEZIER_EASE_IN_OUT",
    "BEZIER_FAST_OUT_SLOW_IN",
    # Choreography & Bridge
    "MotionChoreographer",
    "AnimoraAssetBridge",
    # Scene
    "MotionScene",
    "MotionElement",
    "KineticTextElement",
    "CardElement",
    "ConnectorTrackElement",
    "MetricCounterElement",
    "AttentionHeatmapElement",
    # Effects
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
    # Transitions
    "render_whip_pan_glitch",
    "render_light_leak_burn",
    "render_geometric_slice_wipe",
    # Typography
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
    # Backgrounds
    "FluidCausticsGenerator",
    "WaveRibbonMeshGenerator",
    "CyberGrid3DGenerator",
    "ParticleStarfield3DGenerator",
    # Templates
    "KeynoteShowcaseScene",
    "CyberHUDScene",
    "SciFiContainmentScene",
    "CorporateBenchmarkScene",
    "KineticEditorialScene",
    "AnimeBattleHUDScene",
    "MatrixDigitalRainScene",
    "SynthwaveSunsetScene",
    "LuxuryGoldMonogramScene",
    "CosmicNebulaWarpScene",
    "AEDynamicKineticScene",
    # Adobe After Effects Motion Architecture
    "KeyframeVelocity",
    "ae_velocity_to_bezier",
    "evaluate_ae_segment",
    "wiggle",
    "inertia_bounce",
    "loop_out",
    "RangeSelector",
    "TextAnimatorProperties",
    "AETextAnimator",
    "AEMotionBlur",
    "AELayer",
]
