"""Lettering: speech balloons, narrator box and SFX drawn onto a panel image (the art model cannot render text).

Placement without face detection: the art engine puts the first character on the left half and the second on the right
half (two-reference workflow), so a speaker's balloon sits over their half with its tail pointing down at them.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from engine.original.models import OriginalStory, Panel

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]
BALLOON_FONTS = ["comic.ttf", "segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf"]
BOLD_FONTS = ["comicbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"]
SFX_FONTS = ["impact.ttf", "comicbd.ttf", "DejaVuSans-Bold.ttf"]
MAX_CAPTION_WORDS = 22


@lru_cache(maxsize=64)
def font(names: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if cur and draw.textlength(trial, font=fnt) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    return lines + [cur] if cur else lines


def short_caption(text: str, limit: int = MAX_CAPTION_WORDS) -> str:
    """First sentence(s) of the narration up to `limit` words: a page cannot carry the whole 40-word storyteller text."""
    out: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sent.split()
        if out and len(out) + len(words) > limit:
            break
        out += words
        if len(out) >= limit // 2:
            break
    clipped = out[:limit]
    s = " ".join(clipped)
    return s + "…" if len(clipped) < len(text.split()) and not s.endswith((".", "!", "?")) else s


def _balloon(draw: ImageDraw.ImageDraw, text: str, cx: int, top: int, tail_to: tuple[int, int], size: int, max_w: int,
             bounds: tuple[int, int]) -> tuple[int, int, int, int]:
    fnt = font(tuple(BALLOON_FONTS), size)
    lines = wrap(draw, text, fnt, max_w)
    lh = int(size * 1.25)
    w = int(max(draw.textlength(ln, font=fnt) for ln in lines)) + 2 * int(size * 0.8)
    h = lh * len(lines) + int(size * 0.9)
    x0 = max(bounds[0] + 10, min(cx - w // 2, bounds[1] - w - 10))
    box = (x0, top, x0 + w, top + h)
    bx = min(max(tail_to[0], box[0] + h // 2), box[2] - h // 2)  # tail base stays on the balloon's flat bottom edge
    draw.polygon([(bx - size // 2, box[3] - 3), (bx + size // 2, box[3] - 3), tail_to], fill="white", outline="black")
    draw.rounded_rectangle(box, radius=min(h // 2, 40), fill="white", outline="black", width=max(3, size // 9))
    draw.polygon([(bx - size // 2 + 2, box[3] - size // 8), (bx + size // 2 - 2, box[3] - size // 8), tail_to], fill="white")
    y = top + int(size * 0.45)
    for ln in lines:
        draw.text((box[0] + int(size * 0.8), y), ln, font=fnt, fill="black")
        y += lh
    return box


def letter_panel(img: Image.Image, panel: Panel, story: OriginalStory, caption: bool = True, sfx: bool = True) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    """Returns the lettered copy and the balloon/caption boxes (for overlap tests and for the page composer to avoid)."""
    img = img.convert("RGB").copy()
    W, H = img.size
    d = ImageDraw.Draw(img)
    size = max(24, W // 28)
    order = [c for c in panel.character_ids]
    anchor = {c: int(W * (0.28 if i == 0 else 0.72)) if len(order) > 1 else W // 2 for i, c in enumerate(order)}
    boxes: list[tuple[int, int, int, int]] = []
    top_by_x: dict[int, int] = {}
    for ln in panel.dialogue:
        cx = anchor.get(ln.speaker_id, W // 2)
        top = top_by_x.get(cx, int(H * 0.05))
        box = _balloon(d, ln.text, cx, top, (cx, min(int(H * 0.62), top + int(H * 0.38))), size, int(W * 0.44) - 2 * int(size * 0.8), (0, W))
        boxes.append(box)
        top_by_x[cx] = box[3] + int(size * 0.9)
    if caption and panel.caption.strip():
        fnt = font(tuple(BALLOON_FONTS), int(size * 0.85))
        lines = wrap(d, short_caption(panel.caption), fnt, int(W * 0.9) - 40)
        lh = int(size * 0.85 * 1.25)
        h = lh * len(lines) + 24
        box = (int(W * 0.05), H - h - int(H * 0.04), int(W * 0.95), H - int(H * 0.04))
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).rectangle(box, fill=(255, 248, 225, 235), outline=(40, 30, 20, 255), width=3)
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        d = ImageDraw.Draw(img)
        y = box[1] + 12
        for line in lines:
            d.text((box[0] + 20, y), line, font=fnt, fill=(40, 30, 20))
            y += lh
        boxes.append(box)
    if sfx and panel.sfx:
        sf = font(tuple(SFX_FONTS), int(size * 2.2))
        txt = panel.sfx[0].upper()
        layer = Image.new("RGBA", (int(d.textlength(txt, font=sf)) + 40, int(size * 3.2)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((20, 10), txt, font=sf, fill=(255, 230, 60, 255), stroke_width=6, stroke_fill=(30, 0, 0, 255))
        layer = layer.rotate(10, expand=True, resample=Image.BICUBIC)
        img.paste(layer, (int(W * 0.58), int(H * 0.42)), layer)
    return img, boxes
