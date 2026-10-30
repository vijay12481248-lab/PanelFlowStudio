import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path

# Load Studio-Grade Windows Fonts
FONT_TITLE = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 32)
FONT_HEADING = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 20)
FONT_BADGE = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 15)
FONT_BODY = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 14)
FONT_BODY_BOLD = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 15)
FONT_CODE = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 13)
FONT_POWER = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 36)
FONT_SUB = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 17)

WIDTH, HEIGHT = 1280, 720


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    """Safely word-wrap text to guarantee 0% border clipping."""
    lines = []
    for raw_line in text.split("\n"):
        words = raw_line.split()
        if not words:
            continue
        curr_line = []
        for word in words:
            test_line = " ".join(curr_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                curr_line.append(word)
            else:
                if curr_line:
                    lines.append(" ".join(curr_line))
                curr_line = [word]
        if curr_line:
            lines.append(" ".join(curr_line))
    return lines


class StudioCyberHUDScene:
    """Professional Broadcast HUD Motion Graphic Scene with dynamic particles, rotating dials, and audio visualizer."""

    def __init__(
        self,
        fighter_num: str,
        fighter_name: str,
        discipline: str,
        accent_color: tuple,  # e.g. (0, 255, 170) or (249, 115, 22)
        jutsu_title: str,
        jutsu_desc: str,
        passive_title: str,
        passive_desc: str,
        power_label: str,
        power_val_str: str,
        power_sub_str: str,
        telemetry_lines: list,
        subtitle_lines: list,
        duration_sec: float = 12.0,
    ):
        self.fighter_num = fighter_num
        self.fighter_name = fighter_name
        self.discipline = discipline
        self.accent_color = accent_color
        self.jutsu_title = jutsu_title
        self.jutsu_desc = jutsu_desc
        self.passive_title = passive_title
        self.passive_desc = passive_desc
        self.power_label = power_label
        self.power_val_str = power_val_str
        self.power_sub_str = power_sub_str
        self.telemetry_lines = telemetry_lines
        self.subtitle_lines = subtitle_lines
        self.duration_sec = duration_sec

    def render_frame(self, t: float, size: tuple = (WIDTH, HEIGHT)) -> Image.Image:
        w, h = size
        
        # 1. Base Obsidian Void Canvas
        im = Image.new("RGBA", (w, h), (5, 8, 16, 255))

        # Dynamic Perspective HUD Grid
        grid_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grid_surf)
        grid_spacing = 45
        for x in range(0, w, grid_spacing):
            alpha = int(14 + 10 * math.sin(x * 0.015 + t * 1.5))
            g_draw.line([(x, 0), (x, h)], fill=(0, 220, 255, alpha), width=1)
        for y in range(0, h, grid_spacing):
            alpha = int(14 + 10 * math.cos(y * 0.015 + t * 1.5))
            g_draw.line([(0, y), (w, y)], fill=(0, 220, 255, alpha), width=1)
        im = Image.alpha_composite(im, grid_surf)

        # Volumetric Anamorphic Ambient Flares
        flare_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        f_draw = ImageDraw.Draw(flare_surf)
        f_draw.ellipse([w//2 - 600, -220, w//2 + 600, 260], fill=(0, 180, 255, 45))
        f_draw.ellipse([w - 350, 100, w + 350, 600], fill=(*self.accent_color, 35))
        flare_surf = flare_surf.filter(ImageFilter.GaussianBlur(95))
        im = Image.alpha_composite(im, flare_surf)

        # Floating Cyber Embers
        np.random.seed(int(t * 10) % 1000)
        particle_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(particle_surf)
        for i in range(40):
            px = (np.random.randint(0, w) + int(t * 22 * (i % 3 + 1))) % w
            py = (np.random.randint(0, h) - int(t * 38 * (i % 2 + 1))) % h
            p_size = np.random.randint(1, 3)
            p_col = (0, 240, 255) if i % 2 == 0 else self.accent_color
            p_draw.ellipse([px, py, px + p_size, py + p_size], fill=(*p_col, 190))
        im = Image.alpha_composite(im, particle_surf)
        draw = ImageDraw.Draw(im)

        # 2. Master Broadcast HUD Brackets
        draw.line([(30, 45), (30, 25), (65, 25)], fill=(0, 240, 255, 220), width=2)
        draw.line([(w - 30, 45), (w - 30, 25), (w - 65, 25)], fill=(0, 240, 255, 220), width=2)
        draw.line([(30, h - 45), (30, h - 25), (65, h - 25)], fill=(0, 240, 255, 220), width=2)
        draw.line([(w - 30, h - 45), (w - 30, h - 25), (w - 65, h - 25)], fill=(0, 240, 255, 220), width=2)

        # Telemetry Bar
        telemetry = f"// SYSTEM: NEO_TOKYO_COLOSSEUM  •  FREQ: 138.4 GHz  •  COMBAT_ENGINE: ONLINE  •  FPS: 60.0  •  T+{t:.2f}s"
        draw.text((75, 20), telemetry, font=FONT_CODE, fill=(0, 240, 255, 200))
        rec_pulse = int(140 + 115 * math.sin(t * 6.0))
        draw.ellipse([w - 165, 22, w - 153, 34], fill=(255, 40, 40, rec_pulse))
        draw.text((w - 145, 19), "LIVE BROADCAST", font=FONT_CODE, fill=(255, 90, 90, 240))

        # 3. Main Glassmorphic Fighter HUD Card (Entrance Animation: spring slide from left)
        c_enter = min(1.0, t / 0.7)
        c_ease = 1.0 + 1.4 * math.pow(c_enter - 1.0, 3) + 1.4 * math.pow(c_enter - 1.0, 2) if c_enter < 1.0 else 1.0
        card_x = int(55 + (1.0 - c_ease) * -120)
        card_y = 65
        card_w, card_h = 740, 430

        card_surf = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(card_surf)

        c_draw.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=16, fill=(10, 16, 32, 238), outline=(*self.accent_color, 130), width=1)
        c_draw.line([(16, 2), (card_w - 16, 2)], fill=(*self.accent_color, 240), width=2)

        cb = 18
        c_draw.line([(8, 8 + cb), (8, 8), (8 + cb, 8)], fill=(*self.accent_color, 255), width=2)
        c_draw.line([(card_w - 8, 8 + cb), (card_w - 8, 8), (card_w - 8 - cb, 8)], fill=(*self.accent_color, 255), width=2)
        c_draw.line([(8, card_h - 8 - cb), (8, card_h - 8), (8 + cb, card_h - 8)], fill=(*self.accent_color, 255), width=2)
        c_draw.line([(card_w - 8, card_h - 8 - cb), (card_w - 8, card_h - 8), (card_w - 8 - cb, card_h - 8)], fill=(*self.accent_color, 255), width=2)

        # Category Pill
        c_draw.rounded_rectangle([25, 22, 250, 52], radius=6, fill=(*self.accent_color, 40), outline=(*self.accent_color, 200), width=1)
        c_draw.text((36, 28), self.fighter_num, font=FONT_BADGE, fill=self.accent_color)
        c_draw.text((170, 28), "[S-TIER]", font=FONT_BADGE, fill=(255, 255, 255, 230))

        c_draw.text((25, 62), self.fighter_name, font=FONT_TITLE, fill=(255, 255, 255, 255))
        c_draw.text((25, 102), self.discipline, font=FONT_HEADING, fill=(*self.accent_color, 230))

        c_draw.line([(25, 134), (card_w - 25, 134)], fill=(40, 60, 95, 220), width=1)
        for tick_x in range(25, card_w - 25, 25):
            c_draw.line([(tick_x, 131), (tick_x, 137)], fill=(0, 240, 255, 160), width=1)

        # Sub-Card 1: Jutsu (Width = 335px, Text Padding = 15px)
        c_draw.rounded_rectangle([25, 150, 360, 275], radius=10, fill=(14, 22, 44, 210), outline=(*self.accent_color, 90), width=1)
        c_draw.text((38, 162), "PRIMARY ARTIFACT / JUTSU", font=FONT_CODE, fill=(*self.accent_color, 240))
        c_draw.text((38, 182), self.jutsu_title, font=FONT_BODY_BOLD, fill=(255, 255, 255, 255))
        lines1 = wrap_text(self.jutsu_desc, FONT_BODY, 305, c_draw)
        for l_idx, ln in enumerate(lines1[:2]):
            c_draw.text((38, 206 + l_idx * 20), ln, font=FONT_BODY, fill=(165, 180, 210, 240))

        # Sub-Card 2: Passive Immunity / Debuff
        is_weak = "GIL" in self.passive_title or "WEAKNESS" in self.passive_title
        sec_color = (239, 68, 68) if is_weak else (34, 197, 94)
        c_draw.rounded_rectangle([380, 150, card_w - 25, 275], radius=10, fill=(14, 22, 44, 210), outline=(*sec_color, 90), width=1)
        c_draw.text((395, 162), "SYSTEM ATTRIBUTE", font=FONT_CODE, fill=(*sec_color, 240))
        c_draw.text((395, 182), self.passive_title, font=FONT_BODY_BOLD, fill=(255, 255, 255, 255))
        lines2 = wrap_text(self.passive_desc, FONT_BODY, 305, c_draw)
        for l_idx, ln in enumerate(lines2[:2]):
            c_draw.text((395, 206 + l_idx * 20), ln, font=FONT_BODY, fill=(165, 180, 210, 240))

        # 24-Segment LED Energy Bar
        c_draw.text((25, 292), "CORE SYNAPSE INTEGRITY [100% NOMINAL]:", font=FONT_CODE, fill=(0, 240, 255, 220))
        seg_w, seg_gap, seg_x, seg_y = 26, 4, 25, 314
        active_segs = min(24, int((t / 2.0) * 24)) if t < 2.0 else 24
        for s_i in range(24):
            sx = seg_x + s_i * (seg_w + seg_gap)
            if s_i < active_segs:
                col = (0, 240, 255, 245) if s_i < 16 else ((255, 200, 0, 245) if s_i < 21 else (*self.accent_color, 245))
            else:
                col = (20, 30, 50, 160)
            c_draw.rounded_rectangle([sx, seg_y, sx + seg_w, seg_y + 16], radius=3, fill=col)

        c_draw.text((25, 355), "// HARDWARE: CLOUD_CLUSTER_V4  •  CACHE_MISS: 0.02%  •  THREAD_SYNC: OK", font=FONT_CODE, fill=(110, 135, 175, 220))

        im.alpha_composite(card_surf, (card_x, card_y))

        # 4. Right Side HUD Dial & Power Telemetry
        r_enter = min(1.0, max(0.0, (t - 0.3) / 0.7))
        r_ease = 1.0 + 1.4 * math.pow(r_enter - 1.0, 3) + 1.4 * math.pow(r_enter - 1.0, 2) if r_enter < 1.0 else 1.0
        right_x = int(815 + (1.0 - r_ease) * 120)
        right_y = 65
        right_w, right_h = 410, 430

        dial_surf = Image.new("RGBA", (right_w, right_h), (0, 0, 0, 0))
        d_draw = ImageDraw.Draw(dial_surf)

        d_draw.rounded_rectangle([0, 0, right_w - 1, right_h - 1], radius=16, fill=(10, 16, 32, 238), outline=(0, 240, 255, 130), width=1)
        d_draw.line([(16, 2), (right_w - 16, 2)], fill=(0, 240, 255, 240), width=2)

        cx, cy = right_w // 2, 138
        radius = 92

        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            x1 = cx + (radius + 8) * math.cos(rad)
            y1 = cy + (radius + 8) * math.sin(rad)
            x2 = cx + (radius + 15) * math.cos(rad)
            y2 = cy + (radius + 15) * math.sin(rad)
            d_draw.line([(x1, y1), (x2, y2)], fill=(0, 240, 255, 160), width=1)

        d_draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(0, 240, 255, 180), width=2)
        arc_start = int(t * 110) % 360
        d_draw.arc([cx - radius + 8, cy - radius + 8, cx + radius - 8, cy + radius - 8], arc_start, arc_start + 160, fill=(*self.accent_color, 255), width=4)

        # Mathematical Text Centering
        pl_bbox = d_draw.textbbox((0, 0), self.power_label, font=FONT_CODE)
        pl_w = pl_bbox[2] - pl_bbox[0]
        d_draw.text((cx - pl_w // 2, cy - 42), self.power_label, font=FONT_CODE, fill=(0, 240, 255, 220))

        pw_bbox = d_draw.textbbox((0, 0), self.power_val_str, font=FONT_POWER)
        pw_w = pw_bbox[2] - pw_bbox[0]
        d_draw.text((cx - pw_w // 2, cy - 18), self.power_val_str, font=FONT_POWER, fill=(255, 255, 255, 255))

        ps_bbox = d_draw.textbbox((0, 0), self.power_sub_str, font=FONT_BADGE)
        ps_w = ps_bbox[2] - ps_bbox[0]
        d_draw.text((cx - ps_w // 2, cy + 24), self.power_sub_str, font=FONT_BADGE, fill=self.accent_color)

        d_draw.line([(25, 260), (right_w - 25, 260)], fill=(40, 60, 95, 220), width=1)
        for l_i, line in enumerate(self.telemetry_lines):
            d_draw.text((25, 275 + l_i * 25), line, font=FONT_CODE, fill=(255, 255, 255, 240) if l_i == 0 else (0, 240, 255, 230))

        im.alpha_composite(dial_surf, (right_x, right_y))

        # 5. Broadcast Lower Third / Commentary Banner with Dynamic Spectrum Visualizer
        sub_y = 515
        banner_surf = Image.new("RGBA", (w, 180), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(banner_surf)
        b_draw.rounded_rectangle([55, 0, w - 55, 175], radius=14, fill=(7, 12, 24, 245), outline=(0, 240, 255, 150), width=1)
        b_draw.line([(70, 2), (w - 70, 2)], fill=(0, 240, 255, 220), width=2)

        # Commentary Badge with alpha blending
        b_draw.rounded_rectangle([75, 14, 320, 38], radius=4, fill=(0, 240, 255, 45), outline=(0, 240, 255, 190), width=1)
        b_draw.text((86, 18), "LIVE TOURNAMENT COMMENTARY", font=FONT_CODE, fill=(0, 240, 255, 255))

        if len(self.subtitle_lines) > 0:
            b_draw.text((75, 48), self.subtitle_lines[0], font=FONT_SUB, fill=(255, 255, 255, 255))
        if len(self.subtitle_lines) > 1:
            b_draw.text((75, 76), self.subtitle_lines[1], font=FONT_SUB, fill=(255, 255, 255, 255))

        # 64-Bar Audio Spectrum Visualizer
        vis_start_x = 75
        vis_y = 158
        for i in range(64):
            bx = vis_start_x + i * 17
            freq_h = int(6 + 24 * abs(math.sin(i * 0.35 + t * 6.0) * math.cos(i * 0.15 + t * 3.0)))
            bar_col = (0, 240, 255, 240) if i < 45 else (*self.accent_color, 240)
            b_draw.line([(bx, vis_y), (bx, vis_y - freq_h)], fill=bar_col, width=3)

        im.alpha_composite(banner_surf, (0, sub_y))

        return im.convert("RGB")


class StudioOutroHUDScene:
    """Professional Broadcast Outro & Match Verdict HUD Motion Graphic Scene."""

    def __init__(
        self,
        title: str = "GRAND COMPILER CHAMPIONSHIP  •  MATCH RESULTS",
        verdict_str: str = "VERDICT: MAXIMUM RUNTIME COLLISION!",
        verdict_sub: str = "Both warriors shattered the benchmark latency ceiling! Stalemate declared.",
        teaser_title: str = "EPISODE 2 TEASER: THE C++ GRANDMASTER AWAKENS",
        teaser_desc: str = "Ancient pointer arithmetic stirs in the dark. Manual memory allocation threatens Neo-Tokyo!",
        duration_sec: float = 8.0,
    ):
        self.title = title
        self.verdict_str = verdict_str
        self.verdict_sub = verdict_sub
        self.teaser_title = teaser_title
        self.teaser_desc = teaser_desc
        self.duration_sec = duration_sec

    def render_frame(self, t: float, size: tuple = (WIDTH, HEIGHT)) -> Image.Image:
        w, h = size

        # 1. Base Obsidian Void Canvas
        im = Image.new("RGBA", (w, h), (7, 9, 20, 255))

        # Dynamic Perspective Grid
        grid_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grid_surf)
        grid_spacing = 45
        for x in range(0, w, grid_spacing):
            alpha = int(14 + 10 * math.sin(x * 0.015 + t * 1.2))
            g_draw.line([(x, 0), (x, h)], fill=(168, 85, 247, alpha), width=1)
        for y in range(0, h, grid_spacing):
            alpha = int(14 + 10 * math.cos(y * 0.015 + t * 1.2))
            g_draw.line([(0, y), (w, y)], fill=(0, 220, 255, alpha), width=1)
        im = Image.alpha_composite(im, grid_surf)

        # Volumetric Violet & Cyan Spotlight Flares
        flare_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        f_draw = ImageDraw.Draw(flare_surf)
        f_draw.ellipse([w//2 - 500, -200, w//2 + 500, 220], fill=(168, 85, 247, 50))
        f_draw.ellipse([80, 200, 500, 600], fill=(0, 240, 180, 25))
        f_draw.ellipse([w - 500, 200, w - 80, 600], fill=(249, 115, 22, 25))
        flare_surf = flare_surf.filter(ImageFilter.GaussianBlur(90))
        im = Image.alpha_composite(im, flare_surf)

        # Floating Particles
        np.random.seed(int(t * 8) % 1000)
        particle_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(particle_surf)
        for i in range(35):
            px = (np.random.randint(0, w) + int(t * 18 * (i % 3 + 1))) % w
            py = (np.random.randint(0, h) - int(t * 30 * (i % 2 + 1))) % h
            p_size = np.random.randint(1, 3)
            p_col = (168, 85, 247) if i % 2 == 0 else (0, 240, 255)
            p_draw.ellipse([px, py, px + p_size, py + p_size], fill=(*p_col, 180))
        im = Image.alpha_composite(im, particle_surf)
        draw = ImageDraw.Draw(im)

        # Master HUD Corner Brackets
        draw.line([(30, 45), (30, 25), (65, 25)], fill=(168, 85, 247, 220), width=2)
        draw.line([(w - 30, 45), (w - 30, 25), (w - 65, 25)], fill=(168, 85, 247, 220), width=2)
        draw.line([(30, h - 45), (30, h - 25), (65, h - 25)], fill=(168, 85, 247, 220), width=2)
        draw.line([(w - 30, h - 45), (w - 30, h - 25), (w - 65, h - 25)], fill=(168, 85, 247, 220), width=2)

        # Telemetry
        telemetry = f"// ARENA_STATE: POST_MATCH_RESOLUTION  •  LATENCY: 0.04ms  •  DATA_LOGS: ARCHIVED  •  T+{t:.2f}s"
        draw.text((75, 20), telemetry, font=FONT_CODE, fill=(168, 85, 247, 220))
        draw.text((w - 220, 20), "MATCH VERDICT: FINAL", font=FONT_CODE, fill=(0, 240, 255, 240))

        # Entrance Animation
        e_p = min(1.0, t / 0.6)
        e_ease = 1.0 + 1.4 * math.pow(e_p - 1.0, 3) + 1.4 * math.pow(e_p - 1.0, 2) if e_p < 1.0 else 1.0

        # Top Verdict Glass Card
        v_surf = Image.new("RGBA", (w - 110, 160), (0, 0, 0, 0))
        v_draw = ImageDraw.Draw(v_surf)
        vw, vh = w - 110, 160
        v_draw.rounded_rectangle([0, 0, vw - 1, vh - 1], radius=14, fill=(11, 16, 32, 235), outline=(168, 85, 247, 140), width=1)
        v_draw.line([(16, 2), (vw - 16, 2)], fill=(168, 85, 247, 230), width=2)

        # Verdict Badge
        v_draw.rounded_rectangle([25, 18, 290, 48], radius=6, fill=(168, 85, 247, 45), outline=(168, 85, 247, 220), width=1)
        v_draw.text((36, 24), "OFFICIAL ARBITRATION", font=FONT_BADGE, fill=(216, 180, 254))
        v_draw.text((225, 24), "[DRAW]", font=FONT_BADGE, fill=(255, 255, 255))

        v_draw.text((25, 58), self.verdict_str, font=FONT_TITLE, fill=(255, 255, 255))
        v_draw.text((25, 102), self.verdict_sub, font=FONT_SUB, fill=(196, 181, 253))

        im.alpha_composite(v_surf, (55, int(60 + (1.0 - e_ease) * -60)))

        # Middle Dual Fighter Summary Cards (Side by Side)
        m_y = 240
        box_w = (w - 140) // 2
        box_h = 175

        # Python Summary Box (Emerald)
        py_surf = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        py_draw = ImageDraw.Draw(py_surf)
        py_draw.rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=12, fill=(8, 20, 24, 235), outline=(0, 255, 170, 110), width=1)
        py_draw.line([(12, 2), (box_w - 12, 2)], fill=(0, 255, 170, 220), width=2)
        py_draw.text((20, 16), "FIGHTER 01: PYTHON (SERPENT SAGE)", font=FONT_HEADING, fill=(0, 255, 170))
        py_draw.text((20, 48), "// FINAL STATS: 8.4M OPS/SEC (NUMPY VECTOR ENGINE)", font=FONT_CODE, fill=(200, 240, 230))
        py_draw.text((20, 72), "// TACTICAL STATUS: UNSHAKEABLE AI MONOPOLY", font=FONT_CODE, fill=(150, 220, 200))
        py_draw.text((20, 96), "// JUTSU EFFECT: HIGH-SPEED MODEL CONVERGENCE", font=FONT_CODE, fill=(150, 220, 200))
        py_draw.rounded_rectangle([20, 126, 220, 154], radius=4, fill=(0, 255, 170, 35), outline=(0, 255, 170, 160), width=1)
        py_draw.text((28, 131), "RANKING: S-TIER SHINOBI", font=FONT_CODE, fill=(0, 255, 170))
        im.alpha_composite(py_surf, (55, m_y))

        # Rust Summary Box (Molten Amber)
        rust_surf = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        rust_draw = ImageDraw.Draw(rust_surf)
        rust_draw.rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=12, fill=(24, 14, 8, 235), outline=(249, 115, 22, 110), width=1)
        rust_draw.line([(12, 2), (box_w - 12, 2)], fill=(249, 115, 22, 220), width=2)
        rust_draw.text((20, 16), "FIGHTER 02: RUST (IRONCLAD RONIN)", font=FONT_HEADING, fill=(249, 115, 22))
        rust_draw.text((20, 48), "// FINAL STATS: POWER LEVEL OVER 9,000 (0-COST)", font=FONT_CODE, fill=(255, 220, 190))
        rust_draw.text((20, 72), "// TACTICAL STATUS: 0 SEGFAULTS • 100% MEMORY SAFE", font=FONT_CODE, fill=(255, 190, 150))
        rust_draw.text((20, 96), "// JUTSU EFFECT: IMPENETRABLE CONCURRENCY BARRIER", font=FONT_CODE, fill=(255, 190, 150))
        rust_draw.rounded_rectangle([20, 126, 220, 154], radius=4, fill=(249, 115, 22, 35), outline=(249, 115, 22, 160), width=1)
        rust_draw.text((28, 131), "RANKING: S-TIER RONIN", font=FONT_CODE, fill=(249, 115, 22))
        im.alpha_composite(rust_surf, (55 + box_w + 30, m_y))

        # Bottom Teaser HUD Card
        tea_y = 435
        tea_surf = Image.new("RGBA", (w - 110, 245), (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(tea_surf)
        tw, th = w - 110, 245
        t_draw.rounded_rectangle([0, 0, tw - 1, th - 1], radius=14, fill=(8, 12, 24, 245), outline=(236, 72, 153, 140), width=1)
        t_draw.line([(16, 2), (tw - 16, 2)], fill=(236, 72, 153, 230), width=2)

        # Teaser Pill (Enlarged to 310px to prevent word collision)
        t_draw.rounded_rectangle([25, 18, 310, 48], radius=6, fill=(236, 72, 153, 40), outline=(236, 72, 153, 220), width=1)
        t_draw.text((36, 24), "NEXT EPISODE TEASER", font=FONT_BADGE, fill=(244, 114, 182))
        t_draw.text((245, 24), "[SOON]", font=FONT_BADGE, fill=(255, 255, 255))

        t_draw.text((25, 58), self.teaser_title, font=FONT_HEADING, fill=(255, 255, 255))
        
        # Word wrap teaser text cleanly
        teaser_clean = self.teaser_desc.replace("\nSubscribe to PanelFlow Anime Showdown for Episode 2!", "").strip()
        t_lines = wrap_text(teaser_clean, FONT_BODY, tw - 50, t_draw)
        for t_idx, t_ln in enumerate(t_lines[:2]):
            t_draw.text((25, 88 + t_idx * 20), t_ln, font=FONT_BODY, fill=(203, 213, 225))

        t_draw.text((25, 134), "SUBSCRIBE TO PANELFLOW ANIME SHOWDOWN FOR EPISODE 2!", font=FONT_BODY_BOLD, fill=(236, 72, 153))

        # Audio Spectrum Visualizer inside teaser card
        vis_start_x = 25
        vis_y = 225
        for i in range(68):
            bx = vis_start_x + i * 16
            freq_h = int(6 + 26 * abs(math.sin(i * 0.38 + t * 5.5) * math.cos(i * 0.18 + t * 2.8)))
            bar_col = (236, 72, 153, 240) if i < 34 else (168, 85, 247, 240)
            t_draw.line([(bx, vis_y), (bx, vis_y - freq_h)], fill=bar_col, width=3)

        im.alpha_composite(tea_surf, (55, tea_y))

        return im.convert("RGB")
