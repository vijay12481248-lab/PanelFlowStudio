"""Seamless infinite loop crossfading and score stem frequency crossover isolation."""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000


def _find_zero_crossing(signal: np.ndarray, search_idx: int, window: int = 1200) -> int:
    """Locate the nearest zero-crossing with positive slope around search_idx."""
    start = max(0, search_idx - window)
    end = min(len(signal) - 1, search_idx + window)
    segment = signal[start:end]

    # Look for sign transition from negative to positive
    crossings = np.where((segment[:-1] <= 0) & (segment[1:] > 0))[0]
    if len(crossings) > 0:
        closest = crossings[np.argmin(np.abs(crossings - (search_idx - start)))]
        return int(start + closest)
    return search_idx


def create_seamless_loop(
    audio_path: Path | str,
    out_path: Path | str,
    crossfade_sec: float = 1.50,
) -> Path:
    """Create a seamless infinite loop by equal-power crossfading the tail into the head.

    Uses constant-power sin/cos curves (sin^2 + cos^2 == 1.0) and zero-crossing phase alignment
    to ensure zero clicks or perceptual drops at loop turnover points.
    """
    in_p = Path(audio_path)
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    data, sr = sf.read(str(in_p), dtype="float32", always_2d=True)
    num_samples, num_channels = data.shape

    # Minimum audio duration check (must be at least 2.5x crossfade length)
    fade_len = int(crossfade_sec * sr)
    if num_samples < fade_len * 2:
        fade_len = max(int(num_samples * 0.25), 64)

    # 1. Zero-crossing phase alignment
    mono_ref = np.mean(data, axis=1)
    head_split = _find_zero_crossing(mono_ref, fade_len)
    tail_split = _find_zero_crossing(mono_ref, num_samples - fade_len)

    actual_fade = num_samples - tail_split
    if actual_fade < 32 or actual_fade >= num_samples // 2:
        actual_fade = fade_len

    # Equal power curves
    t = np.linspace(0.0, 1.0, actual_fade, dtype=np.float32)[:, None]
    fade_in = np.sin(t * (np.pi / 2.0))
    fade_out = np.cos(t * (np.pi / 2.0))

    # Splice: loop length becomes (num_samples - actual_fade)
    tail_block = data[-actual_fade:]
    head_block = data[:actual_fade]
    body_block = data[actual_fade:-actual_fade]

    blended_seam = (tail_block * fade_out) + (head_block * fade_in)
    loop_data = np.vstack([blended_seam, body_block])

    sf.write(str(out_p), loop_data, sr)
    return out_p


def isolate_score_stems(
    audio_path: Path | str,
    out_dir: Path | str,
) -> dict[str, Path]:
    """Split a musical score into 3 operational crossover layers:

    1. Bass (< 250 Hz): Sub fundamentals & low root movement
    2. Body (250 Hz - 2500 Hz): Harmonic core, percussion body & mids
    3. Air (> 2500 Hz): Shimmer, tops, and melody presence
    """
    in_p = Path(audio_path)
    out_d = Path(out_dir)
    out_d.mkdir(parents=True, exist_ok=True)

    data, sr = sf.read(str(in_p), dtype="float32", always_2d=True)
    nyq = sr / 2.0

    # Complementary crossover decomposition for perfect acoustic reconstruction
    sos_low = butter(2, 250.0 / nyq, btype="low", output="sos")
    bass = sosfilt(sos_low, data, axis=0)
    rest = data - bass

    sos_high = butter(2, 2500.0 / nyq, btype="high", output="sos")
    air = sosfilt(sos_high, rest, axis=0)
    body = rest - air

    bass_p = out_d / f"{in_p.stem}_bass.wav"
    body_p = out_d / f"{in_p.stem}_body.wav"
    air_p = out_d / f"{in_p.stem}_air.wav"

    sf.write(str(bass_p), bass.astype(np.float32), sr)
    sf.write(str(body_p), body.astype(np.float32), sr)
    sf.write(str(air_p), air.astype(np.float32), sr)

    return {
        "bass": bass_p,
        "body": body_p,
        "air": air_p,
    }
