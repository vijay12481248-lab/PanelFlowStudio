"""
Adobe After Effects Expressions Engine.
Implements After Effects expression language primitives:
- wiggle(freq, amp, octaves, amp_mult, t)
- inertia_bounce(t, t_key, val_start, val_end, amp, freq, decay)
- loop_out(keyframes, t_sec, total_duration, loop_type)
- linear(), ease(), ease_in(), ease_out()
- value_at_time() for leader-follower delay
"""

from __future__ import annotations

import math
from typing import Callable, List, Dict, Any, Optional
from engine.render.motion.curves import clamp


# ── Continuous Gradient Noise for Wiggle ─────────────────────────────────────

def _gradient_noise_1d(x: float, seed: int = 0) -> float:
    """1D gradient noise (smooth C2 continuous interpolation between random integer gradients)."""
    i0 = math.floor(x)
    i1 = i0 + 1
    f = x - i0

    # Quintic smootherstep fade curve: 6f^5 - 15f^4 + 10f^3
    fade = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)

    # Deterministic pseudo-random gradient slopes from hash
    def hash_grad(idx: int) -> float:
        h = ((idx + seed * 997) * 374761393) & 0xFFFFFFFF
        h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
        val = (h ^ (h >> 16)) / 2147483648.0 - 1.0
        return val

    g0 = hash_grad(i0)
    g1 = hash_grad(i1)

    d0 = g0 * f
    d1 = g1 * (f - 1.0)
    return (d0 + (d1 - d0) * fade) * 1.414


def wiggle(
    freq: float,
    amp: float,
    octaves: int = 1,
    amp_mult: float = 0.5,
    t: float = 0.0,
    seed: int = 42,
) -> float:
    """
    After Effects wiggle() expression.
    Evaluates continuous fractal gradient noise at frequency freq and amplitude amp.
    """
    if freq <= 0.0 or amp == 0.0:
        return 0.0

    total = 0.0
    cur_freq = freq
    cur_amp = amp

    for oct_idx in range(max(1, octaves)):
        n = _gradient_noise_1d(t * cur_freq, seed=seed + oct_idx * 101)
        total += n * cur_amp
        cur_freq *= 2.0
        cur_amp *= amp_mult

    return total


# ── Dan Ebberts Inertia / Bounce Expression ─────────────────────────────────

def inertia_bounce(
    t: float,
    t_key: float,
    val_start: float,
    val_end: float,
    amp: float = 0.08,
    freq: float = 3.5,
    decay: float = 5.0,
) -> float:
    """
    Classic After Effects Dan Ebberts inertia bounce expression.
    When t >= t_key, creates a natural damped harmonic physical settle.
    """
    if t < t_key:
        return val_start

    delta_t = t - t_key
    delta_val = val_end - val_start

    # Damped cosine harmonic oscillator
    damp = math.exp(-decay * delta_t)
    osc = math.cos(freq * (2.0 * math.pi) * delta_t)
    bounce = delta_val * amp * damp * osc

    return val_end + bounce


# ── loopOut() Expression ───────────────────────────────────────────────────

def loop_out(
    keyframes: List[Dict[str, float]],
    t_sec: float,
    loop_type: str = "cycle",
    total_duration: Optional[float] = None,
) -> float:
    """
    After Effects loopOut(type) expression:
    - 'cycle': Modulo wrap-around repeating playback.
    - 'pingpong': Reversing forward and backward playback.
    - 'offset': Continues in the direction of the final delta for infinite motion.
    """
    if not keyframes:
        return 0.0
    if len(keyframes) == 1:
        return float(keyframes[0].get("val", 0.0))

    sorted_keys = sorted(keyframes, key=lambda k: float(k.get("t", 0.0)))
    t0 = float(sorted_keys[0]["t"])
    t1 = float(sorted_keys[-1]["t"])
    span = max(0.001, t1 - t0)
    dur = total_duration or span

    v0 = float(sorted_keys[0]["val"])
    v1 = float(sorted_keys[-1]["val"])
    net_delta = v1 - v0

    if t_sec < t0:
        return v0

    eff_t = t_sec - t0

    if loop_type == "pingpong":
        cycle_len = span * 2.0
        mod_t = eff_t % cycle_len
        if mod_t > span:
            sub_t = t1 - (mod_t - span)
        else:
            sub_t = t0 + mod_t
        return _eval_sorted_keys(sorted_keys, sub_t)

    elif loop_type == "offset":
        cycles_completed = math.floor(eff_t / span)
        rem_t = t0 + (eff_t % span)
        base_val = _eval_sorted_keys(sorted_keys, rem_t)
        return base_val + (cycles_completed * net_delta)

    else:  # default 'cycle'
        rem_t = t0 + (eff_t % span)
        return _eval_sorted_keys(sorted_keys, rem_t)


def _eval_sorted_keys(keys: List[Dict[str, float]], t: float) -> float:
    if t <= keys[0]["t"]:
        return keys[0]["val"]
    if t >= keys[-1]["t"]:
        return keys[-1]["val"]
    for i in range(len(keys) - 1):
        k0, k1 = keys[i], keys[i + 1]
        if k0["t"] <= t <= k1["t"]:
            p = (t - k0["t"]) / max(0.0001, k1["t"] - k0["t"])
            return k0["val"] + (k1["val"] - k0["val"]) * p
    return keys[-1]["val"]


# ── Domain Remapping: linear(), ease(), easeIn(), easeOut() ────────────────

def linear(t: float, t_min: float, t_max: float, v_min: float, v_max: float) -> float:
    """AE linear(t, tMin, tMax, value1, value2)"""
    if t <= t_min:
        return v_min
    if t >= t_max:
        return v_max
    p = (t - t_min) / max(0.0001, t_max - t_min)
    return v_min + (v_max - v_min) * p


def ease(t: float, t_min: float, t_max: float, v_min: float, v_max: float) -> float:
    """AE ease(t, tMin, tMax, value1, value2) with Hermite smoothstep 3x^2 - 2x^3"""
    if t <= t_min:
        return v_min
    if t >= t_max:
        return v_max
    p = (t - t_min) / max(0.0001, t_max - t_min)
    smooth = p * p * (3.0 - 2.0 * p)
    return v_min + (v_max - v_min) * smooth


def value_at_time(
    evaluator: Callable[[float], float],
    t: float,
    delay: float = 0.0,
) -> float:
    """AE valueAtTime(time - delay) for trailing leader-follower choreography."""
    return evaluator(max(0.0, t - delay))
