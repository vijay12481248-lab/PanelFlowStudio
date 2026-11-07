"""Weather sound for a silent clip, made locally from noise: rain, wind and thunder, with each thunderclap placed after a lightning flash SEEN in the clip.

Why: the storyboard clips are animated with a silent anchor (so H3 cannot invent speech) and the master only adds the narrator, so a storm showed lightning
in silence (measured on the second storm video). The layers come from the shot's own words (`Panel.atmosphere`, action, end state); a flash is a frame whose
brightness jumps well above the frames before it. No model, no download; the clip's own sound is kept when it has any.
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000
LAYERS = {
    "rain": re.compile(r"\b(rain\w*|drizzl\w*|shower\w*|downpour\w*|raindrop\w*|wet)\b", re.I),
    "wind": re.compile(r"\b(wind\w*|gust\w*|gale\w*|breez\w*|blow\w*|bend\w*|sway\w*)\b", re.I),
    "thunder": re.compile(r"\b(thunder\w*|lightning|bolt\w*|storm\w*)\b", re.I),
}
LEVEL_DB = {"air": -46.0, "rain": -30.0, "wind": -33.0}  # bed RMS; the narrator sits near -23 dB, so the weather stays under the voice
THUNDER_PEAK = 0.35


ENDED = re.compile(r"\b(\w+)\s+(?:stops|stopped|ends|ended|eases|eased|clears|cleared|dies down|died down|fades|faded|passes|passed)\b", re.I)


def layers(text: str) -> set[str]:
    text = ENDED.sub("", text)  # 'as rain stops' is not rain (measured: the rainbow shot got a rain bed)
    return {k for k, rx in LAYERS.items() if rx.search(text)}


def flashes(clip: Path, jump: float = 14.0, gap_s: float = 0.6) -> list[float]:
    """Seconds where a lightning flash starts: mean brightness at least `jump` grey levels over the median of the previous half second."""
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    lum = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        lum.append(float(cv2.cvtColor(cv2.resize(f, (160, 90)), cv2.COLOR_BGR2GRAY).mean()))
    cap.release()
    w = max(3, int(fps / 2))
    out: list[float] = []
    for i in range(w, len(lum)):
        if lum[i] - float(np.median(lum[i - w:i])) >= jump and (not out or i / fps - out[-1] >= gap_s):
            out.append(i / fps)
    return out


def _band(x: np.ndarray, lo: float | None, hi: float | None) -> np.ndarray:
    if lo and hi:
        sos = butter(2, [lo, hi], btype="band", fs=SR, output="sos")
    elif hi:
        sos = butter(2, hi, btype="low", fs=SR, output="sos")
    else:
        sos = butter(2, lo, btype="high", fs=SR, output="sos")
    return sosfilt(sos, x)


def _at(x: np.ndarray, db: float) -> np.ndarray:
    rms = float(np.sqrt(np.mean(x ** 2))) or 1e-9
    return x * (10 ** (db / 20) / rms)


def thunder(rng: np.random.Generator, seconds: float = 4.0) -> np.ndarray:
    """A crack (bright, short) then a rolling rumble (low, long decay)."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    crack = _band(rng.standard_normal(n), 300, 3000) * np.exp(-t / 0.08)
    roll = 1 + 0.6 * np.sin(2 * np.pi * rng.uniform(0.6, 1.4) * t + rng.uniform(0, 6))
    rumble = _band(rng.standard_normal(n), None, 140) * np.exp(-t / 1.4) * roll * np.minimum(1, t / 0.05)
    x = 0.35 * crack / (np.abs(crack).max() or 1) + rumble / (np.abs(rumble).max() or 1)
    return x / (np.abs(x).max() or 1)


def render(seconds: float, text: str, flash_times: list[float], seed: int = 0) -> np.ndarray:
    """Stereo float32 (n, 2): a quiet outdoor air bed, plus the layers the text names; thunder 0.4-1.2 s after each flash (sound travels slower than light),
    or one distant roll a third of the way in when the text names a storm but no flash is seen."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    want = layers(text)
    mix = np.zeros((n, 2))
    for ch in range(2):  # independent noise per channel: a wide, natural bed
        mix[:, ch] += _at(_band(rng.standard_normal(n), 200, 2500), LEVEL_DB["air"])
        if "rain" in want:
            drops = _band(rng.standard_normal(n), 1500, 9000) * (1 + 0.5 * (rng.random(n) > 0.997))
            mix[:, ch] += _at(drops, LEVEL_DB["rain"])
        if "wind" in want:
            t = np.arange(n) / SR
            gust = 0.55 + 0.45 * np.sin(2 * np.pi * 0.17 * t + rng.uniform(0, 6)) * np.sin(2 * np.pi * 0.05 * t + ch)
            mix[:, ch] += _at(_band(rng.standard_normal(n), None, 500) * gust, LEVEL_DB["wind"])
    if "thunder" in want:
        starts = [f + rng.uniform(0.4, 1.2) for f in flash_times] or [seconds / 3]
        for s in starts:
            a = int(s * SR)
            if a >= n:
                continue
            th = thunder(rng)[: n - a] * THUNDER_PEAK * (1.0 if flash_times else 0.5)
            mix[a:a + len(th)] += th[:, None]
    edge = min(n // 2, int(0.05 * SR))  # 50 ms fades: no click at the cut
    ramp = np.linspace(0, 1, edge)
    mix[:edge] *= ramp[:, None]
    mix[n - edge:] *= ramp[::-1, None]
    return np.clip(mix, -0.95, 0.95).astype(np.float32)


def clip_is_silent(clip: Path, db: float = -55.0) -> bool:
    import subprocess

    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(clip), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    return x.size == 0 or 20 * np.log10(float(np.sqrt(np.mean(x ** 2))) or 1e-9) < db


def ensure(clip: Path, text: str, out: Path, seconds: float, seed: int = 0) -> Path | None:
    """Write `out` (48 kHz stereo wav) for a silent clip; None when the clip has its own sound. Rebuilt when the clip is newer."""
    if out.exists() and out.stat().st_mtime >= clip.stat().st_mtime:
        return out
    if not clip_is_silent(clip):
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), render(seconds, text, flashes(clip) if "thunder" in layers(text) else [], seed), SR)
    return out
