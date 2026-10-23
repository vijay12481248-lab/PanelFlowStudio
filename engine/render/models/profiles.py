"""
Render configuration profiles for PanelFlow Production Renderer.
"""
from typing import Optional
from pydantic import BaseModel, Field
from engine.render.models.enums import RenderQuality


def editor_render_profile(name: str, state: dict | None = None) -> "RenderProfile":
    """Keep legacy profile choices; extend the same encoder to 4:5/custom/4K."""
    state = state or {}
    aspect = state.get("aspect_ratio", "16:9")
    if name == "vertical_shorts":
        return RenderProfile.vertical_shorts()
    if name == "square_feed":
        return RenderProfile.square_feed()
    height = 720 if name == "draft_720p" else 2160 if name == "ultra_4k" else 1080
    dimensions = {"16:9": (round(height * 16 / 9), height), "9:16": (height, round(height * 16 / 9)),
                  "1:1": (height, height), "4:5": (round(height * .8), height)}
    width, output_height = dimensions.get(aspect, dimensions["16:9"])
    if aspect == "custom":
        width, output_height = state.get("canvas_width", 1920), state.get("canvas_height", 1080)
        if any(type(value) is not int or value < 64 or value > 7680 or value % 2 for value in (width, output_height)):
            raise ValueError("Custom canvas dimensions must be even integers from 64 to 7680 pixels")
    if name == "draft_720p":
        return RenderProfile(width=width, height=output_height, fps=30, crf=26, preset="ultrafast", quality=RenderQuality.DRAFT)
    return RenderProfile(width=width, height=output_height, fps=30)


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
