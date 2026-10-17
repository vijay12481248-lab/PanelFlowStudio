"""
Controlled enumerations for PanelFlow Production Renderer.
"""
from enum import Enum


class RenderStage(str, Enum):
    PREPARING = "PREPARING"
    COMPOSING = "COMPOSING"
    ENCODING = "ENCODING"
    MUXING = "MUXING"
    VALIDATING = "VALIDATING"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class RenderStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BackgroundFillPolicy(str, Enum):
    BLACK = "BLACK"
    BLURRED_SOURCE = "BLURRED_SOURCE"
    SOLID_COLOR = "SOLID_COLOR"
    EXTENDED_EDGE = "EXTENDED_EDGE"


class ScalePolicy(str, Enum):
    COVER = "COVER"
    CONTAIN = "CONTAIN"
    SMART_CROP = "SMART_CROP"


class MusicDurationPolicy(str, Enum):
    LOOP = "LOOP"
    FADE_OUT = "FADE_OUT"
    EXTEND_WITH_SILENCE = "EXTEND_WITH_SILENCE"
    NO_MUSIC_AFTER_END = "NO_MUSIC_AFTER_END"


class RenderQuality(str, Enum):
    DRAFT = "DRAFT"
    PREVIEW = "PREVIEW"
    PRODUCTION = "PRODUCTION"
