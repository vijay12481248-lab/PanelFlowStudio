"""Synthetic comic-lettering text lines with exact labels, for training a line reader.

Text comes from our own project prose and a standard English vocabulary, never from manga dialogue.
Each index gives the same sample every time (seeded), so runs are reproducible and nothing is stored on disk.
"""
from __future__ import annotations

import io
import json
import random
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[2]
FONTS = Path("C:/Windows/Fonts")
# (file, extra stroke weight options): bold / italic / casual / script faces similar to comic lettering
FACES = ["comic.ttf", "comicbd.ttf", "comici.ttf", "comicz.ttf", "Inkfree.ttf", "segoepr.ttf", "segoeprb.ttf",
         "mvboli.ttf", "framd.ttf", "framdit.ttf", "impact.ttf", "ariblk.ttf", "arialbd.ttf", "arialbi.ttf",
         "trebucbd.ttf", "trebucbi.ttf", "verdanab.ttf", "verdanaz.ttf", "tahomabd.ttf", "seguibl.ttf",
         "seguibli.ttf", "bahnschrift.ttf", "GOTHICB.TTF", "GOTHICBI.TTF", "calibrib.ttf", "calibriz.ttf",
         "segoeuib.ttf", "segoeuiz.ttf", "candarab.ttf", "corbelb.ttf", "constanb.ttf", "ARIALNB.TTF"]
INTERJECTIONS = ["HAHAHA...", "WAIT!", "WHAT?!", "...", "HUH?", "SIGH...", "HEHEHE...", "DAMN!", "NO WAY!", "HMPH!",
                 "WHAT IS THIS?!", "I SEE...", "HOW CAN THIS BE?", "IMPOSSIBLE!", "GO ON,", "FINE,", "THEN,", "SO..."]
PUNCT = [",", ".", "!", "?", "...", "!", "?!", ""]


def load_corpus() -> dict:
    sentences: list[str] = []
    for pattern in ("docs/**/*.md", "engine/narration/prompts/**/*.md", "README.md"):
        for p in REPO.glob(pattern):
            for s in re.split(r"(?<=[.!?])\s+|\n+", p.read_text(encoding="utf-8", errors="ignore")):
                s = re.sub(r"[^A-Za-z0-9 ,.!?'\-]", " ", s)
                s = " ".join(s.split())
                if (3 <= len(s.split()) <= 40 and not re.search(r"vijay|sekhar|sekar|gmail", s, re.I)  # no personal data
                        and not re.search(r"\w\.\w|\w{15,}", s)):  # no filenames or code identifiers
                    sentences.append(s)
    for p in (REPO / "engine/narration/fewshot").glob("*.jsonl"):
        for row in p.read_text(encoding="utf-8").splitlines():
            if row.strip():
                sentences.append(json.loads(row)["line"])
    words: list[str] = []
    try:
        from huggingface_hub import hf_hub_download
        vocab = Path(hf_hub_download("bert-base-uncased", "vocab.txt")).read_text(encoding="utf-8").splitlines()
        words = [w for w in vocab if w.isalpha() and 2 <= len(w) <= 12 and w.isascii()]
    except Exception:
        words = sorted({w for s in sentences for w in re.findall(r"[A-Za-z]{2,12}", s)})
    names: list[str] = []
    for bible in (REPO / "docs/bibles").glob("*.json"):
        for c in json.loads(bible.read_text(encoding="utf-8")).get("characters", []):
            names += [c["name"], *c.get("aliases", [])]
    names = [n for n in names if n and "CONFIRM" not in n]
    return {"sentences": sentences, "words": words, "names": names or ["Kai", "Mira"]}


class LineSynth:
    def __init__(self, corpus: dict | None = None, seed: int = 0):
        self.corpus = corpus or load_corpus()
        self.seed = seed
        self.faces = [str(FONTS / f) for f in FACES if (FONTS / f).is_file()]
        if not self.faces:
            raise RuntimeError("no comic-style fonts found in C:/Windows/Fonts")

    def text(self, rng: random.Random) -> str:
        c, r = self.corpus, rng.random()
        if r < 0.50 and c["sentences"]:
            words = rng.choice(c["sentences"]).split()
            n = rng.randint(1, 6)
            start = rng.randint(0, max(0, len(words) - n))
            t = " ".join(words[start:start + n])
        elif r < 0.78:
            t = " ".join(rng.choice(c["words"]) for _ in range(rng.randint(1, 5)))
        elif r < 0.88:
            t = rng.choice(c["names"]) + rng.choice([" ", "'S ", ", "]) + " ".join(rng.choice(c["words"]) for _ in range(rng.randint(0, 3)))
        elif r < 0.94:
            t = f"{rng.randint(1, 99)}{rng.choice(['TH', 'ST', 'ND', 'RD', ''])} " + " ".join(rng.choice(c["words"]) for _ in range(rng.randint(1, 3)))
        else:
            return rng.choice(INTERJECTIONS)
        t = t.strip(" ,.-")
        t = (t.upper() if rng.random() < 0.88 else t) + rng.choice(PUNCT)
        return t.strip() or "OK"

    def render(self, idx: int) -> tuple[Image.Image, str]:
        rng = random.Random(self.seed * 1_000_003 + idx)
        text = self.text(rng)
        font = ImageFont.truetype(rng.choice(self.faces), rng.randint(28, 76))
        gap = rng.choice([0, 0, 0, 1, 2, 4, 6])
        stroke = rng.choice([0, 0, 0, 1, 1, 2])
        dark = rng.random() < 0.88
        bg = (255, 255, 255) if dark and rng.random() < 0.8 else tuple(rng.randint(200, 255) for _ in range(3)) if dark \
            else tuple(rng.randint(0, 50) for _ in range(3))
        fg = (rng.randint(0, 40),) * 3 if dark else (255, 255, 255) if rng.random() < 0.8 else (rng.randint(180, 255), 30, 30)
        pad = rng.randint(6, 18)
        if gap:
            width = sum(font.getlength(ch) + gap for ch in text)
        else:
            width = font.getlength(text)
        asc, desc = font.getmetrics()
        img = Image.new("RGB", (int(width) + 2 * pad + 4 * stroke, asc + desc + 2 * pad), bg)
        draw = ImageDraw.Draw(img)
        if gap:
            x = pad + 2 * stroke
            for ch in text:
                draw.text((x, pad), ch, font=font, fill=fg, stroke_width=stroke, stroke_fill=fg)
                x += font.getlength(ch) + gap
        else:
            draw.text((pad + 2 * stroke, pad), text, font=font, fill=fg, stroke_width=stroke, stroke_fill=fg)
        shear = rng.choice([0, 0, rng.uniform(-0.06, 0.06), rng.uniform(0.12, 0.38)])
        if shear:
            img = img.transform(img.size, Image.AFFINE, (1, shear, -shear * img.height / 2, 0, 1, 0),
                                resample=Image.BICUBIC, fillcolor=bg)
        if rng.random() < 0.5:
            img = img.rotate(rng.uniform(-4, 4), resample=Image.BICUBIC, expand=True, fillcolor=bg)
        scale = rng.uniform(0.35, 1.2)  # real crops are small and soft
        img = img.resize((max(8, int(img.width * scale)), max(8, int(img.height * scale))), Image.LANCZOS)
        if rng.random() < 0.6:
            img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.2, 1.2)))
        if rng.random() < 0.5:
            arr = np.asarray(img, dtype=np.float32) + np.random.RandomState(idx % (2**31)).normal(0, rng.uniform(1, 8), (img.height, img.width, 3))
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        if rng.random() < 0.7:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=rng.randint(35, 92))
            img = Image.open(buf).convert("RGB")
        return img, text


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    synth = LineSynth(seed=1)
    print(f"corpus: {len(synth.corpus['sentences'])} sentences, {len(synth.corpus['words'])} words, {len(synth.faces)} fonts")
    rows = [synth.render(i) for i in range(12)]
    sheet = Image.new("RGB", (900, sum(min(160, im.height * 2) + 8 for im, _ in rows)), (200, 200, 200))
    y = 0
    for im, t in rows:
        s = min(2.0, 880 / im.width)
        im = im.resize((int(im.width * s), int(im.height * s)))
        sheet.paste(im, (6, y))
        y += im.height + 8
    sheet.save(out / "preview.png")
    print([t for _, t in rows])
