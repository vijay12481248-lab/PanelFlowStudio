"""
PanelFlow Studio Motion Director Subsystem.
Transforms approved script segments, source artwork, and master audio intervals
into deterministic, render-ready motion-comic visual timelines.
"""
from engine.motion.director import MotionDirector
from engine.motion.models.timeline import VisualTimeline, MotionScene, Shot
from engine.motion.models.camera import CameraState, NormalizedRect, TargetResolution
from engine.motion.models.enums import (
    MotionType,
    EasingFunction,
    TransitionType,
    EffectType,
    FocusType,
    TimelineSourceType,
    MotionPreset,
    WarningType,
)
from engine.motion.models.input_contract import (
    MotionDirectorInput,
    VisualSource,
    AudioInterval,
    MasterAudioTimeline,
    MotionStyleProfile,
)
from engine.motion.models.overrides import ShotOverride, MotionOverrides
from engine.motion.models.effects import EffectInstruction, EffectBudget
from engine.motion.models.transitions import TransitionInstruction
from engine.motion.models.cues import FocusTarget, CaptionCue, AnnotationCue
from engine.motion.models.layers import LayerInstruction, ParallaxPlan
from engine.motion.models.warnings import MotionWarning

__all__ = [
    "MotionDirector",
    "VisualTimeline",
    "MotionScene",
    "Shot",
    "CameraState",
    "NormalizedRect",
    "TargetResolution",
    "MotionType",
    "EasingFunction",
    "TransitionType",
    "EffectType",
    "FocusType",
    "TimelineSourceType",
    "MotionPreset",
    "WarningType",
    "MotionDirectorInput",
    "VisualSource",
    "AudioInterval",
    "MasterAudioTimeline",
    "MotionStyleProfile",
    "ShotOverride",
    "MotionOverrides",
    "EffectInstruction",
    "EffectBudget",
    "TransitionInstruction",
    "FocusTarget",
    "CaptionCue",
    "AnnotationCue",
    "LayerInstruction",
    "ParallaxPlan",
    "MotionWarning",
]
