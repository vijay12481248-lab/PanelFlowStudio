"""Episode understanding: transcript + audio-energy peaks -> summary, characters and typed beats (local LLM)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from engine.anime.review.models import Beat, EpisodeAnalysis, Understanding

KINDS = {"opening", "highlight", "emotional", "funny", "smooth", "weak", "ending"}
MAX_TRANSCRIPT_CHARS = 24000


class _BeatOut(BaseModel):
    start: float
    end: float
    kind: str
    label: str = Field(description="5-10 word name of the moment")
    why: str = Field(description="one sentence: why a reviewer would mention it")


class _LLMOut(BaseModel):
    summary: str = Field(description="spoiler-light plot summary of THIS episode, 3-5 sentences")
    characters: list[str]
    beats: list[_BeatOut]


def energy_peaks(wav: Path, n: int = 8, min_gap: float = 20.0) -> tuple[list[float], np.ndarray]:
    """Per-second RMS and the n loudest seconds at least min_gap apart."""
    import soundfile as sf

    audio, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    secs = len(mono) // sr
    if secs == 0:
        return [], np.zeros(0)
    rms = np.sqrt((mono[: secs * sr].reshape(secs, sr) ** 2).mean(axis=1))
    peaks: list[float] = []
    for i in np.argsort(rms)[::-1]:
        if all(abs(i - p) >= min_gap for p in peaks):
            peaks.append(float(i))
        if len(peaks) == n:
            break
    return sorted(peaks), rms


def _transcript_text(a: EpisodeAnalysis) -> str:
    lines = [f"[{s.start:.0f}s] {s.text}" for s in a.transcript]
    text = "\n".join(lines)
    if len(text) > MAX_TRANSCRIPT_CHARS:  # shrink evenly rather than cutting off the ending
        step = len(text) // MAX_TRANSCRIPT_CHARS + 2
        text = "\n".join(lines[::step])
    return text


def clean_beats(raw: list[_BeatOut], duration: float) -> list[Beat]:
    """Clamp to the episode, drop unusable/duplicate beats, sort by time."""
    out: list[Beat] = []
    for b in sorted(raw, key=lambda b: b.start):
        start, end = max(0.0, b.start), min(duration, b.end)
        kind = b.kind.strip().lower()
        if end - start < 1.0 or kind not in KINDS or any(abs(start - o.start) < 3 for o in out):
            continue
        out.append(Beat(id=f"b{len(out) + 1:02d}", start=round(start, 2), end=round(end, 2), kind=kind,
                        label=b.label.strip(), why=b.why.strip()))
    return out


def add_loud_beats(beats: list[Beat], peaks: list[float], duration: float, limit: int = 3) -> list[Beat]:
    """Dialogue-only beats miss action and music peaks: add the loudest moments no beat already covers."""
    extra = [p for p in peaks if all(not (b.start - 10 <= p <= b.end + 10) for b in beats)]
    merged = list(beats) + [Beat(id="", start=max(0.0, p - 3), end=min(duration, p + 6), kind="highlight",
                                 label="Intense moment", why="A high-impact moment with little or no dialogue")
                            for p in extra[:limit]]
    merged.sort(key=lambda b: b.start)
    return [b.model_copy(update={"id": f"b{i + 1:02d}"}) for i, b in enumerate(merged)]


async def describe_beats(beats: list[Beat], source: Path, provider, tmp: Path) -> list[Beat]:
    """One keyframe per beat -> one factual sentence from the local vision model. Failures leave the beat unchanged."""
    import subprocess

    out = []
    for b in beats:
        frame = tmp / f"{b.id}.jpg"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{(b.start + b.end) / 2}", "-i", str(source),
                            "-frames:v", "1", "-vf", "scale=768:-2", str(frame)])
        text = ""
        if r.returncode == 0 and frame.exists():
            try:
                text = (await provider.analyze_vision(
                    frame, "Describe in one factual sentence what is visibly happening in this animation frame "
                           "(who/what, action, mood). No speculation.", max_tokens=200)).strip()
            except Exception:  # vision only enriches; the review still works without it
                text = ""
        out.append(b.model_copy(update={"visual": text}))
    return out


async def understand(a: EpisodeAnalysis, title: str, provider, wav: Path | None = None,
                     source: Path | None = None, tmp: Path | None = None) -> Understanding:
    peaks = energy_peaks(wav)[0] if wav and wav.exists() else []
    prompt = (
        f'You are preparing a YouTube anime episode review of "{title}" ({a.duration_sec:.0f}s long).\n'
        f"Timed transcript (English):\n{_transcript_text(a)}\n\n"
        f"Loudest moments (seconds): {', '.join(f'{p:.0f}' for p in peaks) or 'unknown'}.\n"
        f"The episode has {len(a.shots)} shots.\n\n"
        "Return the plot summary, main characters, and 6-12 beats in time order. Use kinds: opening, highlight, "
        "emotional, funny, smooth (well-executed pacing/animation/writing), weak (slow or flawed), ending. "
        "Include at least one opening and one ending beat, and any funny/weak moments the transcript supports. "
        "Beat start/end are seconds inside the episode and each beat spans 3-20 seconds. "
        "Only use facts present in the transcript; do not invent events."
    )
    out = await provider.generate_structured(
        prompt, _LLMOut, system_prompt="You are an experienced anime reviewer and careful note-taker.",
        temperature=0.3, max_tokens=3000, num_ctx=16384)
    beats = add_loud_beats(clean_beats(out.beats, a.duration_sec), peaks, a.duration_sec)
    if source and tmp:
        tmp.mkdir(parents=True, exist_ok=True)
        beats = await describe_beats(beats, source, provider, tmp)
        # an energy peak over black frames is the end credits or a fade, not a moment worth a clip
        beats = [b for b in beats if not (b.label == "Intense moment" and "black" in b.visual.lower())]
    return Understanding(summary=out.summary.strip(), characters=out.characters, beats=beats, energy_peaks=peaks)
