"""
Deterministic procedural particle system for embers, floating dust, and energy sparks.
"""

import math
import random
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass
from PIL import Image, ImageDraw


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    color: Tuple[int, int, int]
    alpha: int


class ParticleEmitter:
    """
    High-performance deterministic particle emitter with gravity, sway, and convection.
    """

    def __init__(
        self,
        count: int = 60,
        bounds: Tuple[int, int] = (1280, 720),
        primary_color: Tuple[int, int, int] = (0, 240, 255),
        secondary_color: Tuple[int, int, int] = (255, 50, 70),
        seed: int = 42,
        max_particles: Optional[int] = None,
    ):
        self.count = max_particles if max_particles is not None else count
        self.w, self.h = bounds
        self.primary_color = primary_color
        self.secondary_color = secondary_color
        self.seed = seed

        # Internal active particles list
        rng = random.Random(seed)
        self.particles: List[Particle] = [
            Particle(
                x=rng.uniform(0, self.w),
                y=rng.uniform(0, self.h),
                vx=rng.uniform(-15.0, 15.0),
                vy=rng.uniform(-60.0, -15.0),
                size=rng.uniform(1.5, 3.5),
                color=primary_color if rng.random() > 0.4 else secondary_color,
                alpha=rng.randint(120, 240),
            )
            for _ in range(self.count)
        ]

    def update_and_render(self, canvas: Image.Image, dt: float = 0.033) -> Image.Image:
        """
        Advances particle simulation by dt and composites onto canvas.
        """
        overlay = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for p in self.particles:
            p.x = (p.x + p.vx * dt) % self.w
            p.y = (p.y + p.vy * dt) % self.h
            sz = int(p.size)
            draw.ellipse(
                [int(p.x - sz), int(p.y - sz), int(p.x + sz), int(p.y + sz)],
                fill=(*p.color, p.alpha),
            )

        return Image.alpha_composite(canvas, overlay)

    def render(
        self,
        canvas: Image.Image,
        t: float,
        speed_y: float = -20.0,
        sway_amount: float = 25.0,
    ) -> None:
        """
        Renders particles onto canvas at timestamp t.
        """
        draw = ImageDraw.Draw(canvas)
        rng = np.random.RandomState(self.seed)

        base_xs = rng.uniform(0, self.w, self.count)
        base_ys = rng.uniform(0, self.h, self.count)
        speeds = rng.uniform(0.7, 1.4, self.count)
        sizes = rng.choice([1, 2, 3], self.count, p=[0.6, 0.3, 0.1])

        for i in range(self.count):
            cur_y = (base_ys[i] + t * speed_y * speeds[i]) % self.h
            cur_x = (base_xs[i] + math.sin(t * 1.8 + i) * sway_amount) % self.w

            col = self.primary_color if i % 2 == 0 else self.secondary_color
            alpha = int(140 + 75 * math.sin(t * 2.5 + i))
            sz = int(sizes[i])

            draw.ellipse(
                [int(cur_x), int(cur_y), int(cur_x + sz), int(cur_y + sz)],
                fill=(*col, alpha),
            )
