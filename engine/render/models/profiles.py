"""
Render configuration profiles for PanelFlow Production Renderer.
"""
from typing import Optional
from pydantic import BaseModel, Field
from engine.render.models.enums import RenderQuality


class RenderProfile(BaseModel):
    """
    Video and audio encoding parameters for an MP4 render job.
    """
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)
    fps: int = Field(default=30, gt=0)
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_sample_rate: int = 48000
    audio_channels: int = 2
    pixel_format: str = "yuv420p"
    crf: int = 18
    preset: str = "medium"
    video_bitrate_kbps: Optional[int] = 8000
    audio_bitrate_kbps: int = 256
    quality: RenderQuality = RenderQuality.PRODUCTION

    @property
    def aspect_ratio(self) -> float:
        return self.width / max(1, self.height)

    @classmethod
    def standard_1080p(cls, quality: RenderQuality = RenderQuality.PRODUCTION) -> "RenderProfile":
        crf = 18 if quality == RenderQuality.PRODUCTION else (23 if quality == RenderQuality.PREVIEW else 28)
        preset = "medium" if quality == RenderQuality.PRODUCTION else "veryfast"
        return cls(width=1920, height=1080, fps=30, crf=crf, preset=preset, quality=quality)

    @classmethod
    def vertical_shorts(cls, quality: RenderQuality = RenderQuality.PRODUCTION) -> "RenderProfile":
        return cls(width=1080, height=1920, fps=30, quality=quality)

    @classmethod
    def square_feed(cls, quality: RenderQuality = RenderQuality.PRODUCTION) -> "RenderProfile":
        return cls(width=1080, height=1080, fps=30, quality=quality)

    @classmethod
    def draft_720p(cls) -> "RenderProfile":
        return cls(width=1280, height=720, fps=30, crf=26, preset="ultrafast", quality=RenderQuality.DRAFT)

    @classmethod
    def preview_1080p(cls) -> "RenderProfile":
        return cls(width=1920, height=1080, fps=30, crf=22, preset="fast", quality=RenderQuality.PREVIEW)
