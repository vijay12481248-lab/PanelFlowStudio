import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
from pathlib import Path

# Load System TrueType Fonts
FONT_HERO = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 52)
FONT_HERO_MED = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 38)
FONT_HEAD = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 26)
FONT_BADGE = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 14)
FONT_BODY = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 17)
FONT_BODY_BOLD = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 17)
FONT_MONO = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 13)
FONT_METRIC_NUM = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 40)
FONT_METRIC_LBL = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 13)


def ease_out_expo(p: float) -> float:
    return 1.0 if p >= 1.0 else 1.0 - math.pow(2, -10 * p)


def ease_out_back(p: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1.0 + c3 * math.pow(p - 1.0, 3) + c1 * math.pow(p - 1.0, 2) if p < 1.0 else 1.0


def ease_in_out_sine(p: float) -> float:
    return -(math.cos(math.pi * p) - 1.0) / 2.0


def draw_shimmer_text(
    target_surf: Image.Image,
    text: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    base_color: tuple,
    shimmer_color: tuple,
    shimmer_phase: float,  # 0.0 to 1.0
):
    """
    Renders Apple Keynote style text with a sweeping specular highlight gradient wave.
    """
    w, h = target_surf.size
    # Temporary mask canvas for text
    mask_img = Image.new("L", (w, h), 0)
    m_draw = ImageDraw.Draw(mask_img)
    m_draw.text((x, y), text, font=font, fill=255)

    bbox = m_draw.textbbox((x, y), text, font=font)
    tw = max(1, bbox[2] - bbox[0])

    # Gradient surface
    grad_surf = Image.new("RGBA", (w, h), (*base_color, 255))
    g_draw = ImageDraw.Draw(grad_surf)

    # Shimmer band position
    shimmer_x = bbox[0] - 100 + int((tw + 200) * shimmer_phase)
    band_w = 90
    for i in range(-band_w, band_w):
        factor = 1.0 - abs(i) / band_w
        gx = shimmer_x + i
        if 0 <= gx < w:
            # Blend shimmer color
            col = tuple(int(base_color[c] + (shimmer_color[c] - base_color[c]) * factor) for c in range(3))
            g_draw.line([(gx, bbox[1] - 5), (gx, bbox[3] + 5)], fill=(*col, 255), width=1)

    target_surf.paste(grad_surf, (0, 0), mask=mask_img)


def draw_letter_spaced(
    draw: ImageDraw.ImageDraw,
    text: str,
    cx: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple,
    spacing: int,
):
    """Draws centered text with dynamic tracking/kerning."""
    char_widths = [draw.textbbox((0, 0), ch, font=font)[2] - draw.textbbox((0, 0), ch, font=font)[0] for ch in text]
    total_w = sum(char_widths) + (len(text) - 1) * spacing
    start_x = cx - total_w // 2
    cur_x = start_x
    for i, ch in enumerate(text):
        draw.text((cur_x, y), ch, font=font, fill=fill)
        cur_x += char_widths[i] + spacing


class ProceduralKeynoteRenderer:
    """
    100% Code-Driven, Zero-Image Procedural Motion Graphics Presentation Engine.
    Emulates AAA Apple Keynote / Stripe Press / OpenAI DevDay aesthetic:
    - Deep Obsidian canvas `#030712`
    - Undulating volumetric caustics & organic mesh ribbons
    - 3D particle dust with camera drift
    - Kinetic staggered word masking & spring physics
    - Sweeping specular gradient shimmers
    - Frosted glass cards with specular highlight borders
    - Smooth momentum rolling metric counters
    """

    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height

    def render_background_caustics(self, t: float) -> Image.Image:
        """Renders luxury Apple/Stripe-style volumetric fluid lighting ribbons."""
        w, h = self.width, self.height
        bg = Image.new("RGBA", (w, h), (4, 7, 16, 255))

        # Floating Volumetric Colored Light Orbs (Lissajous curves)
        light_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        l_draw = ImageDraw.Draw(light_surf)

        # Orb 1: Deep Indigo / Violet
        x1 = int(w * 0.35 + 240 * math.sin(t * 0.6))
        y1 = int(h * 0.45 + 160 * math.cos(t * 0.4))
        r1 = 380
        l_draw.ellipse([x1 - r1, y1 - r1, x1 + r1, y1 + r1], fill=(124, 58, 237, 70))

        # Orb 2: Electric Cyan
        x2 = int(w * 0.68 + 260 * math.cos(t * 0.5 + 1.2))
        y2 = int(h * 0.40 + 180 * math.sin(t * 0.7 + 0.8))
        r2 = 340
        l_draw.ellipse([x2 - r2, y2 - r2, x2 + r2, y2 + r2], fill=(6, 182, 212, 60))

        # Orb 3: Luminous Emerald / Amber
        x3 = int(w * 0.50 + 200 * math.sin(t * 0.8 + 2.4))
        y3 = int(h * 0.65 + 140 * math.cos(t * 0.6 + 1.8))
        r3 = 300
        l_draw.ellipse([x3 - r3, y3 - r3, x3 + r3, y3 + r3], fill=(16, 185, 129, 45))

        # Heavy Gaussian Blur to create smooth gradient mesh
        light_surf = light_surf.filter(ImageFilter.GaussianBlur(110))
        bg = Image.alpha_composite(bg, light_surf)

        # 3D Silk Ribbons / Undulating Sine Wave Lines
        ribbon_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        r_draw = ImageDraw.Draw(ribbon_surf)

        num_ribbons = 8
        for r_i in range(num_ribbons):
            phase_offset = r_i * 0.42
            pts = []
            for px in range(0, w + 20, 20):
                nx = px / w
                # Multidimensional wave superposition
                wave1 = math.sin(nx * 3.5 + t * 1.2 + phase_offset) * 85
                wave2 = math.cos(nx * 6.2 - t * 0.8 + phase_offset * 1.5) * 45
                wave3 = math.sin(nx * 1.8 + t * 0.5) * 60
                py = int(h * 0.52 + wave1 + wave2 + wave3 + (r_i - 4) * 22)
                pts.append((px, py))

            # Color gradation across ribbons (Cyan to Purple to Emerald)
            f = r_i / max(1, num_ribbons - 1)
            col_r = int(6 + f * 140)
            col_g = int(182 - f * 80)
            col_b = int(212 + f * 43)
            r_alpha = int(45 + 30 * math.sin(t * 1.5 + r_i))

            for p_idx in range(len(pts) - 1):
                r_draw.line([pts[p_idx], pts[p_idx + 1]], fill=(col_r, col_g, col_b, r_alpha), width=2)

        # Soft blur on ribbons for glowing depth
        ribbon_glow = ribbon_surf.filter(ImageFilter.GaussianBlur(14))
        bg = Image.alpha_composite(bg, ribbon_glow)
        bg = Image.alpha_composite(bg, ribbon_surf)

        # 3D Depth Particle Dust
        dust_surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d_draw = ImageDraw.Draw(dust_surf)
        np.random.seed(99)
        for i in range(70):
            bx = np.random.randint(0, w)
            by = np.random.randint(0, h)
            spd = 12 + (i % 5) * 8
            py = int((by - t * spd)) % h
            px = int((bx + math.sin(t * 1.8 + i) * 25)) % w
            p_size = 1 if i % 4 != 0 else 2
            d_draw.ellipse([px, py, px + p_size, py + p_size], fill=(255, 255, 255, 140))
        bg = Image.alpha_composite(bg, dust_surf)

        return bg

    def render_frame(self, t: float) -> Image.Image:
        w, h = self.width, self.height
        canvas = self.render_background_caustics(t)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Top Keynote Header (Apple/OpenAI DevDay style)
        draw.text((60, 42), "SYNTHESIS SPECIAL EVENT", font=FONT_BADGE, fill=(148, 163, 184, 230))
        draw.text((w - 240, 42), "KEYNOTE REVEAL // 2026", font=FONT_MONO, fill=(148, 163, 184, 200))
        draw.line([(60, 68), (w - 60, 68)], fill=(255, 255, 255, 30), width=1)

        # -------------------------------------------------------------
        # 4 DRAMATIC KEYNOTE ACTS
        # -------------------------------------------------------------
        if t < 4.0:
            # ACT 1 (0.0s - 4.0s): THE PROVOCATION
            # "WHAT IF INTELLIGENCE HAD NO LIMITS?"
            p1 = min(1.0, t / 1.0)
            e1 = ease_out_expo(p1)

            # Category Pill
            draw.rounded_rectangle([w // 2 - 160, 180, w // 2 + 160, 212], radius=16, fill=(255, 255, 255, 15), outline=(255, 255, 255, 45), width=1)
            draw.text((w // 2 - 128, 189), "THE NEXT EVOLUTION", font=FONT_BADGE, fill=(167, 139, 250))

            # Main Question (Staggered Word Masking)
            line1 = "WHAT IF INTELLIGENCE"
            line2 = "HAD NO BOUNDARIES?"

            l1_box = draw.textbbox((0, 0), line1, font=FONT_HERO)
            l1_w = l1_box[2] - l1_box[0]
            l2_box = draw.textbbox((0, 0), line2, font=FONT_HERO)
            l2_w = l2_box[2] - l2_box[0]

            y1 = int(250 + (1.0 - e1) * 50)
            y2 = int(320 + (1.0 - e1) * 50)

            # Apple-style Specular Shimmer sweep across the letters
            shimmer_p = (t % 2.5) / 2.5
            draw_shimmer_text(overlay, line1, (w - l1_w) // 2, y1, FONT_HERO, (255, 255, 255), (147, 197, 253), shimmer_p)
            draw_shimmer_text(overlay, line2, (w - l2_w) // 2, y2, FONT_HERO, (255, 255, 255), (196, 181, 253), shimmer_p)

            # Sub-headline
            p_sub = min(1.0, max(0.0, (t - 0.8) / 0.8))
            e_sub = ease_out_expo(p_sub)
            sub = "A breakthrough architecture that blurs the boundary between thought and execution."
            sub_w = draw.textbbox((0, 0), sub, font=FONT_BODY)[2] - draw.textbbox((0, 0), sub, font=FONT_BODY)[0]
            draw.text(((w - sub_w) // 2, int(420 + (1.0 - e_sub) * 30)), sub, font=FONT_BODY, fill=(148, 163, 184, int(240 * e_sub)))

        elif t < 8.0:
            # ACT 2 (4.0s - 8.0s): THE METRIC BENCHMARKS
            # Rolling counters, frosted glass cards
            t_act = t - 4.0
            p2 = min(1.0, t_act / 0.8)
            e2 = ease_out_expo(p2)

            # Header
            draw.rounded_rectangle([w // 2 - 180, 130, w // 2 + 180, 162], radius=16, fill=(6, 182, 212, 25), outline=(6, 182, 212, 120), width=1)
            draw.text((w // 2 - 145, 139), "PERFORMANCE ARCHITECTURE", font=FONT_BADGE, fill=(6, 182, 212))

            h_title = "ENGINEERED FOR THE IMPOSSIBLE"
            ht_w = draw.textbbox((0, 0), h_title, font=FONT_HERO_MED)[2] - draw.textbbox((0, 0), h_title, font=FONT_HERO_MED)[0]
            draw.text(((w - ht_w) // 2, 180), h_title, font=FONT_HERO_MED, fill=(255, 255, 255, 255))

            # 3 Frosted Glass Metric Cards
            card_w = 340
            card_h = 240
            spacing = 40
            total_cards_w = 3 * card_w + 2 * spacing
            start_x = (w - total_cards_w) // 2
            card_y = int(280 + (1.0 - e2) * 60)

            # Card 1: Latency
            c1_x = start_x
            draw.rounded_rectangle([c1_x, card_y, c1_x + card_w, card_y + card_h], radius=18, fill=(15, 23, 42, 210), outline=(56, 189, 248, 90), width=1)
            draw.line([(c1_x + 20, card_y + 2), (c1_x + card_w - 20, card_y + 2)], fill=(56, 189, 248, 200), width=2)
            draw.text((c1_x + 28, card_y + 26), "RESPONSE LATENCY", font=FONT_METRIC_LBL, fill=(56, 189, 248))
            # Rolling counter 1: 0.00 -> 0.42 ms
            lat_val = min(0.42, (t_act / 1.5) * 0.42)
            draw.text((c1_x + 28, card_y + 60), f"{lat_val:.2f} ms", font=FONT_METRIC_NUM, fill=(255, 255, 255))
            draw.text((c1_x + 28, card_y + 120), "Sub-millisecond inference.", font=FONT_BODY_BOLD, fill=(241, 245, 249))
            draw.text((c1_x + 28, card_y + 150), "Zero perception barrier\ninstantaneous streaming.", font=FONT_BODY, fill=(148, 163, 184))

            # Card 2: Compute Throughput
            c2_x = start_x + card_w + spacing
            draw.rounded_rectangle([c2_x, card_y, c2_x + card_w, card_y + card_h], radius=18, fill=(15, 23, 42, 210), outline=(168, 85, 247, 90), width=1)
            draw.line([(c2_x + 20, card_y + 2), (c2_x + card_w - 20, card_y + 2)], fill=(168, 85, 247, 200), width=2)
            draw.text((c2_x + 28, card_y + 26), "PEAK COMPUTE FLUX", font=FONT_METRIC_LBL, fill=(168, 85, 247))
            # Rolling counter 2: 0 -> 125,000 TFLOPS
            tflops = min(125000, int((t_act / 1.5) * 125000))
            draw.text((c2_x + 28, card_y + 60), f"{tflops:,}", font=FONT_METRIC_NUM, fill=(255, 255, 255))
            draw.text((c2_x + 28, card_y + 120), "125K Tensor Operations.", font=FONT_BODY_BOLD, fill=(241, 245, 249))
            draw.text((c2_x + 28, card_y + 150), "Hyper-parallel silicon\nsparse neural routing.", font=FONT_BODY, fill=(148, 163, 184))

            # Card 3: Energy Efficiency
            c3_x = start_x + 2 * (card_w + spacing)
            draw.rounded_rectangle([c3_x, card_y, c3_x + card_w, card_y + card_h], radius=18, fill=(15, 23, 42, 210), outline=(16, 185, 129, 90), width=1)
            draw.line([(c3_x + 20, card_y + 2), (c3_x + card_w - 20, card_y + 2)], fill=(16, 185, 129, 200), width=2)
            draw.text((c3_x + 28, card_y + 26), "ENERGY EFFICIENCY", font=FONT_METRIC_LBL, fill=(16, 185, 129))
            # Rolling counter 3: 0 -> 99.98%
            eff_val = min(99.98, (t_act / 1.5) * 99.98)
            draw.text((c3_x + 28, card_y + 60), f"{eff_val:.2f}%", font=FONT_METRIC_NUM, fill=(255, 255, 255))
            draw.text((c3_x + 28, card_y + 120), "Near-Zero Joule Decay.", font=FONT_BODY_BOLD, fill=(241, 245, 249))
            draw.text((c3_x + 28, card_y + 150), "Green neuromorphic nodes\npowered by light.", font=FONT_BODY, fill=(148, 163, 184))

            # Bottom Subtitle
            b_text = "Benchmarked across 100 million concurrent edge clusters."
            bw = draw.textbbox((0, 0), b_text, font=FONT_BODY)[2] - draw.textbbox((0, 0), b_text, font=FONT_BODY)[0]
            draw.text(((w - bw) // 2, 570), b_text, font=FONT_BODY, fill=(148, 163, 184, 210))

        elif t < 12.0:
            # ACT 3 (8.0s - 12.0s): THE CAPABILITY TRINITY
            # "AUTONOMOUS. MULTIMODAL. INSTANTANEOUS."
            t_act = t - 8.0

            words = ["AUTONOMOUS.", "MULTIMODAL.", "INSTANTANEOUS."]
            colors = [(56, 189, 248), (192, 132, 252), (52, 211, 153)]

            # Staggered reveal for each word
            y_base = 220
            for w_idx, word in enumerate(words):
                w_start = w_idx * 0.7
                p_w = min(1.0, max(0.0, (t_act - w_start) / 0.6))
                e_w = ease_out_back(p_w)

                cur_y = int(y_base + w_idx * 95 + (1.0 - e_w) * 45)
                w_box = draw.textbbox((0, 0), word, font=FONT_HERO)
                word_w = w_box[2] - w_box[0]

                # Specular shimmer across the word
                shimmer_pw = ((t_act + w_idx * 0.5) % 2.0) / 2.0
                draw_shimmer_text(overlay, word, (w - word_w) // 2, cur_y, FONT_HERO, (255, 255, 255), colors[w_idx], shimmer_pw)

            # Subtitle
            p_sub3 = min(1.0, max(0.0, (t_act - 1.8) / 0.8))
            e_sub3 = ease_out_expo(p_sub3)
            sub3 = "One unified neural foundation. Transforming raw computation into human understanding."
            sub3_w = draw.textbbox((0, 0), sub3, font=FONT_BODY)[2] - draw.textbbox((0, 0), sub3, font=FONT_BODY)[0]
            draw.text(((w - sub3_w) // 2, int(530 + (1.0 - e_sub3) * 20)), sub3, font=FONT_BODY, fill=(203, 213, 225, int(240 * e_sub3)))

        else:
            # ACT 4 (12.0s - 16.0s): THE GRAND REVEAL & CALL TO ACTION
            # "SYNTHESIS ONE — THE FUTURE IS NOW"
            t_act = t - 12.0
            p4 = min(1.0, t_act / 1.0)
            e4 = ease_out_expo(p4)

            # Center Vector Monogram Icon (Apple-style precision geometric diamond)
            icon_y = int(185 + (1.0 - e4) * -30)
            ix, iy = w // 2, icon_y
            ir = 38
            draw.polygon(
                [(ix, iy - ir), (ix + ir, iy), (ix, iy + ir), (ix - ir, iy)],
                fill=(255, 255, 255, 25),
                outline=(255, 255, 255, 220),
            )
            # Inner glowing core
            draw.ellipse([ix - 10, iy - 10, ix + 10, iy + 10], fill=(56, 189, 248, 240))

            # Master Brand Title
            title4 = "SYNTHESIS ONE"
            t4_box = draw.textbbox((0, 0), title4, font=FONT_HERO)
            t4_w = t4_box[2] - t4_box[0]
            t4_y = int(255 + (1.0 - e4) * 40)
            shimmer_p4 = (t_act % 2.0) / 2.0
            draw_shimmer_text(overlay, title4, (w - t4_w) // 2, t4_y, FONT_HERO, (255, 255, 255), (147, 197, 253), shimmer_p4)

            # Kinetic Tracking Expansion Subtitle
            # "T H E   F U T U R E   I S   N O W"
            track_p = min(1.0, max(0.0, (t_act - 0.4) / 2.5))
            cur_track = int(4 + 14 * track_p)
            tag_text = "THE FUTURE IS NOW"
            draw_letter_spaced(draw, tag_text, w // 2, t4_y + 85, FONT_HEAD, (196, 181, 253), cur_track)

            # Frosted Glass Call-To-Action Pill
            p_cta = min(1.0, max(0.0, (t_act - 1.2) / 0.8))
            e_cta = ease_out_expo(p_cta)
            cta_y = int(445 + (1.0 - e_cta) * 35)

            draw.rounded_rectangle([w // 2 - 220, cta_y, w // 2 + 220, cta_y + 54], radius=27, fill=(255, 255, 255, 240), outline=(255, 255, 255, 255), width=1)
            cta_text = "AVAILABLE WORLDWIDE // TODAY"
            cta_w = draw.textbbox((0, 0), cta_text, font=FONT_BODY_BOLD)[2] - draw.textbbox((0, 0), cta_text, font=FONT_BODY_BOLD)[0]
            draw.text(((w - cta_w) // 2, cta_y + 17), cta_text, font=FONT_BODY_BOLD, fill=(15, 23, 42))

            # Footer
            draw.text((w // 2 - 130, 560), "synthesis.ai/special-event", font=FONT_MONO, fill=(148, 163, 184, int(200 * e_cta)))

        canvas = Image.alpha_composite(canvas, overlay)
        return canvas.convert("RGB")
