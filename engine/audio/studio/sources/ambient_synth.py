"""Physically-modeled parametric Ambient synthesizer: rain, wind, thunder, fire, night, and room tone (100% deterministic, zero VRAM, CC0)."""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

from engine.audio.studio.plan import Candidate, Cue, Provenance, SoundPlan
from engine.audio.studio.sources.base import Availability

SR = 48000
_MODEL = "panelflow-ambient-v1"

AMBIENT_KINDS = {
    "rain",
    "wind",
    "thunder",
    "fire",
    "night",
    "room_tone",
}

_DEFAULT_DUR = {
    "rain": 6.0,
    "wind": 6.0,
    "thunder": 4.5,
    "fire": 6.0,
    "night": 6.0,
    "room_tone": 6.0,
}


def _norm(x: np.ndarray, peak: float = 0.85) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


def _bandpass(data: np.ndarray, low_hz: float, high_hz: float, sr: int = SR, order: int = 2) -> np.ndarray:
    nyq = sr / 2.0
    low = max(10.0, low_hz) / nyq
    high = min(nyq - 10.0, high_hz) / nyq
    if low >= high:
        low = high * 0.5
    sos = butter(order, [low, high], btype="band", output="sos")
    return sosfilt(sos, data)


def _lowpass(data: np.ndarray, cutoff_hz: float, sr: int = SR, order: int = 2) -> np.ndarray:
    nyq = sr / 2.0
    cutoff = min(nyq - 10.0, max(20.0, cutoff_hz)) / nyq
    sos = butter(order, cutoff, btype="low", output="sos")
    return sosfilt(sos, data)


def render_rain(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Continuous steady rainfall with high-frequency droplet impacts."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    # 1. Continuous rain wash (shaped noise)
    noise = rng.standard_normal(n)
    wash = _bandpass(noise, 700, 4800, sr)

    # 2. Individual droplet clicks
    drops = np.zeros(n)
    num_drops = int(duration * 45)  # ~45 distinct droplets per second
    indices = rng.integers(0, max(1, n - 200), size=num_drops)
    for idx in indices:
        click_len = min(150, n - idx)
        ct = np.arange(click_len) / sr
        click = np.sin(2 * np.pi * rng.uniform(3200, 6500) * ct) * np.exp(-ct * 300)
        drops[idx:idx + click_len] += click * rng.uniform(0.2, 0.6)

    out = 0.75 * wash + 0.45 * drops
    # Smooth fade in and fade out
    fade_len = min(int(0.25 * sr), n // 2)
    out[:fade_len] *= np.linspace(0, 1, fade_len)
    out[-fade_len:] *= np.linspace(1, 0, fade_len)
    return _norm(out, peak=0.70)


def render_wind(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Atmospheric wind with natural gust modulation."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    # Low rumble base
    noise = rng.standard_normal(n)
    rumble = _lowpass(noise, 220, sr)

    # Mid wind whistle with gust envelope
    gust_freq = 0.18 + 0.08 * rng.random()
    gust = (0.5 + 0.5 * np.sin(2 * np.pi * gust_freq * t + rng.random() * 2 * np.pi)) ** 1.8
    whisper = _bandpass(noise, 350, 1200, sr) * gust

    out = 0.65 * rumble + 0.55 * whisper
    fade_len = min(int(0.3 * sr), n // 2)
    out[:fade_len] *= np.linspace(0, 1, fade_len)
    out[-fade_len:] *= np.linspace(1, 0, fade_len)
    return _norm(out, peak=0.75)


def render_thunder(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Dramatic distant thunder with initial crack and low rolling rumble tail."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    # 1. Initial shockwave crack
    noise = rng.standard_normal(n)
    crack_env = np.where(t < 0.08, t / 0.08, np.exp(-(t - 0.08) * 6.0))
    crack = _bandpass(noise, 200, 2400, sr) * crack_env

    # 2. Heavy sub-bass pitch dive (55 Hz -> 26 Hz)
    sub = np.sin(2 * np.pi * np.cumsum(26.0 + 35.0 * np.exp(-t * 2.5)) / sr) * np.exp(-t * 1.2)

    # 3. Rolling sub rumble tail
    tail_env = np.where(t < 0.15, 0.2 + 0.8 * (t / 0.15), np.exp(-(t - 0.15) * 0.95))
    tail_mod = 1.0 + 0.35 * np.sin(2 * np.pi * 3.5 * t)
    rumble = _lowpass(noise, 110, sr) * tail_env * tail_mod

    out = 0.6 * crack + 0.8 * sub + 0.9 * rumble
    return _norm(out, peak=0.85)


def render_fire(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Campfire / torch ambience: warm low rumble + sporadic sharp crackles."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    # Low warmth rumble
    noise = rng.standard_normal(n)
    warmth = _lowpass(noise, 240, sr) * (1.0 + 0.2 * np.sin(2 * np.pi * 1.5 * t))

    # Sparse sharp crackles
    crackles = np.zeros(n)
    num_crackles = int(duration * 12)
    c_indices = rng.integers(0, max(1, n - 100), size=num_crackles)
    for idx in c_indices:
        c_len = min(80, n - idx)
        pop = rng.standard_normal(c_len) * np.exp(-np.arange(c_len) / 8.0)
        crackles[idx:idx + c_len] += pop * rng.uniform(0.4, 0.9)

    out = 0.5 * warmth + 0.7 * crackles
    fade_len = min(int(0.2 * sr), n // 2)
    out[:fade_len] *= np.linspace(0, 1, fade_len)
    out[-fade_len:] *= np.linspace(1, 0, fade_len)
    return _norm(out, peak=0.70)


def render_night(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Peaceful night ambience: gentle crickets + quiet room tone floor."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    # 1. Cricket pulses (5 kHz sine pulsed at 5 Hz)
    cricket_f = 4900.0 + 150.0 * (rng.random() - 0.5)
    pulse = np.maximum(0, np.sin(2 * np.pi * 5.2 * t)) ** 3
    crickets = np.sin(2 * np.pi * cricket_f * t) * pulse * 0.4

    # 2. Very quiet low noise floor
    noise = rng.standard_normal(n)
    floor = _lowpass(noise, 300, sr) * 0.15

    out = crickets + floor
    fade_len = min(int(0.3 * sr), n // 2)
    out[:fade_len] *= np.linspace(0, 1, fade_len)
    out[-fade_len:] *= np.linspace(1, 0, fade_len)
    return _norm(out, peak=0.65)


def render_room_tone(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Subtle, warm diffuse room tone floor for indoor spaces."""
    n = max(int(duration * sr), 1)
    rng = np.random.default_rng(seed)

    noise = rng.standard_normal(n)
    out = _lowpass(noise, 180, sr)
    fade_len = min(int(0.3 * sr), n // 2)
    out[:fade_len] *= np.linspace(0, 1, fade_len)
    out[-fade_len:] *= np.linspace(1, 0, fade_len)
    return _norm(out, peak=0.60)


def render_ambient(kind: str, duration: float, seed: int, sr: int = SR) -> np.ndarray:
    if kind == "rain":
        return render_rain(duration, seed, sr)
    elif kind == "wind":
        return render_wind(duration, seed, sr)
    elif kind == "thunder":
        return render_thunder(duration, seed, sr)
    elif kind == "fire":
        return render_fire(duration, seed, sr)
    elif kind == "night":
        return render_night(duration, seed, sr)
    elif kind in ("room_tone", "interior", "noise_bed"):
        return render_room_tone(duration, seed, sr)
    else:
        raise ValueError(f"Unknown ambient kind {kind!r}")


def detect_ambient_kind(cue: Cue) -> str | None:
    target = f"{cue.kind} {cue.intent or ''}".lower()
    if any(k in target for k in ("rain", "storm", "downpour", "drizzle", "shower")):
        return "rain"
    if any(k in target for k in ("wind", "breeze", "gust", "stormy", "mountain")):
        return "wind"
    if any(k in target for k in ("thunder", "lightning", "storm_strike")):
        return "thunder"
    if any(k in target for k in ("fire", "flame", "campfire", "torch", "burning", "blaze")):
        return "fire"
    if any(k in target for k in ("night", "cricket", "dusk", "evening", "midnight")):
        return "night"
    if any(k in target for k in ("room", "interior", "hall", "indoor", "office", "dungeon", "castle", "ambient", "ambience")):
        return "room_tone"
    return None


class AmbientSynthProvider:
    name = "ambient"

    def availability(self) -> Availability:
        return Availability(True)

    def find(self, cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 3) -> list[Candidate]:
        kind = detect_ambient_kind(cue)
        if not kind:
            return []

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dur = _DEFAULT_DUR.get(kind, 6.0)
        if cue.t_out and cue.t_in and (cue.t_out > cue.t_in):
            dur = max(0.5, cue.t_out - cue.t_in)

        cands: list[Candidate] = []
        for i in range(limit):
            seed = 3000 + i * 41
            path = out_dir / f"{cue.id}_ambient_{kind}_{seed}.wav"
            data = render_ambient(kind, dur, seed)
            sf.write(str(path), data, SR)
            cands.append(
                Candidate(
                    id=uuid.uuid4().hex[:10],
                    path=str(path),
                    provider=self.name,
                    label=f"Ambient {kind.replace('_', ' ').title()} #{i + 1}",
                    provenance=Provenance(source="ambient", licence="CC0", model=_MODEL, seed=seed),
                )
            )
        return cands
