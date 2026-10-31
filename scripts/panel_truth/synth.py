"""Synthetic webtoon strip tiles with exact panel / bubble / promo labels, for detector training.

Each tile is a 1920x3840 strip window rendered at 512x1024. Art is sampled from real chapter pages;
layout, gutters, borders, balloons and scanlator stamps are generated so every box is known.
Usage: python scripts/panel_truth/synth.py <out_dir> <count> <project_id> [<project_id> ...]
"""
import json
import random
import sqlite3
import string
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TW, TH = 512, 1024
S = TW / 1920  # strip units -> tile pixels
CLASSES = ["panel", "bubble", "promo"]
FONTS = Path("C:/Windows/Fonts")
LATIN = ["arialbd.ttf", "impact.ttf", "bahnschrift.ttf", "comicbd.ttf", "ariblk.ttf", "tahomabd.ttf"]
BUBBLE_FONTS = ["comic.ttf", "comicbd.ttf", "arial.ttf", "tahomabd.ttf"]
CJK = ["msyhbd.ttc", "msyh.ttc"]
SITES = ["MANHUAPLUS", "MANGACULTIVATOR", "ASURASCANS", "REAPERSCANS", "FLAMECOMICS", "MANHWATOP", "TOONILY",
         "MANGABUDDY", "LUMINOUSSCANS", "KUNMANGA", "WEBTOONXYZ", "NIGHTSCANS"]
WORDS = "THE MASTER SWORD MAP MANOR CLAN TRAP WHY WHAT YOU ME HE IS NOT THAT KNOW WILL FAKE GO NOW WAIT".split()
DB = Path.home() / "AppData/Local/PanelFlow Studio/database/panelflow.db"


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), max(6, int(size)))


class ArtPool:
    def __init__(self, project_ids, max_pages=160, seed=0):
        db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
        paths = []
        for pid in project_ids:
            ws = Path(db.execute("select workspace_path from projects where id=?", (pid,)).fetchone()[0])
            paths += sorted((ws / "normalized").glob("page_*.jpg"))
        random.Random(seed).shuffle(paths)
        self.pages = []
        for p in paths[:max_pages]:
            with Image.open(p) as im:
                if im.height < 300:
                    continue
                im = im.convert("RGB")
                self.pages.append(im.resize((TW, max(1, round(im.height * S))), Image.BILINEAR))

    def patch(self, w, h, rng):
        crop = rng.choice(self.pages)
        for _ in range(12):
            page = rng.choice(self.pages)
            scale = rng.uniform(0.7, 1.4)
            cw, ch = min(page.width, max(8, round(w * scale))), min(page.height, max(8, round(h * scale)))
            x = rng.randint(0, page.width - cw)
            y = rng.randint(0, page.height - ch)
            crop = page.crop((x, y, x + cw, y + ch))
            arr = np.asarray(crop.convert("L"), dtype=np.float32)
            if arr.std() > 28 and (arr > 235).mean() < 0.5:
                return crop.resize((w, h), Image.BILINEAR)
        return crop.resize((w, h), Image.BILINEAR)


def background(rng):
    kind = rng.random()
    if kind < 0.55:
        return Image.new("RGB", (TW, TH), (255, 255, 255)), "light"
    if kind < 0.7:
        return Image.new("RGB", (TW, TH), (rng.randint(0, 25),) * 3), "dark"
    a = np.array([rng.randint(0, 255) for _ in range(3)], np.float32)
    b = np.array([rng.randint(150, 255) for _ in range(3)], np.float32)
    t = np.linspace(0, 1, TH, dtype=np.float32)[:, None, None]
    grad = (a * (1 - t) + b * t).repeat(TW, axis=1).astype(np.uint8)
    return Image.fromarray(grad), "gradient"


def add_box(labels, cls, box):
    x0, y0, x1, y1 = [float(v) for v in box]
    full_h = y1 - y0
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(TW, x1), min(TH, y1)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return
    if cls == "panel" and (y1 - y0) < 0.3 * full_h and (y1 - y0) < 0.12 * TH:
        return  # barely visible slice of a panel cut by the window edge
    labels.append({"class": cls, "box": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]})


def draw_panel(tile, art, rng, x0, y0, w, h, labels, borderless=False):
    patch = art.patch(w, h, rng)
    mask = Image.new("L", (w, h), 255)
    poly = [(0, 0), (w, 0), (w, h), (0, h)]
    if borderless:
        fade = np.ones((h, w), np.float32)
        top, bottom = rng.randint(10, max(11, h // 4)), rng.randint(10, max(11, h // 4))
        fade[:top] *= np.linspace(0, 1, top)[:, None]
        fade[h - bottom:] *= np.linspace(1, 0, bottom)[:, None]
        mask = Image.fromarray((fade * 255).astype(np.uint8))
    elif rng.random() < 0.15:  # slanted top or bottom edge
        cut = rng.randint(h // 10, max(h // 10 + 1, h // 3))
        idx = rng.choice([0, 1, 2, 3])
        px, py = poly[idx]
        poly[idx] = (px, cut if py == 0 else h - cut)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).polygon(poly, fill=255)
    tile.paste(patch, (x0, y0), mask)
    if not borderless and rng.random() < 0.8:
        stroke = rng.choice([(0, 0, 0), (0, 0, 0), (30, 30, 30), (255, 255, 255)])
        outline = [(x0 + min(px, w - 1), y0 + min(py, h - 1)) for px, py in poly]
        ImageDraw.Draw(tile).line(outline + outline[:1], fill=stroke, width=rng.randint(1, 3))
    add_box(labels, "panel", (x0, y0, x0 + w, y0 + h))


def text_block(draw, cx, cy, maxw, rng, fill=(0, 0, 0)):
    f = font(rng.choice(BUBBLE_FONTS), rng.uniform(6, 10))
    lines = [" ".join(rng.choice(WORDS) for _ in range(rng.randint(2, 4))) for _ in range(rng.randint(1, 4))]
    lh = f.size + 2
    y = cy - lh * len(lines) / 2
    for line in lines:
        tw = draw.textlength(line, font=f)
        if tw > maxw:
            continue
        draw.text((cx - tw / 2, y), line, font=f, fill=fill)
        y += lh


def draw_bubble(tile, rng, cx, cy, labels):
    w, h = rng.randint(70, 200), rng.randint(40, 110)
    layer = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    style = rng.random()
    box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    if style < 0.55:
        d.ellipse(box, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=rng.randint(1, 2))
        tail = [(cx - 8, cy + h / 2 - 4), (cx + 8, cy + h / 2 - 4), (cx + rng.randint(-25, 25), cy + h / 2 + 18)]
        d.polygon(tail, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
        text_block(d, cx, cy, w * 0.75, rng)
    elif style < 0.8:
        pts = []
        n = rng.randint(18, 40)
        for i in range(n):
            ang = 2 * np.pi * i / n
            r = 1.0 if i % 2 == 0 else rng.uniform(0.8, 0.92)
            pts.append((cx + np.cos(ang) * w / 2 * r, cy + np.sin(ang) * h / 2 * r))
        d.polygon(pts, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
        text_block(d, cx, cy, w * 0.7, rng)
    else:  # dark smoke balloon with red text
        d.ellipse(box, fill=(5, 5, 5, 255))
        edge = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        ImageDraw.Draw(edge).ellipse((box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6), fill=(170, 20, 20, 200))
        layer = Image.alpha_composite(edge.filter(ImageFilter.GaussianBlur(4)), layer)
        text_block(ImageDraw.Draw(layer), cx, cy, w * 0.7, rng, fill=(230, 30, 30))
    tile.paste(layer, (0, 0), layer)
    add_box(labels, "bubble", (box[0], box[1], box[2], box[3] + (18 if style < 0.55 else 0)))


def draw_promo(tile, rng, labels, x=None, y=None, region=None):
    d = ImageDraw.Draw(tile)
    site = rng.choice(SITES) if rng.random() < 0.7 else "".join(rng.choice(string.ascii_uppercase)
                                                               for _ in range(rng.randint(6, 12)))
    kind = rng.random()
    if kind < 0.55:  # READ FIRST AT / SITE.COM stamp
        f1, f2 = font(rng.choice(LATIN), rng.uniform(9, 14)), font(rng.choice(LATIN), rng.uniform(11, 17))
        l1, l2 = "READ FIRST AT", f"{site}.COM"
        w = max(d.textlength(l1, font=f1), d.textlength(l2, font=f2))
        h = f1.size + f2.size + 4
        x = rng.uniform(0, TW - w) if x is None else min(max(0, x), TW - w)
        y = rng.uniform(0, TH - h) if y is None else min(max(0, y), TH - h)
        d.text((x + (w - d.textlength(l1, font=f1)) / 2, y), l1, font=f1, fill=(255, 255, 255),
               stroke_width=1, stroke_fill=(0, 0, 0))
        split = rng.randint(3, max(4, len(site) - 2))
        d.text((x, y + f1.size + 3), l2[:split], font=f2, fill=(230, 40, 30))
        d.text((x + d.textlength(l2[:split], font=f2), y + f1.size + 3), l2[split:], font=f2, fill=(20, 20, 20))
        add_box(labels, "promo", (x - 2, y - 2, x + w + 2, y + h + 2))
    elif kind < 0.8:  # three-line banner
        f = font(rng.choice(LATIN), rng.uniform(10, 15))
        lines = ["IF YOU ENJOYED THIS SERIES AND WANT A", "FASTER RELEASE PLEASE READ ON", f"{site}.COM"]
        w = max(d.textlength(t, font=f) for t in lines)
        if w > TW - 4:
            return
        h = 3 * (f.size + 3)
        x = rng.uniform(0, TW - w) if x is None else min(max(0, x), TW - w)
        y = rng.uniform(0, TH - h) if y is None else min(max(0, y), TH - h)
        if rng.random() < 0.5:
            d.rectangle([x - 4, y - 3, x + w + 4, y + h + 3], fill=(255, 255, 255))
        for i, t in enumerate(lines):
            d.text((x + (w - d.textlength(t, font=f)) / 2, y + i * (f.size + 3)), t, font=f,
                   fill=(230, 40, 30) if i == 2 else (0, 0, 0))
        add_box(labels, "promo", (x - 4, y - 3, x + w + 4, y + h + 3))
    else:  # translucent publisher mark (e.g. 快看漫画)
        f = font(rng.choice(CJK), rng.uniform(9, 14))
        t = rng.choice(["快看漫画", "哔哩哔哩漫画", "腾讯动漫", "有妖气"])
        w, h = d.textlength(t, font=f) + f.size + 6, f.size + 6
        x = rng.uniform(0, TW - w) if x is None else min(max(0, x), TW - w)
        y = rng.uniform(0, TH - h) if y is None else min(max(0, y), TH - h)
        layer = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        alpha = rng.randint(90, 170)
        ld.rounded_rectangle([x, y + 1, x + f.size, y + h - 1], radius=3, outline=(240, 240, 240, alpha), width=1)
        ld.text((x + f.size + 4, y + 2), t, font=f, fill=(240, 240, 240, alpha))
        tile.paste(layer, (0, 0), layer)
        add_box(labels, "promo", (x - 1, y, x + w + 1, y + h))


def draw_sfx(tile, rng):
    f = font(rng.choice(["impact.ttf", "ariblk.ttf", "msyhbd.ttc"]), rng.uniform(25, 60))
    t = rng.choice(["BOOM", "HAHAHA", "WHOOSH", "咳", "嗖", "!!", "THUD"])
    layer = Image.new("RGBA", (TW, TW), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((20, 20), t, font=f, fill=tuple(rng.randint(0, 255) for _ in range(3)) + (255,),
                               stroke_width=2, stroke_fill=(255, 255, 255, 255))
    layer = layer.rotate(rng.uniform(-30, 30), expand=False)
    tile.paste(layer, (rng.randint(-100, TW - 150), rng.randint(0, TH - 100)), layer)


def make_tile(art, rng):
    tile, _ = background(rng)
    labels = []
    y = rng.randint(-600, 40)
    panels = []
    while y < TH:
        kind = rng.random()
        if kind < 0.35:  # (near) full width
            x0 = rng.choice([0, 0, rng.randint(0, 50)])
            w = TW - x0 - rng.choice([0, 0, rng.randint(0, 50)])
            h = rng.randint(130, 800)
            draw_panel(tile, art, rng, x0, y, w, h, labels)
            panels.append((x0, y, w, h))
        elif kind < 0.6:  # offset single panel
            w = rng.randint(220, 460)
            x0 = rng.randint(0, TW - w)
            h = rng.randint(140, 650)
            draw_panel(tile, art, rng, x0, y, w, h, labels)
            panels.append((x0, y, w, h))
        elif kind < 0.78:  # staggered pair
            w1, w2 = rng.randint(140, 260), rng.randint(160, 300)
            h1, h2 = rng.randint(200, 500), rng.randint(200, 500)
            left_first = rng.random() < 0.5
            xa = rng.randint(0, 30)
            xb = TW - w2 - rng.randint(0, 30)
            ya, yb = (y, y + rng.randint(40, h1 - 40)) if left_first else (y + rng.randint(40, h2 - 40), y)
            draw_panel(tile, art, rng, xa, ya, w1, h1, labels)
            draw_panel(tile, art, rng, xb, yb, w2, h2, labels)
            panels += [(xa, ya, w1, h1), (xb, yb, w2, h2)]
            h = max(ya + h1, yb + h2) - y
        else:  # borderless full-width scene fading into the gutter
            h = rng.randint(300, 900)
            draw_panel(tile, art, rng, 0, y, TW, h, labels, borderless=True)
            panels.append((0, y, TW, h))
        gap = rng.randint(30, 260)
        if gap > 70 and rng.random() < 0.7:  # balloon in the gutter, often crossing a frame
            draw_bubble(tile, rng, rng.randint(90, TW - 90), y + h + gap // 2 + rng.randint(-40, 20), labels)
        y += h + gap
    for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
        px, py, pw, ph = rng.choice(panels)
        draw_bubble(tile, rng, rng.randint(px + 40, max(px + 41, px + pw - 40)),
                    rng.randint(py, py + max(1, ph)), labels)
    if rng.random() < 0.6:
        px, py, pw, ph = rng.choice(panels)
        corner = rng.random() < 0.5
        draw_promo(tile, rng, labels, x=(px + 2 if corner else px + pw - 150), y=py + ph - 30)
    if rng.random() < 0.35:
        draw_promo(tile, rng, labels)
    if rng.random() < 0.4:
        draw_sfx(tile, rng)
    return tile, labels


def main(out_dir, count, project_ids, seed=1):
    out = Path(out_dir)
    (out / "images").mkdir(parents=True, exist_ok=True)
    art = ArtPool(project_ids, seed=seed)
    rng = random.Random(seed)
    index = []
    for i in range(count):
        tile, labels = make_tile(art, rng)
        name = f"synth_{i:05d}.jpg"
        tile.save(out / "images" / name, quality=rng.randint(75, 95))
        index.append({"file": name, "labels": labels})
    (out / "labels.json").write_text(json.dumps({"classes": CLASSES, "tiles": index}), encoding="utf-8")
    print(f"{count} tiles from {len(art.pages)} art pages -> {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], int(a[1]), a[2:])
