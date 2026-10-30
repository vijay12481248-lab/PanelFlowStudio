"""
Cinema Universe & Procedural Generative Presentation Templates:
1. MatrixDigitalRainScene (Cyber Terminal & Katakana Rain)
2. SynthwaveSunsetScene (80s Retro Outrun & Wireframe Horizon)
3. LuxuryGoldMonogramScene (Cinematic Prestige & 3D Extruded Gold)
4. CosmicNebulaWarpScene (Deep Space Hyperspace Jump & Gravitational Warp)
"""

from __future__ import annotations

import math
import random
from typing import Tuple, List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from engine.render.motion.curves import ease_out_expo, ease_out_back, ease_out_cubic
from engine.render.motion.effects.shimmer import render_shimmer_text
from engine.render.motion.effects.chromatic import apply_chromatic_aberration, apply_scanline_glitch, compute_camera_shake
from engine.render.motion.effects.lighting import render_volumetric_glow, render_anamorphic_flare, render_vignette
from engine.render.motion.effects.particles import ParticleEmitter
from engine.render.motion.typography.kinetic_text import (
    get_scramble_text,
    draw_tracking_expansion_text,
    draw_typewriter_text,
    draw_extruded_text,
    compute_rolling_counter,
)
from engine.render.motion.backgrounds.generative import (
    FluidCausticsGenerator,
    CyberGrid3DGenerator,
    ParticleStarfield3DGenerator,
)
from engine.render.motion.audio.analyzer import AudioFeatureExtractor


def _load_font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


FONT_HERO = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 48)
FONT_TITLE = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 32)
FONT_HEADING = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 22)
FONT_BADGE = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 13)
FONT_BODY = _load_font(r"C:\Windows\Fonts\arial.ttf", 16)
FONT_MONO = _load_font(r"C:\Windows\Fonts\consola.ttf", 15)
FONT_MONO_BOLD = _load_font(r"C:\Windows\Fonts\consolab.ttf", 16)


# -----------------------------------------------------------------------------
# 1. MATRIX DIGITAL RAIN SCENE
# -----------------------------------------------------------------------------
class MatrixDigitalRainScene:
    """
    Iconic Matrix Cyberpunk Terminal with vertical cascading digital glyph rain.
    Features:
    - Multi-column cascading streams with bright white/lime leader glyphs and phosphor decay
    - Procedural character mutation
    - Audio-reactive stream acceleration
    - Central hacker terminal prompt with typewriter decrypt title
    """

    GLYPHS = list("0123456789ABCDEF$#@%&*+-/<>~ｦｱｳｴｵｶｷｹｺｻｼｽｾｿﾀﾂﾃﾅﾆﾇﾈﾊﾋﾎﾏﾐﾑﾒﾓﾔﾕﾗﾘﾜ")

    def __init__(
        self,
        headline: str = "ACCESS GRANTED // MAINFRAME INFILTRATED",
        subtitle: str = "Root privileges acquired. Decrypting neural weights...",
        badge_text: str = "SYSTEM COMPROMISED",
        accent_color: Tuple[int, int, int] = (34, 197, 94),  # Matrix Phosphor Green
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
        audio_path: Optional[str] = None,
    ):
        self.headline = headline
        self.subtitle = subtitle
        self.badge_text = badge_text
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec
        self.w, self.h = bounds
        self.audio = AudioFeatureExtractor(audio_path)

        # Initialize deterministic columns
        self.col_spacing = 24
        self.num_cols = self.w // self.col_spacing
        rng = random.Random(1337)
        self.stream_speeds = [rng.uniform(120.0, 320.0) for _ in range(self.num_cols)]
        self.stream_lengths = [rng.randint(12, 28) for _ in range(self.num_cols)]
        self.stream_offsets = [rng.uniform(0.0, 1000.0) for _ in range(self.num_cols)]

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h
        beat = self.audio.get_beat_envelope_at(t)
        rms = self.audio.get_rms_at(t)

        # Base obsidian canvas
        canvas = Image.new("RGBA", (w, h), (4, 10, 6, 255))
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 1. Render Matrix Digital Rain Columns
        char_h = 20
        eff_speed_mult = 1.0 + beat * 0.8

        for c_idx in range(self.num_cols):
            cx = c_idx * self.col_spacing + 10
            speed = self.stream_speeds[c_idx] * eff_speed_mult
            head_y = (self.stream_offsets[c_idx] + t * speed) % (h + 400) - 100
            s_len = self.stream_lengths[c_idx]

            for g_i in range(s_len):
                gy = int(head_y - g_i * char_h)
                if -20 <= gy < h + 20:
                    char_seed = int(c_idx * 997 + g_i * 31 + t * 4)
                    char = self.GLYPHS[char_seed % len(self.GLYPHS)]

                    if g_i == 0:
                        # Bright white-lime leader
                        col = (240, 255, 240, 255)
                    elif g_i < 3:
                        # Vibrant electric green
                        col = (134, 239, 172, 220)
                    else:
                        # Phosphor decay tail
                        decay = 1.0 - (g_i / s_len)
                        alpha = int(180 * (decay ** 1.5))
                        col = (*self.accent_color, max(15, alpha))

                    draw.text((cx, gy), char, font=FONT_MONO, fill=col)

        # 2. Central Terminal Readout Box
        p_term = min(1.0, max(0.0, t / 0.8))
        e_term = ease_out_expo(p_term)

        box_w = min(w - 80, 840)
        box_h = 240
        bx = (w - box_w) // 2
        by = int((h - box_h) // 2 + (1.0 - e_term) * 40)

        # Semi-transparent dark frosted glass terminal
        draw.rounded_rectangle(
            [bx, by, bx + box_w, by + box_h],
            radius=12,
            fill=(2, 8, 4, 225),
            outline=(*self.accent_color, 200),
            width=2,
        )

        # Terminal Header Bar
        draw.rectangle([bx, by, bx + box_w, by + 34], fill=(*self.accent_color, 40))
        draw.ellipse([bx + 14, by + 12, bx + 24, by + 22], fill=(239, 68, 68, 220))
        draw.ellipse([bx + 32, by + 12, bx + 42, by + 22], fill=(245, 158, 11, 220))
        draw.ellipse([bx + 50, by + 12, bx + 60, by + 22], fill=(34, 197, 94, 220))
        draw.text((bx + 80, by + 9), f"TERMINAL // {self.badge_text}", font=FONT_MONO, fill=(200, 255, 200, 220))

        # 3. Typewriter Headline
        p_type = min(1.0, max(0.0, (t - 0.5) / 1.8))
        draw_typewriter_text(
            draw=draw,
            text=self.headline,
            cx=w // 2,
            y=by + 65,
            font=FONT_HEADING,
            progress=p_type,
            fill=(255, 255, 255),
            cursor_char="█",
        )

        # Subtitle
        p_sub = min(1.0, max(0.0, (t - 1.2) / 1.2))
        e_sub = ease_out_expo(p_sub)
        sub_box = draw.textbbox((0, 0), self.subtitle, font=FONT_BODY)
        sw = sub_box[2] - sub_box[0]
        draw.text(((w - sw) // 2, by + 115), self.subtitle, font=FONT_BODY, fill=(134, 239, 172, int(220 * e_sub)))

        # Telemetry Memory Dump
        dump_str = f"MEM_DUMP: 0x7FFF{int(t*1000):04X} // STACK_POINTER: OK // BYTES_STREAMED: {int(t*184000):,}"
        draw.text((bx + 24, by + 185), dump_str, font=FONT_MONO, fill=(74, 222, 128, 180))

        canvas = Image.alpha_composite(canvas, overlay)

        # Scanline digital drop & aberration on beat hits
        if beat > 0.4:
            canvas = apply_chromatic_aberration(canvas, shift_px=int(8 * beat))
            canvas = apply_scanline_glitch(canvas, intensity=0.15 * beat)

        canvas = render_vignette(canvas, strength=0.35)
        return canvas.convert("RGB")


# -----------------------------------------------------------------------------
# 2. SYNTHWAVE SUNSET SCENE
# -----------------------------------------------------------------------------
class SynthwaveSunsetScene:
    """
    80s Retro Outrun / Synthwave Sunset Scene.
    Features:
    - 3D receding neon floor grid
    - Horizon vector wireframe mountains
    - Radiant striped sunset orb with horizontal blind slices
    - Chrome specular gradient typography
    - Ambient neon scanlines & lens flare
    """

    def __init__(
        self,
        headline: str = "OUTRUN THE FUTURE",
        subtitle: str = "Retro Electro Aesthetics // Neural Frequency 1984",
        badge_text: str = "SYNTHWAVE 84",
        accent_color: Tuple[int, int, int] = (244, 63, 94),  # Hot Neon Rose
        secondary_color: Tuple[int, int, int] = (168, 85, 247),  # Electric Purple
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.headline = headline
        self.subtitle = subtitle
        self.badge_text = badge_text
        self.accent_color = accent_color
        self.secondary_color = secondary_color
        self.bounds = bounds
        self.duration_sec = duration_sec
        self.w, self.h = bounds

        self.grid = CyberGrid3DGenerator(bounds=bounds, grid_color=(236, 72, 153), horizon_y=380)

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h
        horizon_y = 380

        # Deep twilight gradient
        canvas = Image.new("RGBA", (w, h), (18, 8, 38, 255))
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 1. Radiant Sunset Orb (Centered on horizon with horizontal slice blinds)
        sun_cx, sun_cy = w // 2, horizon_y - 20
        sun_r = 140

        sun_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(sun_surf)

        # Multi-layer sunset gradient
        s_draw.ellipse([sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r], fill=(251, 146, 60, 240))
        s_draw.ellipse([sun_cx - sun_r + 20, sun_cy - sun_r + 20, sun_cx + sun_r - 20, sun_cy + sun_r - 20], fill=(244, 63, 94, 240))

        # Horizontal sliced blinds through sun
        blind_h = 6
        for b_i in range(8):
            by = horizon_y - 100 + b_i * 14
            s_draw.rectangle([sun_cx - sun_r - 10, by, sun_cx + sun_r + 10, by + blind_h], fill=(0, 0, 0, 0))

        canvas = Image.alpha_composite(canvas, sun_surf)

        # 2. Distant Wireframe Mountains along Horizon
        pts = [(0, horizon_y)]
        rng = random.Random(42)
        for mx in range(0, w + 60, 60):
            my = horizon_y - int(rng.uniform(30, 95))
            pts.append((mx, my))
        pts.append((w, horizon_y))
        draw.polygon(pts, fill=(10, 4, 20, 220), outline=(236, 72, 153, 180))

        # 3. 3D Floor Grid
        canvas = self.grid.render_onto(canvas, t)

        # 4. Chrome / Specular Headline
        p_head = min(1.0, max(0.0, t / 0.9))
        e_head = ease_out_expo(p_head)
        head_y = int(110 + (1.0 - e_head) * -40)

        h_box = draw.textbbox((0, 0), self.headline, font=FONT_HERO)
        hw = h_box[2] - h_box[0]
        shimmer_phase = (t * 0.4) % 1.0

        render_shimmer_text(
            overlay,
            self.headline,
            (w - hw) // 2,
            head_y,
            FONT_HERO,
            base_color=(255, 255, 255),
            shimmer_color=(244, 63, 94),
            shimmer_progress=shimmer_phase,
        )

        # 5. Tracking Subtitle
        p_sub = min(1.0, max(0.0, (t - 0.4) / 1.5))
        draw_tracking_expansion_text(
            draw=draw,
            text=self.subtitle,
            center_x=w // 2,
            y=head_y + 65,
            font=FONT_HEADING,
            progress=p_sub,
            min_tracking=2,
            max_tracking=8,
            color=(253, 164, 175),
        )

        # Badge Pill
        draw.rounded_rectangle([w // 2 - 90, head_y - 40, w // 2 + 90, head_y - 12], radius=14, fill=(244, 63, 94, 200))
        draw.text((w // 2 - 65, head_y - 34), self.badge_text, font=FONT_BADGE, fill=(255, 255, 255))

        canvas = Image.alpha_composite(canvas, overlay)
        canvas = render_anamorphic_flare(canvas, center=(w // 2, horizon_y), length=450, color=(244, 63, 94))
        canvas = render_vignette(canvas, strength=0.3)
        return canvas.convert("RGB")


# -----------------------------------------------------------------------------
# 3. LUXURY GOLD MONOGRAM SCENE
# -----------------------------------------------------------------------------
class LuxuryGoldMonogramScene:
    """
    High-End Luxury Brand & Cinema Prestige Title Scene.
    Features:
    - Deep royal obsidian & velvet sapphire caustics
    - 3D Extruded gold typography with physical multi-pass bevel depth
    - Sweeping gold specular highlight wave
    - Floating warm golden bokeh dust particles
    """

    def __init__(
        self,
        headline: str = "AURELIA CINEMA",
        subtitle: str = "Grand Award of Cinematic Distinction 2026",
        badge_text: str = "OFFICIAL SELECTION",
        accent_color: Tuple[int, int, int] = (234, 179, 8),  # Warm Radiant Gold
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.headline = headline
        self.subtitle = subtitle
        self.badge_text = badge_text
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec
        self.w, self.h = bounds

        self.caustics = FluidCausticsGenerator(bounds=bounds, base_color=(8, 10, 18), blur_sigma=120)
        self.emitter = ParticleEmitter(
            count=60,
            bounds=bounds,
            primary_color=(254, 240, 138),  # Champagne Gold
            secondary_color=(234, 179, 8),  # Deep Gold
        )

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # 1. Deep Caustics with Warm Golden Spotlights
        orbs = [
            ((120, 90, 20), 0.3, 0.4, 450),  # Soft gold ambient orb
            ((20, 28, 55), 0.5, 0.3, 380),   # Deep velvet sapphire
        ]
        canvas = self.caustics.render(t, orbs=orbs)
        canvas = self.emitter.update_and_render(canvas, dt=0.033)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 2. Golden Monogram Diamond Crest
        p_crest = min(1.0, max(0.0, t / 0.9))
        e_crest = ease_out_expo(p_crest)
        cx, cy = w // 2, int(190 + (1.0 - e_crest) * -35)
        cr = 42

        # Outer Diamond
        draw.polygon([(cx, cy - cr), (cx + cr, cy), (cx, cy + cr), (cx - cr, cy)], fill=(0, 0, 0, 140), outline=(*self.accent_color, 240))
        # Inner Diamond
        draw.polygon([(cx, cy - cr + 8), (cx + cr - 8, cy), (cx, cy + cr - 8), (cx - cr + 8, cy)], outline=(254, 240, 138, 200))
        draw.text((cx - 8, cy - 14), "A", font=FONT_TITLE, fill=(254, 240, 138, 255))

        # 3. 3D Extruded Gold Headline
        p_head = min(1.0, max(0.0, (t - 0.4) / 1.0))
        e_head = ease_out_expo(p_head)
        head_y = int(285 + (1.0 - e_head) * 35)

        h_box = draw.textbbox((0, 0), self.headline, font=FONT_HERO)
        hw = h_box[2] - h_box[0]
        hx = (w - hw) // 2

        draw_extruded_text(
            draw=draw,
            text=self.headline,
            x=hx,
            y=head_y,
            font=FONT_HERO,
            depth=6,
            fill=(254, 240, 138),
            extrusion_color=(74, 55, 12),
            angle_deg=55.0,
        )

        # Shimmer highlight across gold
        shimmer_p = (t * 0.35) % 1.0
        render_shimmer_text(
            overlay,
            self.headline,
            hx,
            head_y,
            FONT_HERO,
            base_color=(254, 240, 138),
            shimmer_color=(255, 255, 255),
            shimmer_progress=shimmer_p,
        )

        # 4. Laurel / Badge
        p_badge = min(1.0, max(0.0, (t - 0.8) / 1.2))
        draw_tracking_expansion_text(
            draw=draw,
            text=self.subtitle,
            center_x=w // 2,
            y=head_y + 80,
            font=FONT_BODY,
            progress=p_badge,
            min_tracking=3,
            max_tracking=10,
            color=(217, 180, 74),
        )

        # Award Tag
        draw.text((w // 2 - 75, head_y + 125), f"// {self.badge_text} //", font=FONT_BADGE, fill=(161, 140, 60, 200))

        canvas = Image.alpha_composite(canvas, overlay)
        canvas = render_volumetric_glow(canvas, center=(w // 2, cy), color=self.accent_color, radius=180, alpha=45)
        canvas = render_vignette(canvas, strength=0.35)
        return canvas.convert("RGB")


# -----------------------------------------------------------------------------
# 4. COSMIC NEBULA WARP SCENE
# -----------------------------------------------------------------------------
class CosmicNebulaWarpScene:
    """
    Hyperspace Warp Drive Jump & Gravitational Nebula Vortex.
    Features:
    - 3D Warp starfield acceleration with velocity streaks
    - Multi-frequency fluid nebula caustics (Magenta & Cyan)
    - Central gravitational event horizon
    - Decaying warp shake trauma
    - Scramble decrypt interstellar coordinates
    """

    def __init__(
        self,
        headline: str = "WARP FACTOR 9.9 // ENGAGED",
        subtitle: str = "Folding space-time metrics... Destination: Sector Andromeda",
        badge_text: str = "HYPERSPACE ACCELERATION",
        accent_color: Tuple[int, int, int] = (168, 85, 247),  # Quantum Violet
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.headline = headline
        self.subtitle = subtitle
        self.badge_text = badge_text
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec
        self.w, self.h = bounds

        self.caustics = FluidCausticsGenerator(bounds=bounds, base_color=(6, 4, 16), blur_sigma=90)
        self.starfield = ParticleStarfield3DGenerator(
            bounds=bounds,
            num_stars=240,
            speed=280.0,  # High-speed warp
            star_color=(220, 245, 255),
        )

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # 1. Interstellar Nebula Caustics
        orbs = [
            ((147, 51, 234), 0.6, 0.4, 420),  # Nebula Violet
            ((6, 182, 212), 0.5, 0.7, 360),   # Cyan Ion Stream
        ]
        canvas = self.caustics.render(t, orbs=orbs)
        canvas = self.starfield.render_onto(canvas, t)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 2. Central Gravitational Event Horizon Rings
        cx, cy = w // 2, h // 2 - 20
        ring_r = int(70 + 20 * math.sin(t * 3.0))
        draw.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r], outline=(*self.accent_color, 180), width=2)
        draw.ellipse([cx - ring_r - 25, cy - ring_r - 25, cx + ring_r + 25, cy + ring_r + 25], outline=(6, 182, 212, 120), width=1)

        # 3. Scramble Interstellar Headline
        p_scramble = min(1.0, max(0.0, t / 1.6))
        disp_title = get_scramble_text(self.headline, p_scramble, seed=int(t * 20))

        t_box = draw.textbbox((0, 0), disp_title, font=FONT_HERO)
        tw = t_box[2] - t_box[0]
        draw.text(((w - tw) // 2, cy + 90), disp_title, font=FONT_HERO, fill=(255, 255, 255, 255))

        # 4. Tracking Subtitle
        p_sub = min(1.0, max(0.0, (t - 0.5) / 1.8))
        draw_tracking_expansion_text(
            draw=draw,
            text=self.subtitle,
            center_x=w // 2,
            y=cy + 160,
            font=FONT_BODY,
            progress=p_sub,
            min_tracking=2,
            max_tracking=9,
            color=(196, 181, 253),
        )

        # Badge
        draw.rounded_rectangle([w // 2 - 140, cy - ring_r - 50, w // 2 + 140, cy - ring_r - 20], radius=15, fill=(15, 23, 42, 200), outline=(*self.accent_color, 200))
        draw.text((w // 2 - 110, cy - ring_r - 44), self.badge_text, font=FONT_BADGE, fill=(240, 230, 255))

        canvas = Image.alpha_composite(canvas, overlay)

        # Warp Trauma Camera Shake & Glitch on entry (t < 0.8s)
        if t < 0.8:
            trauma = 1.0 - (t / 0.8)
            ox, oy = compute_camera_shake(trauma=trauma, max_offset=14.0)
            shifted = Image.new("RGB", (w, h), (0, 0, 0))
            shifted.paste(canvas, (int(ox), int(oy)))
            canvas = shifted
            canvas = apply_chromatic_aberration(canvas, shift_px=int(12 * trauma))

        canvas = render_vignette(canvas, strength=0.4)
        return canvas.convert("RGB")
