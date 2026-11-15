"""Click-bait-grade thumbnails for one reel: NEW art drawn for the thumbnail (not a video frame), colour graded, glow + vignette, big outlined title.

  python tools/reels/thumb_viral.py art r11      draws the pictures with ArtEngine (MiniMax-H3-Image by default, ~3 min each while RAM is tight)
  python tools/reels/thumb_viral.py compose r11  grade + title -> output/reels/<slug>/thumb/v_<name>.jpg and v_sheet.jpg

Recipe (from thumbs research): one giant emotional face or one clear clash, saturated high contrast, a single hot accent colour, 1-3 big words,
the subject and the title inside the centre 3:4 band. Pictures contain no text; PIL draws it. Edit VIRAL[slug] after looking at the art.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from specs import NEGATIVE  # noqa: E402

OUT = ROOT / "output" / "reels"
IMG_WF = os.environ.get("REEL_IMG_WORKFLOW", "minimax_h3_image_edit")
LOOK = ("funny hand-drawn cartoon doodle, simple stick-figure style with a giant round head, huge dot eyes and an extremely exaggerated facial expression, "
        "very thick black marker outlines, ultra saturated flat colors, strong color contrast, bold simple shapes, vertical 9:16 composition, "
        "dramatic glowing light behind the subject, no text, no letters, no numbers, no words")
GUY = "a stick-figure guy with messy black hair, big round dot eyes and blue striped pajamas"
MOS = "a mosquito with a round gray body, long thin legs, two see-through wings, a sharp needle nose and glowing red eyes"

# name -> (scene prompt, [(y, text, fill)], font px, grade (saturation, contrast, tint RGB, tint strength))
VIRAL = {"r11_mosquito_war": {
    "a_nose": (f"extreme close-up of {GUY} screaming in terror, his face filling the whole frame, bloodshot eyes with tiny pupils, mouth wide open, sweat drops flying; "
               f"a giant {MOS} hovering an inch from his nose with its needle pointing at him; background a hot red and orange radial burst, empty space at the top",
               [(190, "1 MOSQUITO", "#FFE500"), (400, "VS ME", "#FFFFFF")], 200, (1.35, 1.15, (255, 40, 20), 0.10)),
    "b_giant": (f"a tiny {GUY} wearing a red headband and holding a tennis-racket sword standing bravely on a pillow, facing a gigantic {MOS} that towers over him "
                "filling most of the frame with huge glowing red eyes, a full moon behind, electric blue night with red glow, epic movie poster angle, empty space at the top",
                [(150, "NOW IT'S", "#FFFFFF"), (360, "PERSONAL", "#FFE500")], 190, (1.35, 1.2, (0, 90, 255), 0.12)),
    "c_bites": (f"extreme close-up of the face of {GUY} looking exhausted and miserable with huge dark circles and half closed eyes, his whole face covered in many red bite dots, "
                f"one finger pointing at a bite on his cheek, five small {MOS} flying around his head like a halo, bright yellow background with a red glow, empty space at the top",
                [(190, "COUNT YOUR", "#FFFFFF"), (400, "BITES", "#FF2A2A")], 200, (1.3, 1.15, (255, 200, 0), 0.08)),
}}


def stage_art(slug):
    from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
    from engine.comfyui.art import ArtEngine
    client = ComfyUIClient()
    engine = ArtEngine(client, ComfyWorkflowRegistry(client))
    for k, (name, spec) in enumerate(VIRAL[slug].items()):
        out = OUT / slug / "thumb" / f"vart_{name}.png"
        if out.exists() and out.stat().st_size:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        art = engine.generate(prompt=f"{LOOK}. Scene: {spec[0]}.", negative_prompt=NEGATIVE, width=768, height=1344,
                              seed=9100 + k, prefix=f"reels/{slug}_vthumb_{name}", workflow_id=IMG_WF)
        out.write_bytes(art.png)
        print(f"art {name} done", flush=True)


def vignette(w, h, strength):
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / 1.41
    return (1 - strength * np.clip(r, 0, 1) ** 2.0)[..., None]


def compose(slug, name, spec):
    scene, lines, px, (sat, con, tint, ts) = spec
    w, h = 1080, 1920
    im = Image.open(OUT / slug / "thumb" / f"vart_{name}.png").convert("RGB").resize((w, h), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=90, threshold=2))
    im = ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(sat)).enhance(con)
    a = np.asarray(im).astype(np.float32)
    a = a * (1 - ts) + np.array(tint, np.float32) * ts * (a.mean(2, keepdims=True) / 255) * 1.6  # tint follows brightness so blacks stay black
    glow = np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(28))).astype(np.float32)
    a = np.clip(a + 0.25 * np.clip(glow - 140, 0, 255), 0, 255) * vignette(w, h, 0.55)  # bloom on highlights, darker corners
    top = np.linspace(0.55, 0, 620)[:, None, None]  # dark fade behind the title so it reads on any picture
    a[:620] *= 1 - top * 0.8
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", px)
    for y, t, c in lines:
        x = (w - d.textlength(t, font=font)) / 2
        d.text((x + 8, y + 10), t, font=font, fill="black", stroke_width=22, stroke_fill="black")  # drop shadow
        d.text((x, y), t, font=font, fill=c, stroke_width=18, stroke_fill="black")
    p = OUT / slug / "thumb" / f"v_{name}.jpg"
    im.save(p, quality=93)
    return p


if __name__ == "__main__":
    stage, slug = sys.argv[1], next(s for s in VIRAL if s.startswith(sys.argv[2]))
    if stage == "art":
        stage_art(slug)
    else:
        paths = [compose(slug, n, s) for n, s in VIRAL[slug].items() if (OUT / slug / "thumb" / f"vart_{n}.png").exists()]
        sheet = Image.new("RGB", (360 * len(paths), 640))
        for i, p in enumerate(paths):
            sheet.paste(Image.open(p).resize((360, 640)), (i * 360, 0))
        sheet.save(OUT / slug / "thumb" / "v_sheet.jpg")
        print(*paths, sep="\n")
