"""Series: a persistent bible (cast, places, rules), character portraits and episode records shared by all episodes.

Layout: <root>/<series_id>/series.json, <root>/<series_id>/sheets/<character>.png (the IP-Adapter portraits, reused by every
episode so a character keeps their face across episodes) and <root>/<series_id>/epNNN/ for each episode's workspace.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from engine.original.models import Bible, OriginalStory


class Episode(BaseModel):
    number: int
    title: str = ""
    summary: str = ""  # fed to the next episode's prompts
    publish_at: str | None = None  # ISO time the channel owner wants it live (upload itself is a separate step)
    status: str = "queued"  # queued | running | done | failed
    workspace: str = ""
    video: str | None = None
    pdf: str | None = None
    warnings: list[str] = Field(default_factory=list)


class Series(BaseModel):
    id: str
    name: str
    genre: str
    channel_id: str = ""
    idea: str = ""
    bible: Bible
    episodes: list[Episode] = Field(default_factory=list)

    def previous_summary(self, limit: int = 4) -> str:
        done = [e for e in self.episodes if e.summary]
        return " ".join(f"Episode {e.number} ({e.title}): {e.summary}" for e in done[-limit:])

    def next_number(self) -> int:
        return max((e.number for e in self.episodes), default=0) + 1


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "series"


class SeriesStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def dir(self, series_id: str) -> Path:
        return self.root / Path(series_id).name  # never a path from the caller

    def create(self, name: str, genre: str, bible: Bible, channel_id: str = "", idea: str = "") -> Series:
        sid, n = slug(name), 2
        while (self.dir(sid) / "series.json").exists():
            sid, n = f"{slug(name)}_{n}", n + 1
        s = Series(id=sid, name=name, genre=genre, channel_id=channel_id, idea=idea, bible=bible)
        self.save(s)
        return s

    def save(self, s: Series) -> None:
        d = self.dir(s.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "series.json.tmp"
        tmp.write_text(s.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(d / "series.json")

    def get(self, series_id: str) -> Series:
        f = self.dir(series_id) / "series.json"
        if not f.exists():
            raise KeyError(series_id)
        return Series.model_validate_json(f.read_text(encoding="utf-8"))

    def list(self) -> list[Series]:
        return [Series.model_validate_json(f.read_text(encoding="utf-8")) for f in sorted(self.root.glob("*/series.json"))] if self.root.exists() else []

    def episode_dir(self, series_id: str, number: int) -> Path:
        return self.dir(series_id) / f"ep{number:03d}"

    def update_episode(self, series_id: str, ep: Episode) -> None:
        s = self.get(series_id)
        s.episodes = [e for e in s.episodes if e.number != ep.number] + [ep]
        s.episodes.sort(key=lambda e: e.number)
        self.save(s)

    def pull_sheets(self, series_id: str, ws: Path) -> int:
        """Copy the series' portraits into an episode workspace so the art engine reuses them instead of redrawing."""
        src, dst = self.dir(series_id) / "sheets", ws / "sheets"
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in src.glob("*.png") if src.exists() else []:
            if not (dst / f.name).exists():
                shutil.copy2(f, dst / f.name)
                n += 1
        return n

    def push_sheets(self, series_id: str, ws: Path) -> int:
        """Keep portraits drawn by an episode (new characters, first episode) for all later episodes."""
        src, dst = ws / "sheets", self.dir(series_id) / "sheets"
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in src.glob("*.png") if src.exists() else []:
            if not (dst / f.name).exists():
                shutil.copy2(f, dst / f.name)
                n += 1
        return n


def publish_times(count: int, start: date | None = None, at: time = time(18, 0)) -> list[str]:
    """One episode per day from `start` (default tomorrow) at `at` local time."""
    first = start or (date.today() + timedelta(days=1))
    return [datetime.combine(first + timedelta(days=i), at).isoformat() for i in range(count)]


def episode_summary(story: OriginalStory) -> str:
    """A short continuity note for later episodes: logline plus how the final scene ends."""
    last = story.scenes[-1].summary if story.scenes else ""
    return f"{story.bible.premise.logline} It ends: {last}"[:600]
