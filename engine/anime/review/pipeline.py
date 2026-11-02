"""Hands-off orchestrator: ingest -> analyse -> understand -> clips -> script -> voice -> render -> package.

Each stage writes its artifact into the workspace; a stage whose artifact already exists is skipped, so a retried or
recovered job resumes where it stopped.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from engine.acquisition.rights.models import RightsDeclaration
from engine.anime.review import analysis, clips, ingest, packaging, render, script, timeline, understanding
from engine.anime.review.channels import ChannelPreset
from engine.anime.review.models import (ClipPlan, EpisodeAnalysis, IngestRecord, ReviewScript, Timeline,
                                        Understanding)

Progress = Callable[[float, str], None]


class ReviewJobSpec(BaseModel):
    source: str
    title: str
    rights: RightsDeclaration
    channel_id: str
    workspace: str


def _have(ws: Path, name: str) -> bool:
    return (ws / name).exists()


def _load(ws: Path, name: str, model):
    return model.model_validate_json((ws / name).read_text(encoding="utf-8"))


def run_review(spec: ReviewJobSpec, channel: ChannelPreset, provider, progress: Progress,
               is_cancelled: Callable[[], bool]) -> dict:
    spec.rights.validate_for_acquisition()  # the gate is re-checked here, not only at enqueue time
    ws = Path(spec.workspace)

    def step(pct: float, msg: str) -> None:
        if is_cancelled():
            raise RuntimeError("cancelled")
        progress(pct, msg)

    step(0.02, "Ingesting episode")
    rec = _load(ws, "source.json", IngestRecord) if _have(ws, "source.json") else ingest.ingest(
        spec.source, ws, spec.rights, spec.title)
    step(0.10, "Detecting shots and transcribing")
    a = _load(ws, "analysis.json", EpisodeAnalysis) if _have(ws, "analysis.json") else analysis.analyze(rec, ws)
    step(0.30, "Understanding the episode")
    if _have(ws, "understanding.json"):
        u = _load(ws, "understanding.json", Understanding)
    else:
        u = asyncio.run(understanding.understand(a, spec.title, provider, Path(a.audio_path) if a.audio_path else None))
        (ws / "understanding.json").write_text(u.model_dump_json(indent=2), encoding="utf-8")
    step(0.40, "Selecting clips")
    if _have(ws, "clips.json"):
        plan = _load(ws, "clips.json", ClipPlan)
    else:
        rms = understanding.energy_peaks(Path(a.audio_path))[1] if a.audio_path else None
        plan = clips.select_clips(a, u.beats, channel.target_video_sec, rms)
        (ws / "clips.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    step(0.50, "Writing the review script")
    if _have(ws, "script.json"):
        sc = _load(ws, "script.json", ReviewScript)
    else:
        sc = asyncio.run(script.write_script(spec.title, u, plan, provider, channel.tone, channel.language))
        (ws / "script.json").write_text(sc.model_dump_json(indent=2), encoding="utf-8")
    step(0.65, "Voicing narration")
    tl = _load(ws, "timeline.json", Timeline) if _have(ws, "timeline.json") else timeline.voice_script(
        sc, plan, ws, rec.fps, channel.voice, channel.voice_rate)
    step(0.75, "Rendering video")
    src = Path(rec.local_path)
    music = Path(channel.music_path) if channel.music_path else render.DEFAULT_MUSIC
    wm = Path(channel.watermark_path) if channel.watermark_path else None
    video = render.render_review(sc, tl, src, rec.has_audio, ws, channel.burn_captions, music, watermark=wm)
    step(0.95, "Packaging for YouTube")
    pkg = packaging.build_package(spec.title, sc, u, tl, plan, src, rec.rights, ws, channel.extra_tags,
                                  channel.description_footer)
    warnings = [w for e in tl.entries for w in e.warnings]
    progress(1.0, "Review video ready")
    return {"video": str(video), "srt": str(ws / "review.srt"), "title": pkg.title, "thumbnail": pkg.thumbnail_path,
            "duration_sec": tl.total_sec, "footage_sec": clips_total(plan), "warnings": warnings}


def clips_total(plan: ClipPlan) -> float:
    return plan.total_sec
