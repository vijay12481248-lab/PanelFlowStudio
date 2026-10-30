"""Step 7 VOICE + ALIGN: one local TTS take per line, silence-normalised and checked by speech-to-text."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from engine.narration.artifacts import PanelFacts, PerformancePlan, ScriptIR, SeriesBible, VoiceTake
from engine.narration.runtime.audio import Stt, Tts, _tokens, normalize_silence, wer, write_wav_atomic
from engine.narration.runtime.roles import load_tts_config

WER_LIMIT = 0.15
RATE_STEPS = (1.0, 0.95, 0.9)
FLAG_LIMIT = 0.10
SILENT_PAD = 1920  # 80 ms at 24 kHz


def _pronunciations(bible: SeriesBible) -> dict[str, str]:
    return {n: c.pronunciation for c in bible.characters if c.pronunciation for n in [c.name, *c.aliases] if n}


def tts_text(text: str, bible: SeriesBible) -> str:
    for name, spoken in sorted(_pronunciations(bible).items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", lambda _: spoken, text)
    return text


def _names(bible: SeriesBible, facts: Sequence[PanelFacts]) -> frozenset[str]:
    """Lower-cased tokens of every character name, alias and name mentioned: Whisper can't spell them."""
    raw = [n for c in bible.characters for n in [c.name, *c.aliases]] + [n for f in facts for n in f.names_mentioned]
    return frozenset(t for n in raw for t in _tokens(n))


def _score(ref: str, spoken: str, heard: str, names: frozenset[str] = frozenset()) -> float:
    """Whisper may hear the respelling or the name; credit whichever matches. A line with no words scores 1.0."""
    try:
        return min(wer(ref, heard, names), wer(spoken, heard, names))
    except ValueError:
        return 1.0


def _key(spoken: str, voice: str, rate: float, bible: SeriesBible, model: str) -> str:
    blob = json.dumps([spoken, voice, rate, sorted(_pronunciations(bible).items()), model], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def _take(line, rate: float, spoken: str, key: str, model: str, tts: Tts, stt: Stt, out_dir: Path, voice: str,
                names: frozenset[str] = frozenset()) -> VoiceTake:
    best: tuple[VoiceTake, Path] | None = None
    for attempt, step in enumerate(RATE_STEPS, 1):
        eff = rate * step
        audio = await asyncio.to_thread(tts.synth, spoken, voice, eff)
        try:
            audio, lead, tail = normalize_silence(audio)
        except ValueError:  # silent output: try the next rate
            continue
        path = out_dir / f"{key}.a{attempt}.wav"
        duration = write_wav_atomic(path, audio)
        stt_text, words = await asyncio.to_thread(stt.words, path)
        err = _score(line.text, spoken, stt_text, names)
        take = VoiceTake(
            line_id=line.line_id, audio_path=str(out_dir / f"{key}.wav"), duration=duration, words=words,
            lead_ms=lead, tail_ms=tail, stt_text=stt_text, wer=min(err, 1.0), tts_model=model,
            voice_id=voice, rate=eff, attempt=attempt, flagged=err > WER_LIMIT)
        if best is None or take.wer <= best[0].wer:
            best = (take, path)
        if err <= WER_LIMIT:
            break
    if best is None:  # every attempt silent: keep a flagged placeholder so the gate counts it
        path = out_dir / f"{key}.a1.wav"
        duration = write_wav_atomic(path, np.zeros(2 * SILENT_PAD, dtype=np.float32))
        best = (VoiceTake(line_id=line.line_id, audio_path=str(out_dir / f"{key}.wav"), duration=duration, words=[],
                          lead_ms=0, tail_ms=0, stt_text="", wer=1.0, tts_model=model, voice_id=voice,
                          rate=rate * RATE_STEPS[-1], attempt=len(RATE_STEPS), flagged=True), path)
    take, src = best
    for p in out_dir.glob(f"{key}.a*.wav"):
        if p != src:
            p.unlink()
    os.replace(src, out_dir / f"{key}.wav")
    return take


async def voice_lines(script: ScriptIR, plan: PerformancePlan, bible: SeriesBible, tts: Tts, stt: Stt,
                      out_dir: Path, voice: str, facts: Sequence[PanelFacts] = ()) -> tuple[list[VoiceTake], list[str]]:
    out_dir = Path(out_dir)
    names = _names(bible, facts)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = load_tts_config().model
    marks = {m.line_id: m for m in plan.lines}
    takes: list[VoiceTake] = []
    for line in script.lines:
        rate = marks[line.line_id].rate
        spoken = tts_text(line.text, bible)
        key = _key(spoken, voice, rate, bible, model)  # base rate: a retried take is still found on rerun
        wav, meta = out_dir / f"{key}.wav", out_dir / f"{key}.json"
        take = None
        if wav.exists() and meta.exists():
            try:
                take = VoiceTake.model_validate_json(meta.read_text(encoding="utf-8"))
            except ValueError:
                take = None
        if take is None:
            take = await _take(line, rate, spoken, key, model, tts, stt, out_dir, voice, names)
            tmp = meta.with_suffix(f".json.{uuid.uuid4().hex[:8]}.tmp")
            tmp.write_text(take.model_dump_json(), encoding="utf-8")
            os.replace(tmp, meta)
        takes.append(take.model_copy(update={"line_id": line.line_id}))
    flagged = sum(t.flagged for t in takes)
    reasons = [f"{flagged} of {len(takes)} takes failed the speech check"] if flagged > FLAG_LIMIT * len(takes) else []
    return takes, reasons

