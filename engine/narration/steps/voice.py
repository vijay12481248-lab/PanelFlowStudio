"""Step 7 VOICE + ALIGN: one local TTS take per line, silence-normalised and checked by speech-to-text."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

from engine.narration.artifacts import PerformancePlan, ScriptIR, SeriesBible, VoiceTake
from engine.narration.runtime.audio import Stt, Tts, normalize_silence, wer, write_wav_atomic

TTS_MODEL = "kokoro-82m"
WER_LIMIT = 0.15
RATE_STEPS = (1.0, 0.95, 0.9)
FLAG_LIMIT = 0.10


def _pronunciations(bible: SeriesBible) -> dict[str, str]:
    return {n: c.pronunciation for c in bible.characters if c.pronunciation for n in [c.name, *c.aliases] if n}


def tts_text(text: str, bible: SeriesBible) -> str:
    for name, spoken in sorted(_pronunciations(bible).items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", lambda _: spoken, text)
    return text


def _key(spoken: str, voice: str, rate: float, bible: SeriesBible) -> str:
    blob = json.dumps([spoken, voice, rate, sorted(_pronunciations(bible).items()), TTS_MODEL], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def _take(line, rate: float, spoken: str, key: str, bible, tts: Tts, stt: Stt, out_dir: Path, voice: str) -> VoiceTake:
    best: tuple[VoiceTake, Path] | None = None
    for attempt, step in enumerate(RATE_STEPS, 1):
        eff = rate * step
        audio = await asyncio.to_thread(tts.synth, spoken, voice, eff)
        audio, lead, tail = normalize_silence(audio)
        path = out_dir / f"{key}.a{attempt}.wav"
        duration = write_wav_atomic(path, audio)
        stt_text, words = await asyncio.to_thread(stt.words, path)
        err = wer(line.text, stt_text)  # 1.0 when STT heard nothing
        take = VoiceTake(
            line_id=line.line_id, audio_path=str(out_dir / f"{key}.wav"), duration=duration, words=words,
            lead_ms=lead, tail_ms=tail, stt_text=stt_text, wer=min(err, 1.0), tts_model=TTS_MODEL,
            voice_id=voice, rate=eff, attempt=attempt, flagged=err > WER_LIMIT)
        if best is None or take.wer <= best[0].wer:
            best = (take, path)
        if err <= WER_LIMIT:
            break
    take, src = best
    for p in out_dir.glob(f"{key}.a*.wav"):
        if p != src:
            p.unlink()
    os.replace(src, out_dir / f"{key}.wav")
    return take


async def voice_lines(script: ScriptIR, plan: PerformancePlan, bible: SeriesBible, tts: Tts, stt: Stt,
                      out_dir: Path, voice: str) -> tuple[list[VoiceTake], list[str]]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    marks = {m.line_id: m for m in plan.lines}
    takes: list[VoiceTake] = []
    for line in script.lines:
        rate = marks[line.line_id].rate
        spoken = tts_text(line.text, bible)
        key = _key(spoken, voice, rate, bible)  # base rate: a retried take is still found on rerun
        wav, meta = out_dir / f"{key}.wav", out_dir / f"{key}.json"
        take = None
        if wav.exists() and meta.exists():
            try:
                take = VoiceTake.model_validate_json(meta.read_text(encoding="utf-8"))
            except ValueError:
                take = None
        if take is None:
            take = await _take(line, rate, spoken, key, bible, tts, stt, out_dir, voice)
            tmp = meta.with_suffix(".json.tmp")
            tmp.write_text(take.model_dump_json(), encoding="utf-8")
            os.replace(tmp, meta)
        takes.append(take)
    flagged = sum(t.flagged for t in takes)
    reasons = [f"{flagged} of {len(takes)} takes failed the speech check"] if flagged > FLAG_LIMIT * len(takes) else []
    return takes, reasons

