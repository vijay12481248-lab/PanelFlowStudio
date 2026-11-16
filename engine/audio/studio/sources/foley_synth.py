"""Physically-modeled parametric Foley synthesizer: footsteps, cloth rustle, blade resonance, heavy impacts, and explosions (100% deterministic, zero VRAM, CC0)."""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

from engine.audio.studio.plan import Candidate, Cue, Provenance, SoundPlan
from engine.audio.studio.sources.base import Availability

SR = 48000
_MODEL = "panelflow-foley-v1"

FOLEY_KINDS = {
    "footstep",
    "cloth_rustle",
    "blade_clash",
    "sword_ring",
    "heavy_impact",
    "explosion",
}

_DEFAULT_DUR = {
    "footstep": 0.35,
    "cloth_rustle": 0.50,
    "blade_clash": 1.80,
    "sword_ring": 2.20,
    "heavy_impact": 1.60,
    "explosion": 3.00,
}


def _norm(x: np.ndarray, peak: float = 0.90) -> np.ndarray:
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


def render_footstep(surface: str, duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Physically modeled footfall transient + surface texture response."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    # Heel thump (pitch envelope dropping 140 Hz -> 50 Hz)
    thump_freq = 110.0 + 30.0 * (rng.random() - 0.5)
    thump = np.sin(2 * np.pi * (thump_freq * np.exp(-t * 45)) * t) * np.exp(-t * 28)

    # Surface acoustic noise
    raw_noise = rng.standard_normal(n)
    if "wood" in surface:
        # Wood floor cavity resonance
        texture = _bandpass(raw_noise, 300, 1200, sr) * np.exp(-t * 35)
        out = 0.7 * thump + 0.5 * texture
    elif "dirt" in surface or "gravel" in surface:
        # Granular crunch
        crunch = _bandpass(raw_noise, 800, 3200, sr) * np.exp(-t * 22)
        out = 0.5 * thump + 0.8 * crunch
    elif "water" in surface:
        # Splash transient
        spray = _bandpass(raw_noise, 1500, 6000, sr) * np.exp(-t * 18)
        bubble = np.sin(2 * np.pi * (800 * np.exp(-t * 30)) * t) * np.exp(-t * 20)
        out = 0.3 * thump + 0.5 * bubble + 0.7 * spray
    else:
        # Default concrete / hard sole
        click = _bandpass(raw_noise, 1800, 4500, sr) * np.exp(-t * 80)
        out = 0.8 * thump + 0.6 * click

    return _norm(out)


def render_cloth_rustle(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Cloth / fabric handling rustle modeled with filtered noise envelope."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    raw_noise = rng.standard_normal(n)
    # Bandpass filtered between 600 Hz and 3500 Hz
    filtered = _bandpass(raw_noise, 600, 3500, sr)
    # Dynamic envelope with natural swell (attack ~20%, decay ~80%)
    env = np.where(t / duration < 0.25, (t / (duration * 0.25)) ** 1.5, ((1.0 - t / duration) / 0.75) ** 1.8)
    # Add subtle secondary micro-swells
    subtle_jitter = 1.0 + 0.2 * np.sin(2 * np.pi * 14 * t)
    out = filtered * env * subtle_jitter
    return _norm(out)


def render_blade_resonance(is_clash: bool, duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Metallic sword clash and inharmonic resonant ringing."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    # Inharmonic metallic partials: fundamental ~2200 Hz, partials at non-integer ratios
    base_f = 2150.0 + 80.0 * (rng.random() - 0.5)
    partials = [
        (1.00, 1.0, 3.2),    # fundamental
        (1.58, 0.65, 4.0),   # second mode
        (2.32, 0.40, 5.5),   # third mode
        (3.41, 0.25, 7.5),   # high shimmer
        (4.18, 0.15, 9.0),   # ringing edge
    ]

    ring = np.zeros(n)
    for freq_mult, amp, decay in partials:
        freq = base_f * freq_mult
        ring += amp * np.sin(2 * np.pi * freq * t) * np.exp(-t * decay)

    if is_clash:
        # Sharp wideband impact transient at onset
        noise = rng.standard_normal(n)
        clack = _bandpass(noise, 1500, 8000, sr) * np.exp(-t * 120)
        thud = np.sin(2 * np.pi * 180 * np.exp(-t * 60) * t) * np.exp(-t * 40)
        out = 0.7 * clack + 0.4 * thud + 0.8 * ring
    else:
        # Pure unsheathe / shimmer ring
        out = ring

    return _norm(out)


def render_heavy_impact(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Deep cinematic heavy body/object impact with sub-bass drop."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    # Sub-bass sine pitch dive (85 Hz -> 32 Hz)
    sub = np.sin(2 * np.pi * np.cumsum(32.0 + 55.0 * np.exp(-t * 12)) / sr) * np.exp(-t * 3.5)
    # Impact transient
    noise = rng.standard_normal(n)
    crack = _bandpass(noise, 800, 4500, sr) * np.exp(-t * 50)
    low_rumble = _lowpass(noise, 120, sr) * np.exp(-t * 4.0)

    out = 0.9 * sub + 0.5 * crack + 0.4 * low_rumble
    return _norm(out)


def render_explosion(duration: float, seed: int, sr: int = SR) -> np.ndarray:
    """Cinematic detonation: initial shockwave impulse, expanding sub rumble, and debris tail."""
    n = max(int(duration * sr), 1)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)

    noise = rng.standard_normal(n)
    # 1. Shockwave impulse
    impulse = np.sin(2 * np.pi * 45 * t) * np.exp(-t * 15)
    # 2. Heavy sub rumble (<90 Hz)
    sub_rumble = _lowpass(noise, 85, sr) * np.exp(-t * 1.5)
    # 3. Fireball blast envelope (attack ~30ms, long decay)
    fireball_env = np.where(t < 0.03, t / 0.03, np.exp(-(t - 0.03) * 2.2))
    fireball = _bandpass(noise, 150, 1200, sr) * fireball_env
    # 4. High-frequency debris / crackle tail
    debris_env = np.where(t < 0.1, 0.0, np.exp(-(t - 0.1) * 1.8))
    debris = _bandpass(noise, 2500, 7500, sr) * debris_env * (1.0 + 0.4 * rng.standard_normal(n))

    out = 0.8 * impulse + 0.9 * sub_rumble + 0.7 * fireball + 0.4 * debris
    return _norm(out)


def render_foley(kind: str, duration: float, seed: int, sr: int = SR, surface: str = "wood") -> np.ndarray:
    """Dispatch procedural rendering for Foley kind."""
    if kind == "footstep":
        return render_footstep(surface, duration, seed, sr)
    elif kind == "cloth_rustle":
        return render_cloth_rustle(duration, seed, sr)
    elif kind == "blade_clash":
        return render_blade_resonance(True, duration, seed, sr)
    elif kind == "sword_ring":
        return render_blade_resonance(False, duration, seed, sr)
    elif kind == "heavy_impact":
        return render_heavy_impact(duration, seed, sr)
    elif kind == "explosion":
        return render_explosion(duration, seed, sr)
    else:
        raise ValueError(f"Unknown foley kind {kind!r}")


def detect_foley_kind(cue: Cue) -> str | None:
    """Determine matching Foley kind from cue kind or intent text."""
    target = f"{cue.kind} {cue.intent or ''}".lower()
    if any(k in target for k in ("footstep", "step", "walk", "tread", "boot", "shoe")):
        return "footstep"
    if any(k in target for k in ("cloth", "rustle", "fabric", "jacket", "coat", "movement")):
        return "cloth_rustle"
    if any(k in target for k in ("blade", "sword", "katana", "clash", "parry", "steel")):
        return "blade_clash"
    if any(k in target for k in ("sword_ring", "sheathe", "unsheathe", "ring", "blade_ring")):
        return "sword_ring"
    if any(k in target for k in ("heavy_impact", "slam", "smash", "thud", "bodyfall", "punch", "strike")):
        return "heavy_impact"
    if any(k in target for k in ("explosion", "blast", "detonation", "bomb", "explode", "grenade")):
        return "explosion"
    return None


class FoleySynthProvider:
    name = "foley"

    def availability(self) -> Availability:
        return Availability(True)

    def find(self, cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 3) -> list[Candidate]:
        kind = detect_foley_kind(cue)
        if not kind:
            return []

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dur = _DEFAULT_DUR.get(kind, 1.0)
        if cue.t_out and cue.t_in and (cue.t_out > cue.t_in):
            dur = max(0.2, min(cue.t_out - cue.t_in, 8.0))

        # Detect surface hint for footstep
        surface = "wood"
        target_text = f"{cue.kind} {cue.intent or ''}".lower()
        for s in ("concrete", "dirt", "gravel", "water", "wood"):
            if s in target_text:
                surface = s
                break

        cands: list[Candidate] = []
        for i in range(limit):
            seed = 2000 + i * 37
            path = out_dir / f"{cue.id}_foley_{kind}_{seed}.wav"
            data = render_foley(kind, dur, seed, surface=surface)
            sf.write(str(path), data, SR)
            cands.append(
                Candidate(
                    id=uuid.uuid4().hex[:10],
                    path=str(path),
                    provider=self.name,
                    label=f"Foley {kind.replace('_', ' ').title()} #{i + 1}",
                    provenance=Provenance(source="foley", licence="CC0", model=_MODEL, seed=seed),
                )
            )
        return cands
