"""Measure a sound: where its hit starts and peaks, how loud it is, whether it clips."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

_WIN_S = 0.005
SR = 48000


@dataclass(frozen=True)
class Measure:
    onset_s: float
    peak_s: float
    duration_s: float
    peak_db: float
    rms_db: float
    clipped_samples: int


def _db(x: float) -> float:
    return float(20 * np.log10(max(x, 1e-6)))


def _decode(path: Path) -> tuple[np.ndarray, int]:
    """Measure at the mixer's 48 kHz, decoded by ffmpeg (the mixer's decoder and resampler), so a take's onset/peak are the ones the
    rendered mix will have. libsndfile and ffmpeg disagree on mp3 start padding by tens of ms; other sample rates shift the 5 ms grid."""
    if path.suffix.lower() in {".wav", ".flac"}:
        info = sf.info(str(path))
        if info.samplerate == SR:
            data, sr = sf.read(str(path), dtype="float32", always_2d=True)
            return data, sr
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "x.wav"
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", str(path), "-ar", str(SR), "-c:a", "pcm_f32le", str(wav)],
                       check=True, timeout=60)
        data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    return data, sr


def measure_take(path: Path) -> Measure:
    data, sr = _decode(Path(path))
    mono = data.mean(axis=1) if data.size else np.zeros(1, dtype=np.float32)
    duration = len(mono) / sr
    peak_amp = float(np.max(np.abs(data))) if data.size else 0.0
    rms_all = float(np.sqrt(np.mean(mono ** 2))) if mono.size else 0.0
    clipped = int(np.sum(np.abs(data) >= 0.999))
    if peak_amp < 1e-4:  # silent
        return Measure(0.0, 0.0, duration, _db(peak_amp), _db(rms_all), clipped)
    win = max(1, int(sr * _WIN_S))
    n = len(mono) // win
    env = np.sqrt(np.mean(mono[: n * win].reshape(n, win) ** 2, axis=1)) if n else np.array([peak_amp])
    first = int(np.argmax(env >= 0.1 * env.max()))
    lo = max(0, first * win - int(sr * 0.02))
    hi = min(len(mono), (first + 1) * win)
    idx = np.nonzero(np.abs(mono[lo:hi]) >= 0.02 * peak_amp)[0]
    onset = (lo + int(idx[0])) / sr if idx.size else first * win / sr
    smooth = max(1, int(round(0.02 / _WIN_S)))  # peak = centre of the loudest 20 ms
    sm = np.convolve(env, np.ones(smooth) / smooth, mode="same")
    # peak = energy-weighted centre of everything within 6 dB of the loudest point. The exact maximum flips between two
    # near-equal lobes when the sample rate or the 5 ms grid shifts a little; a centroid moves only as much as the sound does.
    idx = np.nonzero(sm >= 0.5 * sm.max())[0]
    w = sm[idx] ** 2
    peak = (float(np.sum(idx * w) / np.sum(w)) + 0.5) * win / sr
    return Measure(onset, peak, duration, _db(peak_amp), _db(rms_all), clipped)
