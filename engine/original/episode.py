"""One episode, hands-off: story -> art -> video -> comic pages -> package. Each stage resumes from its artifacts."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Callable

from engine.anime.review.channels import ChannelPreset
from engine.original import art, pages, video
from engine.original.beats import BEATS_FILE, expand_story
from engine.original.series import Episode, SeriesStore, episode_summary
from engine.original.story import generate_story, estimated_minutes
from engine.original.models import OriginalStory

Progress = Callable[[float, str], None]
WAIT_POLL_SEC = 5.0
WAIT_LIMIT_SEC = 6 * 3600


def wait_for_previous(store: SeriesStore, series_id: str, number: int, is_cancelled: Callable[[], bool],
                      poll: float = WAIT_POLL_SEC, limit: float = WAIT_LIMIT_SEC) -> None:
    """Episodes of a series are written in order: episode N needs the summary of N-1. Waits until N-1 is done or failed."""
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if is_cancelled():
            raise RuntimeError("cancelled")
        prev = next((e for e in store.get(series_id).episodes if e.number == number - 1), None)
        if prev is None or prev.status in ("done", "failed"):
            return
        time.sleep(poll)
    raise TimeoutError(f"episode {number - 1} did not finish within {limit / 3600:.0f} h")


def run_episode(store: SeriesStore, series_id: str, number: int, channel: ChannelPreset | None, provider, runner_factory,
                progress: Progress, is_cancelled: Callable[[], bool], scenes: int | None = None, check: bool = True, refine: bool = False) -> dict:
    wait_for_previous(store, series_id, number, is_cancelled)
    series = store.get(series_id)
    ws = store.episode_dir(series_id, number)
    ws.mkdir(parents=True, exist_ok=True)
    ep = next((e for e in series.episodes if e.number == number), Episode(number=number))
    ep = ep.model_copy(update={"status": "running", "workspace": str(ws)})
    store.update_episode(series_id, ep)

    def step(pct: float, msg: str) -> None:
        if is_cancelled():
            raise RuntimeError("cancelled")
        progress(pct, f"Episode {number}: {msg}")

    try:
        step(0.02, "Writing the story")
        f = ws / "story.json"
        if f.exists():
            story = OriginalStory.model_validate_json(f.read_text(encoding="utf-8"))
        else:
            story = asyncio.run(generate_story(series.genre, provider, series.idea, scenes, series_bible=series.bible,
                                               previous=series.previous_summary()))
            f.write_text(story.model_dump_json(indent=2), encoding="utf-8")
        ep = ep.model_copy(update={"title": story.bible.premise.title, "summary": episode_summary(story)})
        store.update_episode(series_id, ep)

        step(0.12, "Planning one picture per narrated moment")
        bf = ws / BEATS_FILE
        if bf.exists():
            story = OriginalStory.model_validate_json(bf.read_text(encoding="utf-8"))
        else:
            story = asyncio.run(expand_story(story, provider, lambda p, m: step(0.12 + 0.08 * p, m)))
            bf.write_text(story.model_dump_json(indent=2), encoding="utf-8")

        step(0.2, "Drawing the pictures")
        store.pull_sheets(series_id, ws)
        runner = runner_factory()
        report = art.generate_art(story, ws, runner, provider if check else None,
                                  progress=lambda p, m: step(0.2 + 0.45 * p, m), is_cancelled=is_cancelled, refine=True if refine else None)
        store.push_sheets(series_id, ws)

        step(0.65, "Voicing and rendering the video")
        narrator = (channel.voice, channel.voice_rate) if channel else None
        music = Path(channel.music_path) if channel and channel.music_path else video.rr.DEFAULT_MUSIC
        out = video.build_video(story, ws, None, 30.0, channel.burn_captions if channel else True, music, narrator=narrator,
                                progress=lambda p, m: step(0.65 + 0.2 * p, m))
        step(0.9, "Packaging and comic pages")
        pkg = video.package(story, ws, channel.extra_tags if channel else None, channel.description_footer if channel else "")
        pg = pages.build_pages(story, ws)
        warnings = list(story.warnings) + [f"panel {p} below the consistency threshold" for p in report["below_threshold"]]
        ep = ep.model_copy(update={"status": "done", "video": out["video"], "pdf": pg["pdf"], "warnings": warnings})
        store.update_episode(series_id, ep)
        progress(1.0, f"Episode {number} ready")
        return {"series": series_id, "episode": number, "title": ep.title, "video": out["video"], "pdf": pg["pdf"],
                "minutes": round(out["duration_sec"] / 60, 1), "publish_at": ep.publish_at, "warnings": warnings,
                "mean_consistency": report["mean_score"], "package_title": pkg["title"]}
    except BaseException:
        store.update_episode(series_id, ep.model_copy(update={"status": "failed"}))
        raise
