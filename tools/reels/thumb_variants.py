"""Three thumbnail variants for one reel from its existing panels (no GPU): python tools/reels/thumb_variants.py r11_mosquito_war
Each variant = (panel number, [(y, text, fill)], saturation boost). Look at the output and pick; edit VARIANTS[slug] to retune."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

OUT = Path(__file__).resolve().parents[2] / "output" / "reels"
Y, W = "#FFE500", "#FFFFFF"
VARIANTS = {"r11_mosquito_war": {
    "a_shock": (2, [(230, "1 MOSQUITO", Y), (430, "VS ME", W)], 1.25),
    "b_friends": (14, [(1190, "IT BROUGHT", W), (1390, "FRIENDS", Y)], 1.25),
    "c_war": (6, [(50, "NOW IT'S", W), (240, "PERSONAL", Y)], 1.3),
}}


def make(slug, name, panel, lines, sat):
    im = Image.open(OUT / slug / "panels" / f"s{panel}.png").convert("RGB")
    w, h = 1080, 1920
    s = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    x0, y0 = (im.width - w) // 2, (im.height - h) // 2
    im = ImageEnhance.Contrast(ImageEnhance.Color(im.crop((x0, y0, x0 + w, y0 + h))).enhance(sat)).enhance(1.08)
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 190)
    for y, t, c in lines:
        d.text(((w - d.textlength(t, font=font)) / 2, y), t, font=font, fill=c, stroke_width=16, stroke_fill="black")
    p = OUT / slug / "thumb" / f"{name}.jpg"
    p.parent.mkdir(exist_ok=True)
    im.save(p, quality=92)
    return p


if __name__ == "__main__":
    slug = sys.argv[1]
    paths = [make(slug, n, *v) for n, v in VARIANTS[slug].items()]
    sheet = Image.new("RGB", (3 * 360, 640))
    for i, p in enumerate(paths):
        sheet.paste(Image.open(p).resize((360, 640)), (i * 360, 0))
    sheet.save(OUT / slug / "thumb" / "sheet.jpg")
    print(*paths, sep="\n")
