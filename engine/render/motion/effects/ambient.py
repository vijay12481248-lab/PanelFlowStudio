"""Soft drifting dust and bokeh for the backdrop behind framed panels.

Deterministic: the same timestamp always gives the same frame, and motes keep drifting across cuts.
"""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image


class AmbientDust:
    def __init__(self, size: tuple[int, int], count: int = 90, seed: int = 7):
        self.w, self.h = size
        rng = random.Random(seed)
        scale = self.h / 1080.0
        self.motes = []
        for i in range(count):
            big = i % 6 == 0  # a few large, faint bokeh discs among many small bright motes
            r = rng.uniform(14, 26) if big else rng.uniform(1.6, 4.2)
            self.motes.append({
                "x": rng.uniform(0, self.w), "y": rng.uniform(0, self.h), "r": max(1.0, r * scale),
                "speed": (rng.uniform(5, 14) if big else rng.uniform(14, 44)) * scale,  # px/s upward
                "sway": rng.uniform(10, 38) * scale, "freq": rng.uniform(0.12, 0.45), "phase": rng.uniform(0, 6.283),
                "tw_freq": rng.uniform(0.3, 1.1), "tw_phase": rng.uniform(0, 6.283),
                "alpha": rng.uniform(0.10, 0.20) if big else rng.uniform(0.35, 0.85),
            })
        self._sprites: dict[int, np.ndarray] = {}

    def _sprite(self, r: float) -> np.ndarray:
        key = int(round(r * 2))
        if key not in self._sprites:
            half = int(math.ceil(r * 2.2))
            yy, xx = np.mgrid[-half:half + 1, -half:half + 1].astype(np.float32)
            self._sprites[key] = np.exp(-((xx * xx + yy * yy) / (r * r)) * 1.1)
        return self._sprites[key]

    def mask(self, t: float) -> np.ndarray:
        out = np.zeros((self.h, self.w), np.float32)
        for m in self.motes:
            x = (m["x"] + m["sway"] * math.sin(m["freq"] * t + m["phase"])) % self.w
            y = (m["y"] - m["speed"] * t) % self.h
            a = m["alpha"] * (0.6 + 0.4 * math.sin(m["tw_freq"] * 6.283 * t + m["tw_phase"]))
            sprite = self._sprite(m["r"])
            half = sprite.shape[0] // 2
            x0, y0 = int(x) - half, int(y) - half
            sx0, sy0 = max(0, -x0), max(0, -y0)
            sx1, sy1 = min(sprite.shape[1], self.w - x0), min(sprite.shape[0], self.h - y0)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            region = out[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1]
            np.maximum(region, sprite[sy0:sy1, sx0:sx1] * a, out=region)
        return out

    def render(self, canvas: Image.Image, t: float, backdrop_rgb: tuple[int, int, int]) -> None:
        """Paint the motes onto `canvas` in a warm light tinted by the backdrop colour."""
        warm = (255, 232, 196)
        color = tuple(int(0.4 * b + 0.6 * w) for b, w in zip(backdrop_rgb, warm))
        mask = Image.fromarray((self.mask(t) * 255).astype(np.uint8), "L")
        canvas.paste(color + (255,) if canvas.mode == "RGBA" else color, (0, 0), mask)
