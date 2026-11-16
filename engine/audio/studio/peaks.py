"""Waveform peaks for drawing: max absolute sample per bin (0..1, absolute, so levels compare across sounds)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from engine.audio.studio.measure import _decode


def file_peaks(path: Path, bins: int) -> tuple[list[float], float]:
    data, sr = _decode(Path(path))
    mono = np.abs(data).max(axis=1) if data.size else np.zeros(1, dtype=np.float32)
    edges = np.linspace(0, len(mono), bins + 1).astype(int)
    peaks = [float(mono[a:b].max()) if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])]
    return [round(min(p, 1.0), 4) for p in peaks], len(mono) / sr
