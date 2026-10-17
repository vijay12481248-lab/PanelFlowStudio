from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel

@dataclass(frozen=True)
class RenderProfile:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_sample_rate: int = 48000
    pixel_format: str = "yuv420p"

DEFAULT_PRODUCTION_PROFILE = RenderProfile()

class RenderJobRequest(BaseModel):
    project_id: str
    output_filename: str = "master_render.mp4"
    shot_plan_path: str
    burn_captions: bool = False
