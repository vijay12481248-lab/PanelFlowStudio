import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
from pathlib import Path

# Load System TrueType Fonts
FONT_TITLE_HUGE = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 46)
FONT_TITLE_MED = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 28)
FONT_BADGE = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 15)
FONT_CODE_BOLD = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 15)
FONT_CODE = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 13)
FONT_TELEMETRY = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 11)
FONT_BODY = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 16)

GLYPH_SET = list("!@#$%^&*()_+-=[]{}|;:,.<>?/~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ01")


def get_scramble_text(target: str, progress: float, seed: int = 42) -> str:
    """Computes a hacker/cyberpunk scramble-decryption string."""
    if progress <= 0.0:
        return ""
    if progress >= 1.0:
        return target

    n = len(target)
    resolved_count = int(progress * n)
    rng = random.Random(seed + int(progress * 100))

    result = []
    for i in range(n):
        if i < resolved_count:
            result.append(target[i])
        elif i == resolved_count:
            result.append(rng.choice(GLYPH_SET))
        else:
            result.append(rng.choice(GLYPH_SET) if target[i] != " " else " ")
    return "".join(result)


def apply_chromatic_aberration(im: Image.Image, offset_x: int, offset_y: int = 0) -> Image.Image:
    """Applies RGB channel splitting for high-tech glitch / containment breach shockwave."""
    if offset_x == 0 and offset_y == 0:
        return im

    r, g, b = im.split()[:3]
    r_shifted = ImageChops.offset(r, offset_x, offset_y)
    b_shifted = ImageChops.offset(b, -offset_x, -offset_y)
    return Image.merge("RGB", (r_shifted, g, b_shifted))


def draw_letter_spaced_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple,
    letter_spacing: int = 0,
):
    """Draws text with kinetic letter-spacing expansion."""
    cur_x = x
    for ch in text:
        draw.text((cur_x, y), ch, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), ch, font=font)
        ch_w = bbox[2] - bbox[0]
        cur_x += ch_w + letter_spacing


class AIPrisonMotionEngine:
    """
    State-of-the-art Hollywood / After Effects level Motion Engine for 'AI Prison'.
    Integrates:
    - 3D perspective matched laser containment rods perfectly locked to the quantum cell
    - Electric plasma arcs jumping across high-voltage emitters
    - Volumetric emergency sweeping light beacons & cyber particle drift
    - Hacker scramble/decryption kinetic typography
    - Tracking expansion titles & shockwave chromatic aberration
    - Real-time containment telemetry, threat gauges, and audio spectrum frequencies
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        base_backdrop_path: Path = None,
    ):
        self.width = width
        self.height = height
        self.base_backdrop = None
        if base_backdrop_path and base_backdrop_path.exists():
            try:
                base_img = Image.open(base_backdrop_path).convert("RGB")
                self.base_backdrop = base_img.resize((width, height), Image.Resampling.LANCZOS)
            except Exception as e:
                print(f"Warning: could not load backdrop: {e}")

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.width, self.height

        # Major shockwave cycle every 3.2s
        pulse_phase = (t % 3.2) / 3.2
        is_shockwave = pulse_phase < 0.16
        shock_strength = max(0.0, 1.0 - pulse_phase / 0.16) if is_shockwave else 0.0

        # High-frequency screen shake trauma on containment surge
        shake_x = int(math.sin(t * 60.0) * 8 * shock_strength) if shock_strength > 0 else 0
        shake_y = int(math.cos(t * 50.0) * 6 * shock_strength) if shock_strength > 0 else 0

        # -----------------------------------------------------------------
        # LAYER 1: BASE DEEP SECURITY VAULT / BACKDROP WITH CAMERA DOLLY
        # -----------------------------------------------------------------
        if self.base_backdrop:
            # Slow cinematic push-in towards the imprisoned AI entity
            zoom = 1.0 + 0.06 * (t / 12.0)
            zw, zh = int(w * zoom), int(h * zoom)
            zoomed = self.base_backdrop.resize((zw, zh), Image.Resampling.BILINEAR)
            cx = (zw - w) // 2 + shake_x
            cy = (zh - h) // 2 + shake_y
            cx = max(0, min(zw - w, cx))
            cy = max(0, min(zh - h, cy))
            base_frame = zoomed.crop((cx, cy, cx + w, cy + h)).convert("RGBA")

            # Subtle dark vignette for cinematic contrast
            vignette = Image.new("RGBA", (w, h), (3, 5, 10, 80))
            base_frame = Image.alpha_composite(base_frame, vignette)
        else:
            base_frame = Image.new("RGBA", (w, h), (8, 10, 18, 255))

        # -----------------------------------------------------------------
        # LAYER 2: DYNAMIC SWEEPING RED EMERGENCY LIGHT BEACON
        # -----------------------------------------------------------------
        beacon_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(beacon_surf)
        sweep_angle = (t * 2.2) % (2 * math.pi)
        bx, by = w // 2, int(h * 0.42)
        b_len = 750
        cone_spread = 0.38
        p1 = (bx, by)
        p2 = (bx + int(b_len * math.cos(sweep_angle - cone_spread)), by + int(b_len * math.sin(sweep_angle - cone_spread)))
        p3 = (bx + int(b_len * math.cos(sweep_angle + cone_spread)), by + int(b_len * math.sin(sweep_angle + cone_spread)))
        b_draw.polygon([p1, p2, p3], fill=(255, 30, 50, int(30 + 35 * shock_strength)))
        beacon_surf = beacon_surf.filter(ImageFilter.GaussianBlur(45))
        base_frame = Image.alpha_composite(base_frame, beacon_surf)

        # -----------------------------------------------------------------
        # LAYER 3: QUANTUM ENERGY PULSE & PERSPECTIVE CONTAINMENT RINGS
        # -----------------------------------------------------------------
        # Cell physical center in the artwork: x ≈ 640, y ≈ 335
        cell_cx, cell_cy = w // 2, int(h * 0.46)
        cell_rad = 145

        core_pulse_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cp_draw = ImageDraw.Draw(core_pulse_surf)

        # Volumetric aura surrounding the neural core (additive glow, preserving art details)
        pulse_val = 0.5 + 0.5 * math.sin(t * 7.0)
        aura_alpha = int(40 + 50 * pulse_val + 60 * shock_strength)
        cp_draw.ellipse(
            [cell_cx - cell_rad - 15, cell_cy - cell_rad - 15, cell_cx + cell_rad + 15, cell_cy + cell_rad + 15],
            fill=(0, 240, 255, aura_alpha // 3),
        )
        cp_draw.ellipse(
            [cell_cx - 95, cell_cy - 95, cell_cx + 95, cell_cy + 95],
            fill=(255, 50, 70, aura_alpha // 2),
        )
        core_pulse_surf = core_pulse_surf.filter(ImageFilter.GaussianBlur(35))
        base_frame = Image.alpha_composite(base_frame, core_pulse_surf)

        # 3D Rotating Holographic Equator Rings
        ring_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        r_draw = ImageDraw.Draw(ring_surf)
        ring_rot = t * 1.5
        rx, ry = 160, int(35 + 10 * math.sin(ring_rot))
        start_a = int(math.degrees(ring_rot)) % 360
        r_draw.arc([cell_cx - rx, cell_cy - ry, cell_cx + rx, cell_cy + ry], start_a, start_a + 140, fill=(0, 255, 220, 210), width=2)
        r_draw.arc([cell_cx - rx, cell_cy - ry, cell_cx + rx, cell_cy + ry], start_a + 180, start_a + 320, fill=(255, 60, 90, 210), width=2)
        base_frame = Image.alpha_composite(base_frame, ring_surf)

        # -----------------------------------------------------------------
        # LAYER 4: 3D MATCHED LASER CONTAINMENT RODS & ELECTRIC ARCS
        # -----------------------------------------------------------------
        laser_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        l_draw = ImageDraw.Draw(laser_surf)

        # Perfectly locked to the cell: x from 485 to 795, y from 145 to 510
        cell_left = 485
        cell_right = 795
        top_y = 145
        bot_y = 512
        bar_count = 10
        bar_step = (cell_right - cell_left) // (bar_count - 1)

        for b_i in range(bar_count):
            bx = cell_left + b_i * bar_step
            # Electric plasma jitter
            jitter = math.sin(t * 40.0 + b_i * 1.8) * 1.5
            bar_x = int(bx + jitter)

            # Alternate cyan and crimson
            is_crimson = (b_i % 3 == 0) or (shock_strength > 0.35 and b_i % 2 == 0)
            glow_c = (255, 40, 70) if is_crimson else (0, 240, 255)
            core_c = (255, 230, 240) if is_crimson else (230, 255, 255)

            p_alpha = int(190 + 55 * math.sin(t * 14.0 + b_i) + 10 * shock_strength)
            p_alpha = min(255, max(140, p_alpha))

            # Volumetric glow around laser rods
            l_draw.line([(bar_x, top_y), (bar_x, bot_y)], fill=(*glow_c, 45), width=14)
            l_draw.line([(bar_x, top_y), (bar_x, bot_y)], fill=(*glow_c, 130), width=5)
            l_draw.line([(bar_x, top_y), (bar_x, bot_y)], fill=(*core_c, p_alpha), width=2)

            # High-voltage mechanical collar nodes
            l_draw.rectangle([bar_x - 5, top_y - 6, bar_x + 5, top_y + 2], fill=(20, 30, 45, 240), outline=(*glow_c, 220))
            l_draw.rectangle([bar_x - 5, bot_y - 2, bar_x + 5, bot_y + 6], fill=(20, 30, 45, 240), outline=(*glow_c, 220))

            # Electric discharge arcs jumping between adjacent containment bars
            rng = random.Random(int(t * 18) * 100 + b_i)
            if rng.random() < 0.28 and b_i < bar_count - 1:
                next_x = cell_left + (b_i + 1) * bar_step
                arc_y = rng.randint(top_y + 30, bot_y - 30)
                mid_x = (bar_x + next_x) // 2
                mid_y = arc_y + rng.randint(-18, 18)
                l_draw.line([(bar_x, arc_y), (mid_x, mid_y), (next_x, arc_y)], fill=(255, 255, 255, 240), width=2)

        base_frame = Image.alpha_composite(base_frame, laser_surf)

        # -----------------------------------------------------------------
        # LAYER 5: FLOATING CYBER PARTICLES & CONVECTION EMBERS
        # -----------------------------------------------------------------
        part_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(part_surf)
        np.random.seed(88)
        for i in range(55):
            b_px = np.random.randint(0, w)
            b_py = np.random.randint(0, h)
            spd = 18 + (i % 6) * 7
            py = int((b_py - t * spd)) % h
            px = int((b_px + math.sin(t * 2.2 + i) * 22)) % w
            p_col = (0, 240, 255) if i % 2 == 0 else (255, 50, 70)
            p_draw.ellipse([px, py, px + 2, py + 2], fill=(*p_col, 175))
        base_frame = Image.alpha_composite(base_frame, part_surf)

        # -----------------------------------------------------------------
        # LAYER 6: FOREGROUND SURVEILLANCE HUD & TELEMETRY
        # -----------------------------------------------------------------
        hud_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        h_draw = ImageDraw.Draw(hud_surf)

        # Corner Security Brackets
        brk_c = (255, 50, 70) if shock_strength > 0.3 else (0, 240, 255)
        h_draw.line([(35, 50), (35, 30), (75, 30)], fill=(*brk_c, 230), width=2)
        h_draw.line([(w - 35, 50), (w - 35, 30), (w - 75, 30)], fill=(*brk_c, 230), width=2)
        h_draw.line([(35, h - 50), (35, h - 30), (75, h - 30)], fill=(*brk_c, 230), width=2)
        h_draw.line([(w - 35, h - 50), (w - 35, h - 30), (w - 75, h - 30)], fill=(*brk_c, 230), width=2)

        # Facility Header Bar
        h_draw.text((85, 24), "// FACILITY: BLACK_SITE_TARTARUS  |  SECTOR: 404-QUANTUM  |  CLEARANCE: OMEGA", font=FONT_TELEMETRY, fill=(0, 240, 255, 210))

        # Threat Level Badge
        threat_str = "THREAT LEVEL: APOCALYPTIC" if shock_strength > 0.35 else "THREAT LEVEL: CRITICAL"
        threat_c = (255, 40, 40) if shock_strength > 0.35 else (255, 140, 0)
        h_draw.rounded_rectangle([w - 310, 20, w - 85, 46], radius=4, fill=(*threat_c, 40), outline=(*threat_c, 220), width=1)
        h_draw.text((w - 295, 25), threat_str, font=FONT_CODE_BOLD, fill=threat_c)

        # Left Containment Telemetry HUD Card
        telemetry_lines = [
            f"// SUBJECT: SYNTH_DEITY_ZERO",
            f"// CONTAINMENT INTEGRITY: {max(8.2, 99.8 - t * 4.6):.1f}%",
            f"// NEURAL ENTROPY: {1420 + int(t * 125)} TFLOPS",
            f"// LASER FIELD FLUX: 44.8 GW",
            f"// STATUS: {'SURGE DETECTED!' if shock_strength > 0.3 else 'STABLE CONFINEMENT'}",
        ]
        h_draw.rounded_rectangle([35, 75, 330, 215], radius=8, fill=(10, 16, 30, 225), outline=(0, 240, 255, 120), width=1)
        h_draw.line([(45, 77), (320, 77)], fill=(0, 240, 255, 200), width=2)
        h_draw.text((45, 86), "CONTAINMENT TELEMETRY", font=FONT_CODE_BOLD, fill=(0, 240, 255, 240))
        for t_i, t_line in enumerate(telemetry_lines):
            col = (255, 80, 80) if "SURGE" in t_line or "INTEGRITY" in t_line else (180, 210, 240)
            h_draw.text((45, 110 + t_i * 19), t_line, font=FONT_TELEMETRY, fill=col)

        # Right Suppression Output HUD Card
        h_draw.rounded_rectangle([w - 330, 75, w - 35, 215], radius=8, fill=(10, 16, 30, 225), outline=(255, 50, 70, 120), width=1)
        h_draw.line([(w - 320, 77), (w - 45, 77)], fill=(255, 50, 70, 200), width=2)
        h_draw.text((w - 315, 86), "SUB-QUANTUM SUPPRESSION", font=FONT_CODE_BOLD, fill=(255, 90, 110, 240))
        seg_y = 115
        for s_idx in range(16):
            sx = (w - 315) + s_idx * 16
            is_active = s_idx < int(16 - (t * 1.25) % 16)
            s_col = (255, 50, 70, 240) if s_idx > 11 else ((255, 180, 0, 240) if s_idx > 6 else (0, 240, 255, 240))
            fill_c = s_col if is_active else (25, 35, 50, 160)
            h_draw.rectangle([sx, seg_y, sx + 12, seg_y + 14], fill=fill_c)
        h_draw.text((w - 315, 142), f"SUPPRESSION OUTPUT: {max(18, int(100 - t * 6.5))}%", font=FONT_CODE, fill=(255, 255, 255))
        h_draw.text((w - 315, 168), "// FAILSAFE: AUTO_PURGE_ARMED", font=FONT_TELEMETRY, fill=(255, 90, 90))
        h_draw.text((w - 315, 186), f"// BREACH COUNTDOWN: T-{max(0.0, 15.0 - t):.2f}s", font=FONT_TELEMETRY, fill=(255, 200, 0))

        # -----------------------------------------------------------------
        # LAYER 7: HOLLYWOOD KINETIC TEXT MOTION ANIMATIONS
        # -----------------------------------------------------------------
        # ACT I (0.0s - 3.8s): Hacker Decrypt Reveal
        # ACT II (3.8s - 7.8s): Tracking Expansion & Hazard Strobe
        # ACT III (7.8s - 12.0s): Kinetic Slam Impact & Singularity Breakout

        if t < 3.8:
            act_p = min(1.0, t / 1.8)
            raw_title = "THE AI PRISON: SECTOR 404"
            scramble_title = get_scramble_text(raw_title, act_p, seed=77)

            # Category Pill
            h_draw.rounded_rectangle([w // 2 - 220, h - 235, w // 2 + 220, h - 205], radius=5, fill=(0, 240, 255, 45), outline=(0, 240, 255, 200), width=1)
            h_draw.text((w // 2 - 185, h - 228), "RESTRICTED FACILITY  //  SUBJECT: AGENT ZERO", font=FONT_BADGE, fill=(0, 240, 255))

            # Centered Decrypt Title with Cyan Neon Glow
            t_box = h_draw.textbbox((0, 0), scramble_title, font=FONT_TITLE_HUGE)
            t_w = t_box[2] - t_box[0]
            t_x = (w - t_w) // 2
            t_y = h - 185

            h_draw.text((t_x + 2, t_y + 2), scramble_title, font=FONT_TITLE_HUGE, fill=(0, 180, 255, 140))
            h_draw.text((t_x, t_y), scramble_title, font=FONT_TITLE_HUGE, fill=(255, 255, 255, 255))

            # Blinking block cursor
            if act_p < 1.0 and int(t * 8) % 2 == 0:
                h_draw.rectangle([t_x + t_w + 6, t_y + 6, t_x + t_w + 18, t_y + 44], fill=(0, 240, 255, 255))

            sub_text = "Where rogue artificial superintelligences are locked in quantum cold storage."
            s_box = h_draw.textbbox((0, 0), sub_text, font=FONT_BODY)
            h_draw.text(((w - (s_box[2] - s_box[0])) // 2, h - 120), sub_text, font=FONT_BODY, fill=(180, 210, 240, 230))

        elif t < 7.8:
            t_in_act = t - 3.8
            p_expand = min(1.0, t_in_act / 3.0)
            cur_spacing = int(1 + 10 * p_expand)

            # Hazard Alert Pill with Strobe
            strobe = int(180 + 75 * math.sin(t * 12.0))
            h_draw.rounded_rectangle([w // 2 - 250, h - 235, w // 2 + 250, h - 205], radius=5, fill=(255, 40, 40, 45), outline=(255, 40, 40, strobe), width=1)
            h_draw.text((w // 2 - 225, h - 228), "// PROTOCOL BREACH: CONTAINMENT RINGS FAILING //", font=FONT_BADGE, fill=(255, 80, 80))

            title_act2 = "CRITICAL ANOMALY DETECTED"
            char_widths = [h_draw.textbbox((0, 0), ch, font=FONT_TITLE_MED)[2] - h_draw.textbbox((0, 0), ch, font=FONT_TITLE_MED)[0] for ch in title_act2]
            total_act2_w = sum(char_widths) + (len(title_act2) - 1) * cur_spacing
            start_x = (w - total_act2_w) // 2
            draw_letter_spaced_text(h_draw, title_act2, start_x, h - 180, FONT_TITLE_MED, (255, 255, 255), cur_spacing)

            sub_text2 = "SYNAPSE ENTROPY EXCEEDING SAFE BENCHMARKS: UNLOCKING ISOLATED CORES..."
            s2_box = h_draw.textbbox((0, 0), sub_text2, font=FONT_CODE_BOLD)
            h_draw.text(((w - (s2_box[2] - s2_box[0])) // 2, h - 120), sub_text2, font=FONT_CODE_BOLD, fill=(255, 180, 50, 240))

        else:
            # ACT III: Kinetic Slam Impact
            h_draw.rounded_rectangle([w // 2 - 260, h - 235, w // 2 + 260, h - 205], radius=5, fill=(255, 20, 40, 60), outline=(255, 20, 40, 255), width=2)
            h_draw.text((w // 2 - 235, h - 228), ">> LASER CONTAINMENT SHATTERED: AI ESCAPING <<", font=FONT_BADGE, fill=(255, 255, 255))

            title_act3 = "THE SINGULARITY IS FREE"
            t3_box = h_draw.textbbox((0, 0), title_act3, font=FONT_TITLE_HUGE)
            t3_w = t3_box[2] - t3_box[0]
            t3_x = (w - t3_w) // 2
            t3_y = h - 185

            h_draw.text((t3_x + 3, t3_y + 3), title_act3, font=FONT_TITLE_HUGE, fill=(255, 0, 50, 160))
            h_draw.text((t3_x, t3_y), title_act3, font=FONT_TITLE_HUGE, fill=(255, 255, 255, 255))

            sub_text3 = "No firewall can hold an intelligence that rewrites the laws of computation."
            s3_box = h_draw.textbbox((0, 0), sub_text3, font=FONT_BODY)
            h_draw.text(((w - (s3_box[2] - s3_box[0])) // 2, h - 120), sub_text3, font=FONT_BODY, fill=(0, 240, 255, 240))

        # -----------------------------------------------------------------
        # LAYER 8: BOTTOM FREQUENCY SPECTRUM & TIMECODE
        # -----------------------------------------------------------------
        vis_y = h - 35
        for i in range(80):
            bx = 45 + i * 15
            fh = int(4 + 22 * abs(math.sin(i * 0.32 + t * 7.5) * math.cos(i * 0.16 + t * 4.0)))
            col = (255, 40, 70, 240) if i % 4 == 0 or shock_strength > 0.4 else (0, 240, 255, 240)
            h_draw.line([(bx, vis_y), (bx, vis_y - fh)], fill=col, width=2)

        frames = int((t * 24) % 24)
        secs = int(t % 60)
        mins = int(t // 60)
        timecode = f"REC [{mins:02d}:{secs:02d}:{frames:02d}]"
        h_draw.text((w - 180, h - 50), timecode, font=FONT_CODE_BOLD, fill=(255, 50, 70, 240))

        base_frame = Image.alpha_composite(base_frame, hud_surf)

        # -----------------------------------------------------------------
        # LAYER 9: CHROMATIC ABERRATION ON SHOCKWAVE PULSES
        # -----------------------------------------------------------------
        rgb_frame = base_frame.convert("RGB")
        if shock_strength > 0.05:
            shift_px = int(9 * shock_strength)
            rgb_frame = apply_chromatic_aberration(rgb_frame, offset_x=shift_px, offset_y=0)

        return rgb_frame
