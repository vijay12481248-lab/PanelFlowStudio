"""Per-YouTube-channel presets for the review workflow (voice, tone, language, music, branding)."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from engine.anime.review.ingest import slugify
from engine.config.settings import settings


class ChannelPreset(BaseModel):
    id: str = ""
    name: str
    voice: str = "am_michael"
    voice_rate: float = Field(default=1.0, ge=0.7, le=1.3)
    tone: str = "warm, witty, honest fan reviewer"
    language: str = "English"
    target_video_sec: float = Field(default=480.0, ge=60.0)
    music_path: str | None = None  # None = bundled default
    watermark_path: str | None = None  # logo PNG overlaid top-right
    extra_tags: list[str] = Field(default_factory=list)
    description_footer: str = ""
    burn_captions: bool = True


class ChannelStore:
    def __init__(self, path: Path | None = None):
        self.path = path or settings.app_data_dir / "config" / "anime_channels.json"

    def _read(self) -> dict[str, ChannelPreset]:
        if not self.path.exists():
            return {}
        return {k: ChannelPreset(**v) for k, v in json.loads(self.path.read_text(encoding="utf-8")).items()}

    def list(self) -> list[ChannelPreset]:
        return list(self._read().values())

    def get(self, channel_id: str) -> ChannelPreset:
        try:
            return self._read()[channel_id]
        except KeyError:
            raise KeyError(f"unknown channel preset: {channel_id}") from None

    def save(self, preset: ChannelPreset) -> ChannelPreset:
        preset = preset.model_copy(update={"id": preset.id or slugify(preset.name).lower()})
        data = self._read()
        data[preset.id] = preset
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({k: v.model_dump() for k, v in data.items()}, indent=2), encoding="utf-8")
        return preset

    def delete(self, channel_id: str) -> None:
        data = self._read()
        data.pop(channel_id, None)
        self.path.write_text(json.dumps({k: v.model_dump() for k, v in data.items()}, indent=2), encoding="utf-8")


channel_store = ChannelStore()
