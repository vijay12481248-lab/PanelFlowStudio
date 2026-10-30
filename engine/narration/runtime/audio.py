"""Local speech adapters (Kokoro TTS, faster-whisper STT) and signal helpers."""
from __future__ import annotations

import os
import re
import tempfile
import wave
from pathlib import Path
from typing import Protocol

import numpy as np

from engine.narration.artifacts import Word
from engine.narration.runtime.roles import load_stt_config

SR = 24000
PAD_MS = 80
_FRAME_MS = 20


class Tts(Protocol):
    def synth(self, text: str, voice: str, rate: float) -> np.ndarray: ...


class Stt(Protocol):
    def words(self, wav_path: Path) -> tuple[str, list[Word]]: ...


_pipeline = None
_whisper = None


class KokoroTts:
    def synth(self, text: str, voice: str, rate: float) -> np.ndarray:
        global _pipeline
        if _pipeline is None:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")  # models are cached; never reach the network
            from kokoro import KPipeline  # lazy: heavy import

            _pipeline = KPipeline(lang_code="a")
        chunks = [np.asarray(a.cpu() if hasattr(a, "cpu") else a, dtype=np.float32).reshape(-1)
                  for _, _, a in _pipeline(text, voice=voice, speed=rate) if a is not None]
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


class WhisperStt:
    def words(self, wav_path: Path) -> tuple[str, list[Word]]:
        global _whisper
        if _whisper is None:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from faster_whisper import WhisperModel  # lazy: heavy import

            cfg = load_stt_config()
            _whisper = WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)
        segments, _ = _whisper.transcribe(str(wav_path), word_timestamps=True, language="en")
        words = [Word(text=w.word.strip(), start=w.start, end=max(w.end, w.start))
                 for s in segments for w in (s.words or []) if w.word.strip()]
        return " ".join(w.text for w in words), words


def release_audio_models() -> None:
    global _pipeline, _whisper
    _pipeline = _whisper = None


def normalize_silence(audio: np.ndarray, sr: int = SR, pad_ms: int = PAD_MS,
                      thresh_db: float = -40.0) -> tuple[np.ndarray, int, int]:
    frame = sr * _FRAME_MS // 1000
    if len(audio) < frame:  # shorter than one frame: judge it as a single frame
        frame = max(len(audio), 1)
    n = len(audio) // frame
    rms = np.sqrt((audio[: n * frame].reshape(n, frame).astype(np.float64) ** 2).mean(axis=1))
    loud = np.flatnonzero(rms > 10 ** (thresh_db / 20))
    if loud.size == 0:
        raise ValueError("take is silent")
    start, end = int(loud[0]) * frame, (int(loud[-1]) + 1) * frame
    end = len(audio) if loud[-1] == n - 1 else end  # keep the sub-frame remainder after the last full frame
    pad = np.zeros(sr * pad_ms // 1000, dtype=np.float32)
    out = np.concatenate([pad, audio[start:end].astype(np.float32), pad])
    return out, start * 1000 // sr, (len(audio) - end) * 1000 // sr


def write_wav_atomic(path: Path, audio: np.ndarray, sr: int = SR) -> float:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f, wave.open(f, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return len(audio) / sr


def _tokens(s: str) -> list[str]:
    return re.sub(r"[^\w\s']", " ", s.lower()).split()


def wer(ref: str, hyp: str) -> float:
    r, h = _tokens(ref), _tokens(hyp)
    if not r:
        raise ValueError("reference is empty")
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i]
        for j, hw in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw)))
        prev = cur
    return prev[-1] / len(r)
