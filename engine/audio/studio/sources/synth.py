"""Effects synthesised in code: deterministic per seed, no samples, so no licence to worry about (CC0)."""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, sosfilt_zi

from engine.audio.studio.plan import Candidate, Cue, Provenance, SoundPlan
from engine.audio.studio.sources.base import Availability

SR = 48000
SYNTH_KINDS = {"whoosh", "impact", "click", "pop", "ding", "riser", "drop", "noise_bed"}
_DEFAULT_DUR = {"whoosh": 1.0, "impact": 1.2, "click": 0.15, "pop": 0.2, "ding": 1.5, "riser": 2.0, "drop": 1.5, "noise_bed": 5.0}
_MODEL = "panelflow-synth-v1"


def _t(n: int, sr: int) -> np.ndarray:
    return np.arange(n) / sr


def _sweep_noise(rng, n: int, sr: int, f0: float, f1: float, q: float = 1.5) -> np.ndarray:
    """White noise through a band-pass whose centre glides f0 -> f1 (filter state carried between 10 ms chunks)."""
    noise = rng.standard_normal(n).astype(np.float64)
    out = np.zeros(n)
    chunk = sr // 100
    zi = None
    for i in range(0, n, chunk):
        f = f0 * (f1 / f0) ** (i / max(n - 1, 1))
        sos = butter(2, [f / q / 1.5 / (sr / 2) + 1e-4, min(f * 1.5 / (sr / 2), 0.99)], btype="band", output="sos")
        if zi is None:
            zi = sosfilt_zi(sos) * 0
        seg, zi = sosfilt(sos, noise[i:i + chunk], zi=zi)
        out[i:i + chunk] = seg
    return out


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


def render(kind: str, duration: float, seed: int, sr: int = SR) -> np.ndarray:
    if kind not in SYNTH_KINDS:
        raise ValueError(f"unknown synth kind {kind!r}")
    n = max(int(duration * sr), 1)
    t = _t(n, sr)
    rng = np.random.default_rng(seed)
    j = 1 + 0.12 * (rng.random() - 0.5)  # per-seed pitch jitter so tonal variants differ
    if kind == "whoosh":  # swell peaking at ~65 %
        env = np.where(t / duration < 0.65, (t / duration / 0.65) ** 2, ((1 - t / duration) / 0.35) ** 1.5)
        x = _sweep_noise(rng, n, sr, 300, 4000) * env
    elif kind == "riser":  # builds to the end
        x = _sweep_noise(rng, n, sr, 200, 6000) * (t / duration) ** 2.5
        x[-int(0.02 * sr):] *= np.linspace(1, 0, int(0.02 * sr))
    elif kind == "impact":  # instant attack, sub thump + noise crack
        thump = np.sin(2 * np.pi * (45 * j + 60 * np.exp(-t * 30)) * t) * np.exp(-t * 5)
        crack = _sweep_noise(rng, n, sr, 1500, 800) * np.exp(-t * 60)
        x = thump + 0.6 * crack
    elif kind == "drop":
        x = np.sin(2 * np.pi * np.cumsum(30 * j + 110 * np.exp(-t * 6)) / sr) * np.exp(-t * 3)
    elif kind == "click":
        x = _sweep_noise(rng, n, sr, 3500, 3000) * np.exp(-t * 400) + 0.4 * np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 90)
    elif kind == "pop":
        x = np.sin(2 * np.pi * np.cumsum(180 * j + 520 * np.exp(-t * 55)) / sr) * np.exp(-t * 28)
        x[: int(0.002 * sr)] *= np.linspace(0, 1, int(0.002 * sr))
    elif kind == "ding":
        x = sum(a * np.sin(2 * np.pi * 1400 * j * m * t) * np.exp(-t * d) for m, a, d in ((1, 1, 2.5), (2.76, 0.5, 4), (5.4, 0.25, 7)))
    else:  # noise_bed: soft brown-ish noise, gentle fade in and out so a bed never clicks
        x = np.cumsum(rng.standard_normal(n))
        x = x - np.convolve(x, np.ones(2000) / 2000, mode="same")
        f = min(int(0.3 * sr), n // 2)
        x[:f] *= np.linspace(0, 1, f)
        x[-f:] *= np.linspace(1, 0, f)
    return _norm(np.asarray(x))


class SynthProvider:
    name = "synth"

    def availability(self) -> Availability:
        return Availability(True)

    def find(self, cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 3) -> list[Candidate]:
        if cue.kind not in SYNTH_KINDS:
            return []
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dur = _DEFAULT_DUR[cue.kind]
        if cue.kind == "noise_bed" and cue.t_out:
            dur = max(cue.t_out - cue.t_in, 0.5)
        cands = []
        for i in range(limit):
            seed = 1000 + i
            path = out_dir / f"{cue.id}_synth_{cue.kind}_{seed}.wav"
            sf.write(str(path), render(cue.kind, dur, seed), SR)
            cands.append(Candidate(id=uuid.uuid4().hex[:10], path=str(path), provider=self.name, label=f"{cue.kind} #{i + 1}",
                                   provenance=Provenance(source="synth", licence="CC0", model=_MODEL, seed=seed)))
        return cands
