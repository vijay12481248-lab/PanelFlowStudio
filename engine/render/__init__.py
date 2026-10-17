"""
PanelFlow Studio Production Renderer Subsystem.
Transforms deterministic VisualTimelines and MasterAudioTimelines into professional MP4 videos.
"""
from engine.render.clock import RenderFrameClock
from engine.render.composer import (
    FrameComposer,
    CameraRenderer,
    EffectRenderer,
    CaptionRenderer,
)
from engine.render.audio import AudioMixer
from engine.render.encoder import FFmpegEncoder
from engine.render.validator import RenderValidator
from engine.render.engine import RenderEngine
from engine.render.models import (
    RenderStage,
    RenderStatus,
    BackgroundFillPolicy,
    ScalePolicy,
    MusicDurationPolicy,
    RenderQuality,
    RenderProfile,
    RenderPlan,
    RenderShotPlan,
    RenderAudioTrack,
    RenderAuditReport,
    FrameSampleAudit,
)

__all__ = [
    "RenderEngine",
    "RenderFrameClock",
    "FrameComposer",
    "CameraRenderer",
    "EffectRenderer",
    "CaptionRenderer",
    "AudioMixer",
    "FFmpegEncoder",
    "RenderValidator",
    "RenderStage",
    "RenderStatus",
    "BackgroundFillPolicy",
    "ScalePolicy",
    "MusicDurationPolicy",
    "RenderQuality",
    "RenderProfile",
    "RenderPlan",
    "RenderShotPlan",
    "RenderAudioTrack",
    "RenderAuditReport",
    "FrameSampleAudit",
]
