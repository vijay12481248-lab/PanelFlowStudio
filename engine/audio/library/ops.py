"""Sound edit operations: each takes float samples (n, channels) at 48 kHz and returns new samples. Nothing is overwritten; the store keeps versions.

Cutting, silencing, fades, gain, reverse and loops are exact numpy work; filters (loudness, speed, pitch, EQ, reverb, clean-up) run through ffmpeg.
An operation with a selection [a, b] works on that part only and is joined back with 10 ms cross-fades, so there are no clicks.
Parameters come from REST/MCP: every one is checked against OPS (numbers clamped to their range, choices from a list), never passed through as text.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

SR = 48000
XFADE_S = 0.01

# name -> group, label, selection ("none": whole sound only, "needs": a selection is required, "any": selection or whole), params {name: spec}
# a spec is (min, max, default) for a number or a list of choices (first is the default)
OPS: dict[str, dict[str, Any]] = {
    "trim": {"group": "Edit", "label": "Keep only the selection", "selection": "needs", "params": {}},
    "delete": {"group": "Edit", "label": "Delete the selection", "selection": "needs", "params": {}},
    "silence": {"group": "Edit", "label": "Silence the selection", "selection": "needs", "params": {}},
    "insert_silence": {"group": "Edit", "label": "Insert silence at the playhead", "selection": "none", "params": {"at": (0.0, 3600.0, 0.0), "seconds": (0.05, 30.0, 1.0)}},
    "loop": {"group": "Edit", "label": "Repeat", "selection": "any", "params": {"times": (2, 50, 2)}},
    "gain": {"group": "Volume", "label": "Gain", "selection": "any", "params": {"db": (-40.0, 24.0, 3.0)}},
    "normalize": {"group": "Volume", "label": "Normalize", "selection": "none", "params": {"mode": ["loudness", "peak"], "target": (-36.0, -0.1, -16.0)}},
    "fade_in": {"group": "Volume", "label": "Fade in", "selection": "any", "params": {"seconds": (0.01, 30.0, 0.5)}},
    "fade_out": {"group": "Volume", "label": "Fade out", "selection": "any", "params": {"seconds": (0.01, 30.0, 0.5)}},
    "speed": {"group": "Time and pitch", "label": "Speed (keeps pitch)", "selection": "any", "params": {"factor": (0.5, 2.0, 1.1)}},
    "pitch": {"group": "Time and pitch", "label": "Pitch (keeps length)", "selection": "any", "params": {"semitones": (-12.0, 12.0, 2.0)}},
    "reverse": {"group": "Time and pitch", "label": "Reverse", "selection": "any", "params": {}},
    "eq": {"group": "Effects", "label": "EQ", "selection": "any",
           "params": {"preset": ["custom", "bass_cut", "warm", "bright", "telephone", "radio"], "bass": (-15.0, 15.0, 0.0), "mid": (-15.0, 15.0, 0.0), "treble": (-15.0, 15.0, 0.0)}},
    "reverb": {"group": "Effects", "label": "Reverb", "selection": "any", "params": {"room": ["room", "hall"]}},
    "echo": {"group": "Effects", "label": "Echo", "selection": "any", "params": {"delay_ms": (50.0, 2000.0, 350.0), "decay": (0.05, 0.9, 0.4)}},
    "compressor": {"group": "Effects", "label": "Compressor", "selection": "any", "params": {"amount": ["light", "strong"]}},
    "denoise": {"group": "Clean up", "label": "Reduce noise", "selection": "any", "params": {"amount": ["light", "strong"]}},
    "deess": {"group": "Clean up", "label": "De-ess (soften s sounds)", "selection": "any", "params": {}},
    "remove_silence": {"group": "Clean up", "label": "Shorten long silences", "selection": "none", "params": {"longer_than": (0.2, 5.0, 0.6), "keep": (0.05, 1.0, 0.25)}},
    "hum": {"group": "Clean up", "label": "Remove hum", "selection": "any", "params": {"mains": ["50", "60"]}},
}

_EQ_PRESETS = {
    "bass_cut": "highpass=f=100",
    "warm": "equalizer=f=200:width_type=q:width=1:g=3,equalizer=f=6000:width_type=q:width=1:g=-3",
    "bright": "equalizer=f=5000:width_type=q:width=0.8:g=4",
    "telephone": "highpass=f=300,lowpass=f=3400",
    "radio": "highpass=f=500,lowpass=f=4000,acompressor=threshold=-20dB:ratio=4:makeup=2",
}


def clean_params(op: str, params: dict | None) -> dict[str, Any]:
    """The operation's parameters with defaults filled in, numbers clamped and choices checked. Unknown names are refused."""
    if op not in OPS:
        raise ValueError(f"unknown operation {op!r}; known: {', '.join(OPS)}")
    spec, given = OPS[op]["params"], dict(params or {})
    extra = set(given) - set(spec)
    if extra:
        raise ValueError(f"{op} has no parameter {', '.join(sorted(extra))}")
    out: dict[str, Any] = {}
    for name, s in spec.items():
        v = given.get(name)
        if isinstance(s, list):
            v = s[0] if v is None else str(v)
            if v not in s:
                raise ValueError(f"{op}.{name} must be one of {', '.join(s)}")
        else:
            lo, hi, default = s
            try:
                v = default if v is None else float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{op}.{name} must be a number")
            if not math.isfinite(v):
                raise ValueError(f"{op}.{name} must be a number")
            v = min(max(v, lo), hi)
            if isinstance(default, int):
                v = int(round(v))
        out[name] = v
    return out


def ops_catalog() -> list[dict[str, Any]]:
    """The list the UI and agents read: one source for names, groups and ranges."""
    def p(s):
        return {"choices": s} if isinstance(s, list) else {"min": s[0], "max": s[1], "default": s[2]}
    return [{"op": k, "group": v["group"], "label": v["label"], "selection": v["selection"], "params": {n: p(s) for n, s in v["params"].items()}} for k, v in OPS.items()]


def _ramp(n: int) -> np.ndarray:
    return np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]


def join(parts: list[np.ndarray], sr: int = SR) -> np.ndarray:
    """Concatenate with a short equal-length cross-fade at each join (only where both sides are long enough)."""
    parts = [p for p in parts if len(p)]
    if not parts:
        return np.zeros((0, 1), dtype=np.float32)
    out = parts[0]
    for p in parts[1:]:
        n = min(int(XFADE_S * sr), len(out) // 2, len(p) // 2)
        if n < 2:
            out = np.concatenate([out, p])
            continue
        r = _ramp(n)
        mid = out[-n:] * (1 - r) + p[:n] * r
        out = np.concatenate([out[:-n], mid, p[n:]])
    return out.astype(np.float32)


def noise_floor_db(x: np.ndarray, sr: int = SR) -> float:
    w = max(int(0.05 * sr), 1)
    r = [float(np.sqrt(np.mean(np.square(x[i:i + w])))) for i in range(0, max(len(x) - w, 1), w)]
    return float(20 * np.log10(max(np.percentile(r, 10), 1e-6)))


def _ffmpeg(x: np.ndarray, sr: int, af: str) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="pf-audio-op-") as tmp:
        src, dst = Path(tmp) / "in.wav", Path(tmp) / "out.wav"
        sf.write(str(src), x, sr, subtype="FLOAT")
        p = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", af, "-ar", str(sr), "-ac", str(x.shape[1]),
                            "-c:a", "pcm_f32le", str(dst)], capture_output=True, text=True, timeout=600)
        if p.returncode != 0 or not dst.is_file():
            raise RuntimeError(f"ffmpeg failed: {p.stderr.strip()[-300:]}")
        y, _ = sf.read(str(dst), dtype="float32", always_2d=True)
    return y


def _has_rubberband() -> bool:
    try:
        out = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return False
    return " rubberband " in out


def _atempo_chain(f: float) -> str:
    parts = []
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    parts.append(f"atempo={f:.5f}")
    return ",".join(parts)


def _filter(op: str, p: dict[str, Any], x: np.ndarray, sr: int, whole: bool) -> str:
    if op == "normalize":
        return f"loudnorm=I={p['target']:.1f}:TP=-1.5:LRA=11"
    if op == "speed":
        return f"rubberband=tempo={p['factor']:.5f}" if _has_rubberband() else _atempo_chain(p["factor"])
    if op == "pitch":
        r = 2 ** (p["semitones"] / 12)
        if _has_rubberband():
            return f"rubberband=pitch={r:.6f}:pitchq=quality"
        return f"asetrate={sr * r:.0f},aresample={sr}," + _atempo_chain(1 / r)   # shortcut: lower quality without rubberband
    if op == "eq":
        if p["preset"] != "custom":
            return _EQ_PRESETS[p["preset"]]
        return ",".join(f"equalizer=f={f}:width_type=q:width=0.8:g={p[k]:.1f}" for k, f in (("bass", 100), ("mid", 1000), ("treble", 8000)))
    if op == "echo":
        return f"aecho=0.8:0.8:{p['delay_ms']:.0f}:{p['decay']:.2f}"
    if op == "compressor":
        return "acompressor=threshold=-18dB:ratio=3:attack=10:release=200:makeup=2" if p["amount"] == "light" else \
            "acompressor=threshold=-26dB:ratio=6:attack=5:release=150:makeup=4"
    if op == "denoise":
        # afftdn only works when nf sits at the real noise: measured on a Kokoro line + white noise at -34 dBFS, nf=-50 (default) removed 0.2 dB,
        # nf = floor + 9 removed 40 dB. The floor is the quietest 10% of 50 ms windows.
        nf = min(max(noise_floor_db(x, sr) + 9, -80.0), -20.0)
        return f"afftdn=nr={12 if p['amount'] == 'light' else 40}:nf={nf:.1f}"
    if op == "deess":
        return "deesser"
    if op == "remove_silence":
        return f"silenceremove=stop_periods=-1:stop_duration={p['longer_than']:.2f}:stop_threshold=-45dB:stop_silence={p['keep']:.2f}"
    if op == "hum":
        f0 = int(p["mains"])
        return "highpass=f=40," + ",".join(f"bandreject=f={f0 * k}:width_type=q:width=10" for k in (1, 2, 3))
    raise ValueError(op)


_RT60 = {"room": (0.5, 0.010, 0.22), "hall": (1.8, 0.025, 0.32)}   # seconds to fall 60 dB, pre-delay, wet level


def _reverb(x: np.ndarray, sr: int, room: str, tail: bool) -> np.ndarray:
    """Convolution with a decaying-noise impulse response (fixed seed, so the same sound gives the same result)."""
    from scipy.signal import fftconvolve
    rt60, pre, wet = _RT60[room]
    n = int(rt60 * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(7)
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)   # -60 dB at rt60
    ir = np.concatenate([np.zeros(int(pre * sr)), ir / np.sqrt(np.sum(ir ** 2))]).astype(np.float32)
    y = np.stack([fftconvolve(x[:, c], ir) for c in range(x.shape[1])], axis=1).astype(np.float32)
    dry = np.concatenate([x, np.zeros((len(y) - len(x), x.shape[1]), np.float32)])
    out = dry * np.float32(1 - wet * 0.5) + y * np.float32(wet)
    if not tail:
        return out[:len(x)]
    loud = np.flatnonzero(np.abs(out).max(axis=1) > 10 ** (-70 / 20))   # keep the tail until it falls below -70 dBFS
    return out[:max(len(x), int(loud[-1]) + 1 if len(loud) else len(x))]


def _region(x: np.ndarray, sr: int, op: str, p: dict[str, Any], whole: bool) -> np.ndarray:
    """The operation applied to a whole piece of sound (the selection, or the whole sound)."""
    if op == "loop":
        return join([x] * p["times"], sr)
    if op == "gain":
        return x * np.float32(10 ** (p["db"] / 20))
    if op in ("fade_in", "fade_out"):
        n = len(x) if not whole else min(len(x), int(p["seconds"] * sr))
        y = x.copy()
        r = _ramp(n)
        if op == "fade_in":
            y[:n] *= r
        else:
            y[len(y) - n:] *= r[::-1]
        return y
    if op == "reverse":
        return x[::-1].copy()
    if op == "normalize" and p["mode"] == "peak":
        peak = float(np.abs(x).max()) if x.size else 0.0
        return x if peak < 1e-6 else x * np.float32(10 ** (p["target"] / 20) / peak)
    if op == "reverb":
        return _reverb(x, sr, p["room"], tail=whole)
    if op == "denoise":   # afftdn delays its output by 1200 samples (measured at 48 kHz): pad, then drop the delay so the sound stays in sync
        lat = 1200
        y = _ffmpeg(np.concatenate([x, np.zeros((lat, x.shape[1]), np.float32)]), sr, _filter(op, p, x, sr, whole))
        return y[lat:lat + len(x)]
    return _ffmpeg(x, sr, _filter(op, p, x, sr, whole))


def apply(op: str, x: np.ndarray, sr: int = SR, params: dict | None = None, a: float | None = None, b: float | None = None) -> np.ndarray:
    """Run one operation. x is float32 (n, channels). a/b in seconds select a part of the sound."""
    p = clean_params(op, params)
    rule = OPS[op]["selection"]
    total = len(x) / sr
    has_sel = a is not None and b is not None
    if has_sel:
        a, b = sorted((max(0.0, float(a)), min(total, float(b))))
        if b - a < 1 / sr * 2:
            raise ValueError("the selection is empty")
    if rule == "needs" and not has_sel:
        raise ValueError(f"{OPS[op]['label']}: select a part of the sound first")
    if rule == "none":
        has_sel = False
    if op == "insert_silence":
        i = int(min(max(p["at"], 0.0), total) * sr)
        head, tail = x[:i].copy(), x[i:].copy()
        n = min(int(XFADE_S * sr / 2), len(head), len(tail))   # short fades into and out of the gap, the length stays exact
        if n >= 2:
            head[len(head) - n:] *= _ramp(n)[::-1]
            tail[:n] *= _ramp(n)
        return np.concatenate([head, np.zeros((int(p["seconds"] * sr), x.shape[1]), dtype=np.float32), tail])
    if not has_sel:
        return _region(x, sr, op, p, whole=True).astype(np.float32)
    ia, ib = int(round(a * sr)), int(round(b * sr))
    before, mid, after = x[:ia], x[ia:ib], x[ib:]
    if op == "trim":
        return mid.copy()
    if op == "delete":
        return join([before, after], sr)
    new = np.zeros_like(mid) if op == "silence" else _region(mid, sr, op, p, whole=False).astype(np.float32)
    if op not in ("speed", "loop"):   # filters (echo, pitch) may add or lose a few samples: the selection keeps its length
        new = new[:len(mid)] if len(new) >= len(mid) else np.concatenate([new, np.zeros((len(mid) - len(new), new.shape[1]), np.float32)])
    if len(new) != len(mid):   # speed, loop: the length changes, so the parts are joined with overlaps
        return join([before, new, after], sr)
    y = x.copy()   # same length: blend old -> new at both edges of the selection, the sound keeps its exact length
    n = min(int(XFADE_S * sr), len(mid) // 2)
    if n >= 2:
        r = _ramp(n)
        new[:n] = mid[:n] * (1 - r) + new[:n] * r
        new[-n:] = new[-n:] * (1 - r) + mid[-n:] * r
    y[ia:ib] = new
    return y
