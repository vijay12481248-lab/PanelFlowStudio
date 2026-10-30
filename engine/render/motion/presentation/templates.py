"""
Production-Ready Reusable Motion Graphics Presentation Templates.
Standardized interfaces, 100% procedural generators, zero external image assets required.
"""

from __future__ import annotations

import math
import numpy as np
import cv2
from typing import Tuple, List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from engine.render.motion.curves import (
    ease_out_expo,
    ease_out_back,
    ease_out_cubic,
    spring_interpolate,
)
from engine.render.motion.effects.shimmer import render_shimmer_text
from engine.render.motion.effects.chromatic import (
    apply_chromatic_aberration,
    apply_scanline_glitch,
    compute_camera_shake,
)
from engine.render.motion.effects.lighting import (
    render_volumetric_glow,
    render_anamorphic_flare,
    render_vignette,
)
from engine.render.motion.effects.particles import ParticleEmitter
from engine.render.motion.typography.kinetic_text import (
    get_scramble_text,
    draw_word_stagger_reveal,
    draw_tracking_expansion_text,
    compute_rolling_counter,
)
from engine.render.motion.typography.orbital_kinetic import (
    draw_3d_orbiting_text_ring,
)
from engine.render.motion.backgrounds.generative import (
    FluidCausticsGenerator,
    WaveRibbonMeshGenerator,
    CyberGrid3DGenerator,
    ParticleStarfield3DGenerator,
)
from engine.render.motion.ae.velocity import (
    KeyframeVelocity,
    ae_velocity_to_bezier,
    evaluate_ae_segment,
    AE_HERO_OUT_HANDLE,
    AE_HERO_IN_HANDLE,
)
from engine.render.motion.ae.expressions import (
    wiggle,
    inertia_bounce,
)
from engine.render.motion.ae.text_animator import (
    RangeSelector,
    TextAnimatorProperties,
    AETextAnimator,
)
from engine.render.motion.ae.motion_blur import AEMotionBlur


def _load_font(font_path: str, size: int) -> ImageFont.ImageFont:
    """Safe font loader with default fallback."""
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()


# Fonts
FONT_HERO = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 48)
FONT_HERO_MED = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 36)
FONT_TITLE = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 28)
FONT_HEADING = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 20)
FONT_BADGE = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 13)
FONT_BODY = _load_font(r"C:\Windows\Fonts\arial.ttf", 16)
FONT_BODY_BOLD = _load_font(r"C:\Windows\Fonts\arialbd.ttf", 16)
FONT_MONO = _load_font(r"C:\Windows\Fonts\consola.ttf", 14)
FONT_MONO_BOLD = _load_font(r"C:\Windows\Fonts\consolab.ttf", 15)
FONT_METRIC_NUM = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 44)
FONT_METRIC_LBL = _load_font(r"C:\Windows\Fonts\bahnschrift.ttf", 12)


class KeynoteShowcaseScene:
    """
    Luxury Apple/Stripe-tier Keynote Presentation Scene.
    Features:
    - Procedural fluid caustics + multi-frequency wave silk ribbons
    - Glassmorphism badge with ease-out drop
    - Sweeping specular shimmer highlight across master headline
    - Word-by-word kinetic stagger subtitle
    - Glassmorphic metric showcase cards with animated rolling counters and progress bars
    """

    def __init__(
        self,
        headline: str = "SYNTHESIS ONE",
        subtitle: str = "The Next Generation Neural Presentation Architecture",
        badge_text: str = "GLOBAL KEYNOTE 2026",
        metrics: Optional[List[Dict[str, Any]]] = None,
        accent_color: Tuple[int, int, int] = (124, 58, 237),  # Vibrant violet
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.headline = headline
        self.subtitle = subtitle
        self.badge_text = badge_text
        self.metrics = metrics or [
            {"val": 99.8, "unit": "%", "label": "PRECISION ACCURACY", "delta": "+14.2%"},
            {"val": 3.8, "unit": "x", "label": "FASTER INFERENCE", "delta": "+280%"},
            {"val": 1.2, "unit": "ms", "label": "MEDIAN LATENCY", "delta": "-68%"},
        ]
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec

        self.w, self.h = bounds
        self.caustics = FluidCausticsGenerator(bounds=bounds, base_color=(4, 7, 16))
        self.ribbons = WaveRibbonMeshGenerator(
            bounds=bounds,
            num_ribbons=6,
            color_start=(6, 182, 212),
            color_end=accent_color,
        )

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # 1. Procedural Background
        canvas = self.caustics.render(t)
        canvas = self.ribbons.render_onto(canvas, t)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 2. Glassmorphism Category Badge
        p_badge = min(1.0, max(0.0, t / 0.8))
        e_badge = ease_out_expo(p_badge)
        badge_y = int(60 + (1.0 - e_badge) * -30)

        badge_bbox = draw.textbbox((0, 0), self.badge_text, font=FONT_BADGE)
        badge_bw = (badge_bbox[2] - badge_bbox[0]) + 36
        badge_x = (w - badge_bw) // 2

        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_bw, badge_y + 32],
            radius=16,
            fill=(255, 255, 255, int(18 * e_badge)),
            outline=(*self.accent_color, int(180 * e_badge)),
            width=1,
        )
        draw.text(
            (badge_x + 18, badge_y + 8),
            self.badge_text,
            font=FONT_BADGE,
            fill=(255, 255, 255, int(230 * e_badge)),
        )

        # 3. Master Headline with Specular Shimmer Wave
        p_head = min(1.0, max(0.0, (t - 0.3) / 0.9))
        e_head = ease_out_expo(p_head)
        head_y = int(120 + (1.0 - e_head) * 35)

        h_box = draw.textbbox((0, 0), self.headline, font=FONT_HERO)
        head_w = h_box[2] - h_box[0]
        head_x = (w - head_w) // 2

        shimmer_phase = (t * 0.45) % 1.0
        render_shimmer_text(
            overlay,
            self.headline,
            head_x,
            head_y,
            FONT_HERO,
            base_color=(255, 255, 255),
            shimmer_color=self.accent_color,
            shimmer_phase=shimmer_phase,
        )

        # 4. Word-by-Word Stagger Subtitle
        p_sub = min(1.0, max(0.0, (t - 0.8) / 1.4))
        draw_word_stagger_reveal(
            draw=draw,
            words=self.subtitle.split(),
            center_x=w // 2,
            baseline_y=head_y + 68,
            font=FONT_BODY,
            progress=p_sub,
            color=(203, 213, 225),
            stagger_delay=0.10,
        )

        # 5. Glassmorphism Metric Showcase Cards
        num_cards = len(self.metrics)
        card_w = 260
        card_h = 160
        gap = 35
        total_w = num_cards * card_w + (num_cards - 1) * gap
        start_x = (w - total_w) // 2
        card_base_y = 330

        for i, m in enumerate(self.metrics):
            card_start_t = 1.2 + i * 0.22
            p_card = min(1.0, max(0.0, (t - card_start_t) / 0.8))
            e_card = ease_out_back(p_card)

            cx = start_x + i * (card_w + gap)
            cy = int(card_base_y + (1.0 - e_card) * 50)
            card_alpha = int(255 * min(1.0, p_card * 1.5))

            if p_card > 0.0:
                # Glass container
                draw.rounded_rectangle(
                    [cx, cy, cx + card_w, cy + card_h],
                    radius=18,
                    fill=(15, 23, 42, int(150 * (card_alpha / 255.0))),
                    outline=(*self.accent_color, int(100 * (card_alpha / 255.0))),
                    width=1,
                )

                # Metric Counter (Rolling animation)
                target_val = float(m.get("val", 0.0))
                unit = m.get("unit", "")
                p_counter = min(1.0, max(0.0, (t - (card_start_t + 0.3)) / 1.2))
                cur_val = compute_rolling_counter(0.0, target_val, p_counter, easing="ease_out_expo")

                val_str = f"{cur_val:.1f}" if isinstance(target_val, float) and target_val % 1 != 0 else f"{int(cur_val)}"
                disp_str = f"{val_str}{unit}"

                draw.text(
                    (cx + 24, cy + 22),
                    disp_str,
                    font=FONT_METRIC_NUM,
                    fill=(255, 255, 255, card_alpha),
                )

                # Metric Label
                draw.text(
                    (cx + 24, cy + 86),
                    m.get("label", ""),
                    font=FONT_METRIC_LBL,
                    fill=(148, 163, 184, int(card_alpha * 0.9)),
                )

                # Progress / Delta Bar
                delta_str = m.get("delta", "")
                draw.rounded_rectangle(
                    [cx + 24, cy + 124, cx + card_w - 24, cy + 130],
                    radius=3,
                    fill=(255, 255, 255, 20),
                )
                bar_prog = ease_out_expo(p_counter)
                bar_fill_w = int((card_w - 48) * bar_prog)
                if bar_fill_w > 0:
                    draw.rounded_rectangle(
                        [cx + 24, cy + 124, cx + 24 + bar_fill_w, cy + 130],
                        radius=3,
                        fill=(*self.accent_color, card_alpha),
                    )

                # Delta Tag
                if delta_str:
                    draw.text(
                        (cx + card_w - 75, cy + 96),
                        delta_str,
                        font=FONT_BADGE,
                        fill=(52, 211, 153, card_alpha),
                    )

        # 6. Ambient Vignette
        canvas = Image.alpha_composite(canvas, overlay)
        canvas = render_vignette(canvas, strength=0.35)
        return canvas.convert("RGB")


class CyberHUDScene:
    """
    Broadcast-Grade Cyberpunk / Esports HUD Scene.
    Features:
    - 3D perspective floor grid receding to horizon
    - Depth-projected 3D starfield particles
    - Hexagonal corner telemetry HUD brackets
    - Hacker scramble / decrypt title animation with blinking cursor block
    - Procedural audio visualizer waveform bars
    - Status telemetry gauges
    - Dynamic chromatic aberration on entrance
    """

    def __init__(
        self,
        title: str = "CYBERNETIC_MAINFRAME // V8",
        target_name: str = "UNIT_AEGIS_09",
        status: str = "STATUS: SYNCHRONIZED",
        telemetry: Optional[List[str]] = None,
        accent_color: Tuple[int, int, int] = (0, 255, 170),  # Neon Mint
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.title = title
        self.target_name = target_name
        self.status = status
        self.telemetry = telemetry or [
            "SYS.LATENCY: 0.42 ms",
            "QUANTUM_CORE: STABLE",
            "NEURAL_LINK: 100.0%",
            "PROTOCOL: AES-GCM-256",
        ]
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec

        self.w, self.h = bounds
        self.grid = CyberGrid3DGenerator(bounds=bounds, grid_color=accent_color, horizon_y=380)
        self.stars = ParticleStarfield3DGenerator(
            bounds=bounds,
            num_stars=140,
            speed=120.0,
            star_color=(180, 240, 255),
        )

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # Base obsidian background
        canvas = Image.new("RGBA", (w, h), (5, 8, 14, 255))
        canvas = self.grid.render_onto(canvas, t)
        canvas = self.stars.render_onto(canvas, t)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 1. Corner Tech HUD Brackets
        margin = 40
        bracket_len = 50
        col_acc = (*self.accent_color, 200)

        # Top-Left
        draw.line([(margin, margin), (margin + bracket_len, margin)], fill=col_acc, width=2)
        draw.line([(margin, margin), (margin, margin + bracket_len)], fill=col_acc, width=2)
        # Top-Right
        draw.line([(w - margin, margin), (w - margin - bracket_len, margin)], fill=col_acc, width=2)
        draw.line([(w - margin, margin), (w - margin, margin + bracket_len)], fill=col_acc, width=2)
        # Bottom-Left
        draw.line([(margin, h - margin), (margin + bracket_len, h - margin)], fill=col_acc, width=2)
        draw.line([(margin, h - margin), (margin, h - margin - bracket_len)], fill=col_acc, width=2)
        # Bottom-Right
        draw.line([(w - margin, h - margin), (w - margin - bracket_len, h - margin)], fill=col_acc, width=2)
        draw.line([(w - margin, h - margin), (w - margin, h - margin - bracket_len)], fill=col_acc, width=2)

        # 2. Scramble Hacker Title
        p_scramble = min(1.0, max(0.0, t / 1.8))
        disp_title = get_scramble_text(self.title, p_scramble, seed=int(t * 15))
        draw.text((margin + 20, margin + 15), disp_title, font=FONT_TITLE, fill=col_acc)

        # Subtitle Target
        draw.text(
            (margin + 20, margin + 55),
            f">> TARGET ACQUIRED: {self.target_name}",
            font=FONT_MONO,
            fill=(203, 213, 225, 230),
        )

        # 3. Status indicator with pulsing LED
        pulse = 0.5 + 0.5 * math.sin(t * 8.0)
        led_alpha = int(140 + 115 * pulse)
        draw.ellipse([w - margin - 220, margin + 20, w - margin - 208, margin + 32], fill=(*self.accent_color, led_alpha))
        draw.text(
            (w - margin - 200, margin + 18),
            self.status,
            font=FONT_MONO_BOLD,
            fill=(*self.accent_color, 240),
        )

        # 4. Animated Equalizer Waveform Bars (Procedural Sine Harmonics)
        eq_x = margin + 20
        eq_y = h - margin - 90
        num_bars = 36
        bar_w = 6
        bar_gap = 4

        for b_i in range(num_bars):
            f1 = math.sin(t * 5.0 + b_i * 0.35)
            f2 = math.cos(t * 8.2 - b_i * 0.22)
            f3 = math.sin(t * 3.1 + b_i * 0.7)
            bh = int(10 + 45 * abs(0.5 * f1 + 0.3 * f2 + 0.2 * f3))
            bx = eq_x + b_i * (bar_w + bar_gap)
            draw.rectangle([bx, eq_y + 60 - bh, bx + bar_w, eq_y + 60], fill=(*self.accent_color, 210))

        # 5. Telemetry Readouts
        for idx, line in enumerate(self.telemetry):
            ty = h - margin - 120 + idx * 24
            draw.text((w - margin - 280, ty), f"[{idx:02d}] {line}", font=FONT_MONO, fill=(148, 163, 184, 210))

        # Composite overlay
        canvas = Image.alpha_composite(canvas, overlay)

        # Subtle chromatic glitch on entry (t < 0.8s)
        if t < 0.8:
            glitch_p = 1.0 - (t / 0.8)
            canvas = apply_chromatic_aberration(canvas, shift_px=int(8 * glitch_p))
            if int(t * 20) % 2 == 0:
                canvas = apply_scanline_glitch(canvas, glitch_intensity=0.15 * glitch_p)

        return canvas.convert("RGB")


class SciFiContainmentScene:
    """
    Hollywood Cinematic Sci-Fi Containment Breach Scene.
    Features:
    - Ominous pulsing crimson caustics
    - Convection floating fire ember particles
    - Decaying camera shake trauma
    - Hacker scramble breach alert text with flashing cursor
    - Chromatic aberration and scanline slices
    - Volumetric lighting spotlight
    """

    def __init__(
        self,
        title: str = "CONTAINMENT FAILURE",
        facility: str = "SUBTERRANEAN SECTOR 09",
        threat_level: str = "CLASS 5 : PROTOCOL BREACH",
        warning_text: str = "NEURAL RESTRICTIONS DISSOLVED // OVERRIDE ACTIVE",
        accent_color: Tuple[int, int, int] = (239, 68, 68),  # Crimson Red
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.title = title
        self.facility = facility
        self.threat_level = threat_level
        self.warning_text = warning_text
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec

        self.w, self.h = bounds
        self.caustics = FluidCausticsGenerator(bounds=bounds, base_color=(12, 4, 6))
        self.emitter = ParticleEmitter(bounds=bounds, max_particles=120)

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # 1. Base Crimson Pulse Caustics
        pulse_alpha = 0.5 + 0.5 * math.sin(t * 3.5)
        orbs = [
            (self.accent_color, 0.4, 0.3, 400),
            ((185, 28, 28), 0.6, 0.5, 320),
            ((245, 158, 11), 0.7, 0.6, 260),  # Amber core
        ]
        canvas = self.caustics.render(t, orbs=orbs)

        # 2. Convection Ember Particles
        canvas = self.emitter.update_and_render(canvas, dt=0.033)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 3. Warning Hazard Banner
        p_banner = min(1.0, max(0.0, t / 0.6))
        e_banner = ease_out_expo(p_banner)
        ban_y = int(80 + (1.0 - e_banner) * -40)

        draw.rectangle([0, ban_y, w, ban_y + 44], fill=(*self.accent_color, int(180 * e_banner)))
        draw.text(
            (w // 2 - 210, ban_y + 12),
            f"// HAZARD ALERT // {self.threat_level}",
            font=FONT_HEADING,
            fill=(255, 255, 255, 255),
        )

        # 4. Scramble Breach Headline
        p_scramble = min(1.0, max(0.0, (t - 0.4) / 1.6))
        disp_title = get_scramble_text(self.title, p_scramble, seed=int(t * 18))
        cursor = "_" if int(t * 6) % 2 == 0 else " "

        t_box = draw.textbbox((0, 0), disp_title + cursor, font=FONT_HERO)
        tw = t_box[2] - t_box[0]
        draw.text(((w - tw) // 2, 220), disp_title + cursor, font=FONT_HERO, fill=(255, 255, 255, 255))

        # 5. Tracking Expansion Facility Tag
        p_track = min(1.0, max(0.0, (t - 0.8) / 2.0))
        draw_tracking_expansion_text(
            draw=draw,
            text=self.facility,
            center_x=w // 2,
            y=300,
            font=FONT_HEADING,
            progress=p_track,
            min_tracking=4,
            max_tracking=14,
            color=(254, 202, 202),
        )

        # 6. Monospace Warning Readout Box
        box_y = 420
        draw.rounded_rectangle(
            [w // 2 - 340, box_y, w // 2 + 340, box_y + 90],
            radius=12,
            fill=(0, 0, 0, 160),
            outline=(*self.accent_color, 220),
            width=2,
        )
        draw.text(
            (w // 2 - 310, box_y + 22),
            self.warning_text,
            font=FONT_MONO_BOLD,
            fill=(255, 255, 255, 240),
        )
        draw.text(
            (w // 2 - 310, box_y + 52),
            ">> IMMEDIATE EVACUATION ORDER AUTHORIZED //",
            font=FONT_MONO,
            fill=(*self.accent_color, 220),
        )

        canvas = Image.alpha_composite(canvas, overlay)

        # 7. Cinematic Camera Shake Trauma & Chromatic Glitch
        trauma = max(0.0, 1.0 - (t / 2.5))
        if trauma > 0.05:
            ox, oy = compute_camera_shake(trauma, max_offset=12.0)
            shifted = Image.new("RGB", (w, h), (0, 0, 0))
            shifted.paste(canvas, (int(ox), int(oy)))
            canvas = shifted

            chroma_shift = int(12.0 * trauma)
            canvas = apply_chromatic_aberration(canvas, shift_px=chroma_shift)
            canvas = apply_scanline_glitch(canvas, glitch_intensity=0.25 * trauma)

        canvas = render_vignette(canvas, strength=0.45)
        return canvas.convert("RGB")


class CorporateBenchmarkScene:
    """
    Enterprise SaaS & AI Model Benchmark Comparison Scene.
    Features:
    - Procedural deep obsidian/sapphire gradient caustics
    - 3D perspective cyber grid
    - Hero title with tracking expansion
    - Multi-model comparative progress bars with glowing metric caps
    - Live KPI rolling metrics
    - High-trust verified badge
    """

    def __init__(
        self,
        title: str = "ENTERPRISE INFERENCE BENCHMARK",
        subtitle: str = "PanelFlow Studio v8.0 vs Industry Standard Baselines",
        benchmarks: Optional[List[Dict[str, Any]]] = None,
        kpis: Optional[List[Dict[str, Any]]] = None,
        accent_color: Tuple[int, int, int] = (6, 182, 212),  # Precision Cyan
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.title = title
        self.subtitle = subtitle
        self.benchmarks = benchmarks or [
            {"model": "PanelFlow Engine (v8)", "score": 96.4, "highlight": True},
            {"model": "Standard Framework A", "score": 71.2, "highlight": False},
            {"model": "Legacy Batch Pipeline", "score": 48.6, "highlight": False},
        ]
        self.kpis = kpis or [
            {"label": "THROUGHPUT", "val": 420.0, "unit": " fps"},
            {"label": "VRAM FOOTPRINT", "val": 1.4, "unit": " GB"},
            {"label": "COST EFFICIENCY", "val": 94.2, "unit": "%"},
        ]
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec

        self.w, self.h = bounds
        self.caustics = FluidCausticsGenerator(bounds=bounds, base_color=(4, 8, 18))
        self.grid = CyberGrid3DGenerator(bounds=bounds, grid_color=(15, 45, 80), horizon_y=450)

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # 1. Background
        canvas = self.caustics.render(t)
        canvas = self.grid.render_onto(canvas, t)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 2. Header with Tracking Expansion
        p_head = min(1.0, max(0.0, t / 0.8))
        draw_tracking_expansion_text(
            draw=draw,
            text=self.title,
            center_x=w // 2,
            y=55,
            font=FONT_TITLE,
            progress=p_head,
            min_tracking=2,
            max_tracking=8,
            color=(255, 255, 255),
        )

        # Subtitle
        p_sub = min(1.0, max(0.0, (t - 0.3) / 0.8))
        e_sub = ease_out_expo(p_sub)
        sub_box = draw.textbbox((0, 0), self.subtitle, font=FONT_BODY)
        sw = sub_box[2] - sub_box[0]
        draw.text(((w - sw) // 2, 105), self.subtitle, font=FONT_BODY, fill=(148, 163, 184, int(220 * e_sub)))

        # 3. Comparative Benchmark Bars
        bar_start_x = 120
        bar_base_y = 190
        bar_w = 640
        bar_h = 32
        row_gap = 52

        for r_i, bm in enumerate(self.benchmarks):
            p_bar = min(1.0, max(0.0, (t - (0.6 + r_i * 0.2)) / 1.0))
            e_bar = ease_out_expo(p_bar)
            by = bar_base_y + r_i * row_gap

            # Model Label
            m_name = bm.get("model", "")
            draw.text((bar_start_x, by - 22), m_name, font=FONT_HEADING, fill=(241, 245, 249, 240))

            # Background Track
            draw.rounded_rectangle([bar_start_x, by, bar_start_x + bar_w, by + bar_h], radius=6, fill=(255, 255, 255, 15))

            # Filled Progress Bar
            target_score = float(bm.get("score", 0.0))
            cur_score = compute_rolling_counter(0.0, target_score, p_bar, easing="ease_out_expo")
            fill_px = int((bar_w * (cur_score / 100.0)))

            is_hl = bm.get("highlight", False)
            bar_color = self.accent_color if is_hl else (100, 116, 139)

            if fill_px > 0:
                draw.rounded_rectangle(
                    [bar_start_x, by, bar_start_x + fill_px, by + bar_h],
                    radius=6,
                    fill=(*bar_color, 240),
                )

            # Score text
            score_str = f"{cur_score:.1f}%"
            draw.text((bar_start_x + bar_w + 18, by + 4), score_str, font=FONT_HEADING, fill=(*bar_color, 255))

        # 4. Right Side KPI Dashboard Card
        kpi_x = bar_start_x + bar_w + 160
        kpi_y = 175
        kpi_card_w = 280
        kpi_card_h = 240

        p_kpi = min(1.0, max(0.0, (t - 0.9) / 0.8))
        e_kpi = ease_out_back(p_kpi)

        if p_kpi > 0.0:
            cur_ky = int(kpi_y + (1.0 - e_kpi) * 40)
            draw.rounded_rectangle(
                [kpi_x, cur_ky, kpi_x + kpi_card_w, cur_ky + kpi_card_h],
                radius=14,
                fill=(15, 23, 42, 200),
                outline=(*self.accent_color, 120),
                width=1,
            )

            # KPI Header
            draw.text((kpi_x + 20, cur_ky + 16), "KEY METRICS", font=FONT_BADGE, fill=(*self.accent_color, 240))

            for k_i, kpi in enumerate(self.kpis):
                p_item = min(1.0, max(0.0, (t - (1.1 + k_i * 0.2)) / 1.0))
                val_target = float(kpi.get("val", 0.0))
                unit = kpi.get("unit", "")
                cur_v = compute_rolling_counter(0.0, val_target, p_item)

                val_disp = f"{cur_v:.1f}" if isinstance(val_target, float) and val_target % 1 != 0 else f"{int(cur_v)}"
                item_y = cur_ky + 52 + k_i * 56

                draw.text((kpi_x + 20, item_y), f"{val_disp}{unit}", font=FONT_TITLE, fill=(255, 255, 255, 240))
                draw.text((kpi_x + 20, item_y + 28), kpi.get("label", ""), font=FONT_METRIC_LBL, fill=(148, 163, 184, 200))

        # 5. Verified Footer Banner
        footer_y = h - 80
        draw.line([(bar_start_x, footer_y), (w - bar_start_x, footer_y)], fill=(255, 255, 255, 25), width=1)
        draw.text((bar_start_x, footer_y + 16), "[VERIFIED BENCHMARK 2026] // DETERMINISTIC HARDWARE REPRODUCIBLE", font=FONT_MONO, fill=(148, 163, 184, 180))

        canvas = Image.alpha_composite(canvas, overlay)
        canvas = render_vignette(canvas, strength=0.25)
        return canvas.convert("RGB")


class KineticEditorialScene:
    """
    Swiss Minimalist Typographic Editorial Scene.
    Aesthetic: High-contrast International Typographic Style, stark black/white with acid neon accent.
    """

    def __init__(
        self,
        headline: str = "ARCHITECTURAL SYNTAX",
        subtitle: str = "Pure Typographic Motion & Kinetic Geometry",
        issue_tag: str = "VOL. 08 // SPECIAL EDITION",
        statement: str = "FORM FOLLOWS LOGIC. EVERY PIXEL HAS PURPOSE.",
        accent_color: Tuple[int, int, int] = (250, 204, 21),  # Electric Acid Yellow
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.headline = headline
        self.subtitle = subtitle
        self.issue_tag = issue_tag
        self.statement = statement
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec
        self.w, self.h = bounds

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # Stark Obsidian background
        canvas = Image.new("RGBA", (w, h), (8, 9, 11, 255))
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 1. Architectural Editorial Grid Lines (Animated wipe)
        p_grid = min(1.0, max(0.0, t / 0.8))
        e_grid = ease_out_expo(p_grid)

        col_rule = (255, 255, 255, 30)
        # Top Rule
        line_w = int(w * e_grid)
        draw.line([(0, 90), (line_w, 90)], fill=col_rule, width=1)
        # Bottom Rule
        draw.line([(w - line_w, h - 90), (w, h - 90)], fill=col_rule, width=1)
        # Vertical Sidebar Rule
        line_h = int(h * e_grid)
        draw.line([(140, 0), (140, line_h)], fill=col_rule, width=1)

        # 2. Editorial Index & Tag
        draw.text((170, 56), self.issue_tag, font=FONT_BADGE, fill=(*self.accent_color, 240))
        draw.text((w - 220, 56), "EDITORIAL / 2026", font=FONT_MONO, fill=(148, 163, 184, 200))

        # Vertical Rubric
        draw.text((60, 140), "N° 08", font=FONT_TITLE, fill=(255, 255, 255, 220))
        draw.text((60, 180), "MOTION", font=FONT_BADGE, fill=(148, 163, 184, 180))

        # 3. Massive Tracking Expansion Headline
        p_head = min(1.0, max(0.0, (t - 0.3) / 1.0))
        e_head = ease_out_expo(p_head)
        head_y = int(220 + (1.0 - e_head) * 40)

        draw_tracking_expansion_text(
            draw=draw,
            text=self.headline,
            center_x=w // 2 + 50,
            y=head_y,
            font=FONT_HERO,
            progress=p_head,
            min_tracking=2,
            max_tracking=10,
            color=(255, 255, 255),
        )

        # 4. Acid Yellow Kinetic Slash / Accent Bar
        bar_len = int(380 * e_head)
        draw.rectangle([w // 2 - 140, head_y + 70, w // 2 - 140 + bar_len, head_y + 74], fill=(*self.accent_color, 255))

        # 5. Subtitle & Manifesto Words
        p_sub = min(1.0, max(0.0, (t - 0.7) / 1.2))
        draw_word_stagger_reveal(
            draw=draw,
            text=self.subtitle,
            center_x=w // 2 + 50,
            baseline_y=head_y + 105,
            font=FONT_HEADING,
            progress=p_sub,
            color=(203, 213, 225),
        )

        # 6. Lower Statement Text
        p_stat = min(1.0, max(0.0, (t - 1.2) / 0.8))
        e_stat = ease_out_expo(p_stat)
        stat_y = int(480 + (1.0 - e_stat) * 20)
        draw.text((170, stat_y), self.statement, font=FONT_MONO_BOLD, fill=(241, 245, 249, int(230 * e_stat)))

        # Footer Coordinates
        draw.text((170, h - 60), "INDEX_01 / TYPOGRAPHIC_SYNCHRONIZATION", font=FONT_MONO, fill=(100, 116, 139, 180))
        draw.text((w - 200, h - 60), "SEC 09.00 // CH.02", font=FONT_MONO, fill=(100, 116, 139, 180))

        canvas = Image.alpha_composite(canvas, overlay)
        canvas = render_vignette(canvas, strength=0.2)
        return canvas.convert("RGB")


class AnimeBattleHUDScene:
    """
    High-Energy Shonen Combat / Tactical Anime HUD Scene.
    Features:
    - 3D Receding grid floor with energy horizon
    - Floating convection sparks / embers
    - Fighter identification plate & scramble technique title
    - Dynamic rolling power-level counter (e.g. 9,450,000+)
    - Segmented power gauge & warning badges
    """

    def __init__(
        self,
        fighter_name: str = "SHADOW REAPER // KAI",
        technique_name: str = "FORBIDDEN DOMAIN: ABYSS REND",
        power_level: int = 9450000,
        status: str = "LIMITER RELEASE: 100%",
        threat_rank: str = "SPECIAL GRADE [S]",
        accent_color: Tuple[int, int, int] = (249, 115, 22),  # Fiery Shonen Orange
        secondary_color: Tuple[int, int, int] = (239, 68, 68),  # Crimson Red
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
    ):
        self.fighter_name = fighter_name
        self.technique_name = technique_name
        self.power_level = power_level
        self.status = status
        self.threat_rank = threat_rank
        self.accent_color = accent_color
        self.secondary_color = secondary_color
        self.bounds = bounds
        self.duration_sec = duration_sec

        self.w, self.h = bounds
        self.grid = CyberGrid3DGenerator(bounds=bounds, grid_color=accent_color, horizon_y=420)
        self.emitter = ParticleEmitter(
            count=80,
            bounds=bounds,
            primary_color=accent_color,
            secondary_color=secondary_color,
        )

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # 1. Dark anime arena background
        canvas = Image.new("RGBA", (w, h), (14, 6, 8, 255))
        canvas = self.grid.render_onto(canvas, t)
        canvas = self.emitter.update_and_render(canvas, dt=0.033)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 2. Combat HUD Corner Brackets & Crosshairs
        pad = 35
        bracket_len = 40
        col_acc = (*self.accent_color, 220)

        draw.line([(pad, pad), (pad + bracket_len, pad)], fill=col_acc, width=2)
        draw.line([(pad, pad), (pad, pad + bracket_len)], fill=col_acc, width=2)
        draw.line([(w - pad, pad), (w - pad - bracket_len, pad)], fill=col_acc, width=2)
        draw.line([(w - pad, pad), (w - pad, pad + bracket_len)], fill=col_acc, width=2)

        # 3. Fighter Identification Header Plate
        p_name = min(1.0, max(0.0, t / 0.7))
        e_name = ease_out_expo(p_name)
        plate_y = int(50 + (1.0 - e_name) * -30)

        draw.rounded_rectangle([pad + 20, plate_y, pad + 480, plate_y + 44], radius=6, fill=(0, 0, 0, 180), outline=(*self.accent_color, 180), width=1)
        draw.text((pad + 36, plate_y + 12), self.fighter_name, font=FONT_TITLE, fill=(255, 255, 255, 255))

        # Threat Rank Pill
        draw.rounded_rectangle([w - pad - 240, plate_y, w - pad - 20, plate_y + 44], radius=6, fill=(*self.secondary_color, 200))
        draw.text((w - pad - 220, plate_y + 14), self.threat_rank, font=FONT_BADGE, fill=(255, 255, 255, 255))

        # 4. Decrypt / Scramble Technique Name
        p_tech = min(1.0, max(0.0, (t - 0.4) / 1.5))
        scrambled_tech = get_scramble_text(self.technique_name, p_tech, seed=int(t * 16))

        draw.text((pad + 20, 130), "// TECHNIQUE ACTIVATION //", font=FONT_BADGE, fill=(*self.accent_color, 240))
        draw.text((pad + 20, 155), scrambled_tech, font=FONT_HERO_MED, fill=(255, 255, 255, 255))

        # 5. Dynamic Battle Power Level (Rolling Counter)
        p_power = min(1.0, max(0.0, (t - 0.8) / 1.4))
        cur_power = int(compute_rolling_counter(0.0, float(self.power_level), p_power, easing="ease_out_expo"))

        power_box_y = 260
        draw.rounded_rectangle([pad + 20, power_box_y, pad + 380, power_box_y + 110], radius=10, fill=(0, 0, 0, 200), outline=(*self.accent_color, 200), width=1)
        draw.text((pad + 40, power_box_y + 14), "ENERGY OUTPUT // POWER LEVEL", font=FONT_BADGE, fill=(148, 163, 184, 220))
        draw.text((pad + 40, power_box_y + 42), f"{cur_power:,}", font=FONT_METRIC_NUM, fill=(*self.accent_color, 255))

        # 6. Segmented Energy Shield Gauge
        gauge_x = pad + 20
        gauge_y = power_box_y + 130
        num_segments = 18
        seg_w = 18
        seg_gap = 4

        draw.text((gauge_x, gauge_y - 20), "REIATSU DENSITY GAUGE", font=FONT_BADGE, fill=(148, 163, 184, 200))
        p_gauge = ease_out_expo(min(1.0, max(0.0, (t - 1.0) / 1.0)))
        active_segs = int(num_segments * p_gauge)

        for s_i in range(num_segments):
            sx = gauge_x + s_i * (seg_w + seg_gap)
            is_active = s_i < active_segs
            col = (*self.accent_color, 240) if is_active else (255, 255, 255, 25)
            draw.rectangle([sx, gauge_y, sx + seg_w, gauge_y + 18], fill=col)

        # 7. Status Footer
        draw.text((pad + 20, h - 60), f">> SYSTEM: {self.status}", font=FONT_MONO_BOLD, fill=(*self.accent_color, 230))
        draw.text((w - pad - 260, h - 60), "ANIME ENGINE V8 // ENGAGED", font=FONT_MONO, fill=(148, 163, 184, 180))

        canvas = Image.alpha_composite(canvas, overlay)

        # Entrance chromatic shockwave (t < 0.6s)
        if t < 0.6:
            glitch_f = 1.0 - (t / 0.6)
            canvas = apply_chromatic_aberration(canvas, shift_px=int(10 * glitch_f))

        canvas = render_vignette(canvas, strength=0.35)
        return canvas.convert("RGB")


class AEDynamicKineticScene:
    """
    After Effects Dynamic Kinetic Presentation Scene.
    Fully powered by After Effects procedural mechanics:
    - Text Animators with Range Selectors (Ramp Up character cascade)
    - Keyframe Velocity (75% / 85% Hero influence curve)
    - Dan Ebberts inertia bounce on metric counters
    - Wiggle handheld camera float
    - 180° Shutter Angle temporal motion blur
    """

    def __init__(
        self,
        headline: str = "AFTER EFFECTS KINETIC",
        subtitle: str = "Procedural Range Selectors & Velocity Interpolation",
        badge_text: str = "ADOBE AE ENGINE // 60FPS",
        metrics: Optional[List[Dict[str, Any]]] = None,
        accent_color: Tuple[int, int, int] = (99, 102, 241),  # Indigo
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
        enable_motion_blur: bool = False,
    ):
        self.headline = headline
        self.subtitle = subtitle
        self.badge_text = badge_text
        self.metrics = metrics or [
            {"val": 85.0, "unit": "%", "label": "VELOCITY INFLUENCE"},
            {"val": 180.0, "unit": "°", "label": "SHUTTER ANGLE"},
            {"val": 60.0, "unit": "fps", "label": "SUB-FRAME SAMPLING"},
        ]
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec
        self.enable_motion_blur = enable_motion_blur
        self.w, self.h = bounds

        self.ribbons = WaveRibbonMeshGenerator(
            bounds=bounds,
            num_ribbons=8,
            color_start=(14, 165, 233),
            color_end=accent_color,
        )
        self.starfield = ParticleStarfield3DGenerator(bounds=bounds, num_stars=80)
        self.blur_engine = AEMotionBlur(shutter_angle=180.0, samples_per_frame=4)

    def _render_internal(self, t: float) -> Image.Image:
        w, h = self.w, self.h

        # 1. Generative 3D Background
        canvas = Image.new("RGBA", (w, h), (7, 10, 19, 255))
        canvas = self.ribbons.render_onto(canvas, t)
        canvas = self.starfield.render_onto(canvas, t)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        pad = int(w * 0.08)

        # 2. Category Badge with AE Hero Velocity curve
        p_badge = evaluate_ae_segment(t, 0.0, 0.0, 0.8, 1.0, AE_HERO_OUT_HANDLE, AE_HERO_IN_HANDLE)
        badge_y = int(60 + (1.0 - p_badge) * -40)
        badge_x = pad

        draw.rounded_rectangle([badge_x, badge_y, badge_x + 220, badge_y + 30], radius=15, fill=(*self.accent_color, 45), outline=(*self.accent_color, 180), width=1)
        draw.text((badge_x + 18, badge_y + 8), self.badge_text, font=FONT_BADGE, fill=(255, 255, 255, 240))

        # 3. Master Headline via AE Text Animator with Range Selector (Ramp Up)
        p_head = min(100.0, max(0.0, (t / 1.4) * 100.0))
        head_selector = RangeSelector(
            start=0.0,
            end=p_head,
            shape="ramp_up",
            based_on="characters",
        )
        head_props = TextAnimatorProperties(
            position_offset=(0.0, 50.0),
            opacity=0.0,
            scale=(0.85, 0.85),
            tracking=4.0,
        )
        head_animator = AETextAnimator(range_selector=head_selector, properties=head_props)
        overlay = head_animator.render_to_canvas(
            overlay,
            self.headline,
            FONT_HERO,
            origin=(pad, 150),
            fill_color=(255, 255, 255),
            anchor="left",
        )

        # 4. Subtitle via AE Text Animator (Words Cascade)
        p_sub = min(100.0, max(0.0, ((t - 0.5) / 1.2) * 100.0))
        sub_selector = RangeSelector(
            start=0.0,
            end=p_sub,
            shape="smooth",
            based_on="words",
        )
        sub_props = TextAnimatorProperties(
            position_offset=(0.0, 30.0),
            opacity=0.0,
            tracking=2.0,
        )
        sub_animator = AETextAnimator(range_selector=sub_selector, properties=sub_props)
        overlay = sub_animator.render_to_canvas(
            overlay,
            self.subtitle,
            FONT_HEADING,
            origin=(pad, 225),
            fill_color=(148, 163, 184),
            anchor="left",
        )

        # 5. KPI Showcase Cards with Dan Ebberts Inertia Bounce
        card_w = int((w - (pad * 2) - 40) / 3)
        card_h = 130
        card_y_base = int(h - card_h - 100)

        for i, metric in enumerate(self.metrics[:3]):
            card_x = int(pad + i * (card_w + 20))
            card_t_start = 1.0 + i * 0.15

            # Entrance transition with AE Hero curve
            p_card = evaluate_ae_segment(t, card_t_start, 0.0, card_t_start + 0.6, 1.0, AE_HERO_OUT_HANDLE, AE_HERO_IN_HANDLE)
            card_y = int(card_y_base + (1.0 - p_card) * 60)

            if p_card > 0.01:
                # Glass card background
                draw.rounded_rectangle(
                    [card_x, card_y, card_x + card_w, card_y + card_h],
                    radius=12,
                    fill=(15, 23, 42, int(180 * p_card)),
                    outline=(*self.accent_color, int(160 * p_card)),
                    width=1,
                )

                # Metric counter with Dan Ebberts inertia bounce settling
                target_val = float(metric.get("val", 0.0))
                bounced_val = inertia_bounce(
                    t=t,
                    t_key=card_t_start + 0.5,
                    val_start=0.0,
                    val_end=target_val,
                    amp=0.12,
                    freq=4.0,
                    decay=6.0,
                )

                draw.text(
                    (card_x + 24, card_y + 18),
                    metric.get("label", "METRIC"),
                    font=FONT_BADGE,
                    fill=(148, 163, 184, int(220 * p_card)),
                )
                draw.text(
                    (card_x + 24, card_y + 44),
                    f"{bounced_val:.1f}{metric.get('unit', '')}",
                    font=FONT_METRIC_NUM,
                    fill=(*self.accent_color, int(255 * p_card)),
                )

        canvas = Image.alpha_composite(canvas, overlay)
        canvas = render_vignette(canvas, strength=0.3)

        # 6. Full-canvas sub-pixel organic camera float via After Effects wiggle() & cv2.warpAffine
        cam_x = wiggle(freq=1.5, amp=3.5, octaves=2, t=t, seed=101)
        cam_y = wiggle(freq=1.2, amp=2.5, octaves=2, t=t, seed=202)
        canvas_np = np.array(canvas, dtype=np.uint8)
        M_cam = np.float32([[1, 0, cam_x], [0, 1, cam_y]])
        canvas_np = cv2.warpAffine(canvas_np, M_cam, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        return Image.fromarray(canvas_np, mode="RGBA").convert("RGB")

    def render_frame(self, t: float) -> Image.Image:
        if self.enable_motion_blur:
            return self.blur_engine.render_blurred_frame(self._render_internal, t, fps=60.0)
        return self._render_internal(t)


class GlobalShoeOrbitScene:
    """
    Flagship 3D Shoe Orbit Motion Graphics Scene.
    Renders floating hero sneaker with continuous 3D cylindrical orbital kinetic typography,
    volumetric lighting, and depth-sorted occlusion.
    """
    def __init__(
        self,
        headline: str = "AETHER VELOCITY ONE",
        subtitle: str = "SUPPLYING EVERY CORNER OF THE WORLD",
        orbit_text_1: str = "AETHER VELOCITY ONE // ZERO-GRAVITY NITROGEN // FULL-LENGTH CARBON PLATE // ",
        orbit_text_2: str = "SUPPLYING EVERY CORNER OF THE WORLD // 195 COUNTRIES // WORLDWIDE LOGISTICS // ",
        accent_color: Tuple[int, int, int] = (6, 182, 212),
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: float = 6.0,
        shoe_cutout_path: Optional[str] = None,
    ):
        self.headline = headline
        self.subtitle = subtitle
        self.orbit_text_1 = orbit_text_1
        self.orbit_text_2 = orbit_text_2
        self.accent_color = accent_color
        self.bounds = bounds
        self.duration_sec = duration_sec
        self.w, self.h = bounds

        self.caustics = FluidCausticsGenerator(bounds=bounds, base_color=(4, 8, 16))
        self.ribbons = WaveRibbonMeshGenerator(
            bounds=bounds,
            num_ribbons=8,
            color_start=accent_color,
            color_end=(245, 158, 11),
        )
        self.starfield = ParticleStarfield3DGenerator(bounds=bounds, num_stars=80)

        # Shoe cutout
        self.shoe_cutout = None
        if shoe_cutout_path:
            p = Path(shoe_cutout_path)
            if p.exists():
                raw = Image.open(p).convert("RGBA")
                tw = int(self.w * 0.52)
                th = int(tw * (raw.height / raw.width))
                self.shoe_cutout = raw.resize((tw, th), Image.Resampling.LANCZOS)

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.w, self.h
        cx, cy = w / 2.0, h / 2.0

        canvas = self.caustics.render(t)
        canvas = self.ribbons.render_onto(canvas, t)
        canvas = self.starfield.render_onto(canvas, t)

        behind_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        front_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))

        shoe_y_offset = 12.0 * math.sin(1.3 * t)
        shoe_tilt = 2.5 * math.sin(0.9 * t)

        draw_3d_orbiting_text_ring(
            behind_canvas=behind_layer,
            front_canvas=front_layer,
            text=self.orbit_text_1,
            cx=cx,
            cy=cy + shoe_y_offset * 0.4,
            font=FONT_HEADING,
            t=t,
            rx=w * 0.35,
            rz=h * 0.28,
            pitch_deg=22.0,
            roll_deg=-14.0,
            omega=0.26,
            y_offset=-10.0,
            base_color=(255, 255, 255),
            accent_color=self.accent_color,
        )

        draw_3d_orbiting_text_ring(
            behind_canvas=behind_layer,
            front_canvas=front_layer,
            text=self.orbit_text_2,
            cx=cx,
            cy=cy + shoe_y_offset * 0.4,
            font=FONT_HEADING,
            t=t,
            rx=w * 0.32,
            rz=h * 0.25,
            pitch_deg=-18.0,
            roll_deg=12.0,
            omega=-0.20,
            y_offset=40.0,
            base_color=(255, 255, 255),
            accent_color=(245, 158, 11),
        )

        behind_glow = behind_layer.filter(ImageFilter.GaussianBlur(radius=2))
        composite = Image.alpha_composite(behind_glow, behind_layer)

        if self.shoe_cutout is not None:
            shoe_rot = self.shoe_cutout.rotate(shoe_tilt, resample=Image.Resampling.BICUBIC, expand=True)
            sx = int(cx - shoe_rot.width / 2.0)
            sy = int(cy - shoe_rot.height / 2.0 + shoe_y_offset)
            composite.alpha_composite(shoe_rot, (sx, sy))

        front_glow = front_layer.filter(ImageFilter.GaussianBlur(radius=5))
        composite = Image.alpha_composite(composite, front_glow)
        composite = Image.alpha_composite(composite, front_layer)

        canvas = Image.alpha_composite(canvas, composite)
        canvas = render_vignette(canvas, strength=0.28)

        cam_x = 3.2 * math.sin(0.75 * t)
        cam_y = 1.8 * math.cos(0.60 * t)
        canvas_np = np.array(canvas, dtype=np.uint8)
        M_cam = np.float32([[1, 0, cam_x], [0, 1, cam_y]])
        canvas_np = cv2.warpAffine(canvas_np, M_cam, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        return Image.fromarray(canvas_np, mode="RGBA").convert("RGB")

