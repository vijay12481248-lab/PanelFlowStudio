"""Voice + sync: per-segment TTS (existing Kokoro adapter), measured durations, and a timeline where the audio drives the clip."""
from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from engine.anime.review.models import Clip, ClipPlan, ReviewScript, Timeline, TimelineEntry
from engine.narration.runtime import audio as rt

PAUSE_SEC = 0.25     # breathing room after every segment
MIN_SPEED = 0.8      # slower than this looks like a mistake; hold the last frame instead
MIN_TAKE = 1.0       # a clip remainder shorter than this is not worth using: wrap to the clip start
LONG_HOLD_SEC = 3.0


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def synth_segment(tts, text: str, voice: str, rate: float, fps: float, out: Path) -> float:
    """Writes a wav whose length is trimmed of dead air, plus a pause, padded up to a whole video frame."""
    audio, _, _ = rt.normalize_silence(tts.synth(text, voice, rate))
    audio = np.concatenate([audio, np.zeros(int(PAUSE_SEC * rt.SR), dtype=np.float32)])
    frame = rt.SR / fps
    n = math.ceil(len(audio) / frame - 1e-9) * frame
    audio = np.concatenate([audio, np.zeros(int(round(n)) - len(audio), dtype=np.float32)])
    rt.write_wav_atomic(out, audio)
    return wav_seconds(out)


def plan_entry(d: float, clip: Clip, cursor: float) -> tuple[float, float, float, float, list[str]]:
    """(src_start, src_len, speed, hold, warnings) covering d seconds of narration from the clip at cursor."""
    warns: list[str] = []
    if clip.end - cursor < MIN_TAKE:
        cursor = clip.start
        warns.append("clip footage reused")
    avail = clip.end - cursor
    if avail >= d:
        return cursor, d, 1.0, 0.0, warns
    speed = max(MIN_SPEED, avail / d)
    hold = max(0.0, d - avail / speed)
    if hold > LONG_HOLD_SEC:
        warns.append(f"long freeze {hold:.1f}s: clip too short for this segment")
    return cursor, avail, speed, hold, warns


def build_timeline(script: ReviewScript, plan: ClipPlan, durations: list[float], paths: list[Path],
                   fps: float, voice: str) -> Timeline:
    clips = {c.id: c for c in plan.clips}
    cursors = {c.id: c.start for c in plan.clips}
    entries: list[TimelineEntry] = []
    t = 0.0
    for seg, d, p in zip(script.segments, durations, paths):
        clip = clips[seg.clip_id]
        start, length, speed, hold, warns = plan_entry(d, clip, cursors[clip.id])
        cursors[clip.id] = start + length
        entries.append(TimelineEntry(segment_id=seg.id, clip_id=clip.id, audio_path=str(p), audio_sec=round(d, 4),
                                     timeline_start=round(t, 4), src_start=round(start, 3), src_len=round(length, 3),
                                     speed=round(speed, 3), hold_sec=round(hold, 3), warnings=warns))
        t += entries[-1].audio_sec
    return Timeline(fps=fps, total_sec=round(t, 4), entries=entries, voice=voice)


def voice_script(script: ReviewScript, plan: ClipPlan, workspace: Path, fps: float = 30.0, voice: str = "am_michael",
                 rate: float = 1.0, tts=None) -> Timeline:
    tts = tts or rt.get_default_tts()
    out_dir = workspace / "voice"
    paths, durs = [], []
    try:
        for seg in script.segments:
            p = out_dir / f"{seg.id}.wav"
            durs.append(synth_segment(tts, seg.text, voice, rate, fps, p))
            paths.append(p)
    finally:
        rt.release_audio_models()
    tl = build_timeline(script, plan, durs, paths, fps, voice)
    (workspace / "timeline.json").write_text(tl.model_dump_json(indent=2), encoding="utf-8")
    return tl
