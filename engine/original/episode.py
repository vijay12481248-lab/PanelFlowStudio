"""One episode, hands-off: story -> art -> video -> comic pages -> package. Each stage resumes from its artifacts."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger("panelflow.original.episode")

from engine.anime.review.channels import ChannelPreset
from engine.original import art, pages, video
from engine.original.animate import animate_beats
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


def animate_stage(story: OriginalStory, ws, step: Progress, is_cancelled: Callable[[], bool]) -> list[str]:
    """Key moments move with the fast H3 workflow. Never fatal: a failed clip, or an animation that cannot run at all (ComfyUI or a model missing),
    leaves those beats as stills and comes back as a warning; only a cancel propagates."""
    step(0.55, "Animating key moments")
    try:
        made = animate_beats(story, ws, progress=lambda p, m: step(0.55 + 0.1 * p, m), is_cancelled=is_cancelled)
        return [f"clip failed for {f['beat']}: {f['error']}" for f in made["failed"]]
    except Exception as exc:
        if str(exc) == "cancelled":
            raise
        return [f"animation skipped: {str(exc)[:160]}"]


def _pre_synthesize_episode_audio_async(
    story: OriginalStory,
    ws: Path,
    channel: ChannelPreset | None,
    is_cancelled: Callable[[], bool],
) -> threading.Thread:
    """Pre-synthesizes Kokoro audio on CPU while ComfyUI renders images on the GPU."""
    def _worker():
        try:
            from engine.narration.runtime import audio as rt
            from engine.original import video

            tts = rt.KokoroTts()
            narrator = (channel.voice, channel.voice_rate) if channel else None
            narrator_tuple, chars = video.voices_for(story, narrator)
            (ws / "voice").mkdir(parents=True, exist_ok=True)
            meta_path = ws / "video_meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

            for p in story.panels:
                if is_cancelled():
                    break
                wav = ws / "voice" / f"{p.id}.wav"
                vkey = video._digest(json.dumps(video.spoken_parts(p)), json.dumps(narrator_tuple), json.dumps(chars))
                if not (wav.exists() and meta.get(p.id, {}).get("voice") == vkey):
                    video.voice_panel(tts, p, narrator_tuple, chars, 30.0, wav)
                    meta[p.id] = {**(meta.get(p.id, {})), "voice": vkey}
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
        except Exception as exc:
            logger.debug(f"Audio pre-synthesis background worker encountered non-fatal error: {exc}")
        finally:
            try:
                from engine.narration.runtime import audio as rt
                rt.release_audio_models()
            except Exception:
                pass

    t = threading.Thread(target=_worker, name="kokoro_tts_overlap", daemon=True)
    t.start()
    return t


def run_episode(store: SeriesStore, series_id: str, number: int, channel: ChannelPreset | None, provider, runner_factory,
                progress: Progress, is_cancelled: Callable[[], bool], scenes: int | None = None, check: bool = True, refine: bool = False, animate: bool = False, preview: bool = False) -> dict:
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

        # Overlap CPU-bound Kokoro TTS audio rendering with GPU image rendering
        audio_thread = _pre_synthesize_episode_audio_async(story, ws, channel, is_cancelled)

        try:
            report = art.generate_art(story, ws, runner, provider if check else None,
                                      progress=lambda p, m: step(0.2 + 0.35 * p, m), is_cancelled=is_cancelled,
                                      refine=True if refine else None, preview=preview)
        finally:
            audio_thread.join(timeout=120.0)

        store.push_sheets(series_id, ws)

        if preview:
            warnings = list(story.warnings) + [f"panel {p} below the consistency threshold" for p in report.get("below_threshold", [])]
            ep = ep.model_copy(update={"status": "draft", "warnings": warnings})
            store.update_episode(series_id, ep)
            progress(1.0, f"Episode {number} draft ready")
            return {"series": series_id, "episode": number, "title": ep.title, "preview": True, "art": report, "panels": len(story.panels)}

        animate_note = animate_stage(story, ws, step, is_cancelled) if animate else []

        step(0.65, "Voicing and rendering the video")
        narrator = (channel.voice, channel.voice_rate) if channel else None
        music = Path(channel.music_path) if channel and channel.music_path else video.rr.DEFAULT_MUSIC
        out = video.build_video(story, ws, None, 30.0, channel.burn_captions if channel else True, music, narrator=narrator,
                                progress=lambda p, m: step(0.65 + 0.2 * p, m))
        step(0.9, "Packaging and comic pages")
        pkg = video.package(story, ws, channel.extra_tags if channel else None, channel.description_footer if channel else "")
        pg = pages.build_pages(story, ws)
        warnings = list(story.warnings) + [f"panel {p} below the consistency threshold" for p in report["below_threshold"]] + animate_note
        ep = ep.model_copy(update={"status": "done", "video": out["video"], "pdf": pg["pdf"], "warnings": warnings})
        store.update_episode(series_id, ep)
        progress(1.0, f"Episode {number} ready")
        return {"series": series_id, "episode": number, "title": ep.title, "video": out["video"], "pdf": pg["pdf"],
                "minutes": round(out["duration_sec"] / 60, 1), "publish_at": ep.publish_at, "warnings": warnings,
                "mean_consistency": report["mean_score"], "package_title": pkg["title"]}
    except BaseException:
        store.update_episode(series_id, ep.model_copy(update={"status": "failed"}))
        raise
