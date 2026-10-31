"""Cut labelled real strip windows (1920x3840 -> 512x1024) from a ground-truth chapter for training.

Panels and promo boxes come from the truth file; bubbles from detector candidates (pseudo labels).
Usage: python scripts/panel_truth/real_tiles.py <truth.json> <bubble_raw.json> <out_dir> <count> [seed]
"""
import json
import random
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from render_strip_chunks import strip_pages  # noqa: E402
from synth import CLASSES, TH, TW  # noqa: E402

WIN_W, WIN_H = 1920, 3840


def window(pages, top):
    canvas = Image.new("RGB", (WIN_W, WIN_H), "white")
    for y0, path, h in pages:
        if y0 + h <= top or y0 >= top + WIN_H:
            continue
        with Image.open(path) as im:
            part = im.convert("RGB").crop((0, max(0, top - y0), im.width, min(h, top + WIN_H - y0)))
        canvas.paste(part, (0, max(0, y0 - top)))
    return canvas.resize((TW, TH), Image.BILINEAR)


def clip(box, top, cls):
    x, y, w, h = box
    s = TW / WIN_W
    y0, y1 = max(y, top), min(y + h, top + WIN_H)
    if y1 - y0 < 25 or (cls == "panel" and y1 - y0 < 0.3 * h and y1 - y0 < 0.12 * WIN_H):
        return None
    return [round(x * s, 1), round((y0 - top) * s, 1), round((x + w) * s, 1), round((y1 - top) * s, 1)]


def main(truth_path, bubble_path, out_dir, count, seed=0):
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    bubbles = [c["box"] for c in json.loads(Path(bubble_path).read_text(encoding="utf-8"))["panels"]
               if c["score"] >= 0.5 and c["box"][2] <= 1440 and c["box"][3] <= 1150]
    pages = strip_pages(truth["project_id"])
    rng = random.Random(seed)
    out = Path(out_dir)
    (out / "images").mkdir(parents=True, exist_ok=True)
    index = []
    slug = Path(truth_path).stem
    for i in range(count):
        top = rng.randint(0, truth["strip_height"] - WIN_H)
        labels = []
        for p in truth["panels"]:
            if (b := clip(p["box"], top, "panel")):
                labels.append({"class": "panel", "box": b})
        for w in truth["watermarks"]:
            if (b := clip(w["box"], top, "promo")):
                labels.append({"class": "promo", "box": b})
        for bb in bubbles:
            if (b := clip(bb, top, "bubble")):
                labels.append({"class": "bubble", "box": b})
        name = f"real_{slug}_{i:04d}.jpg"
        window(pages, top).save(out / "images" / name, quality=92)
        index.append({"file": name, "labels": labels})
    (out / "labels.json").write_text(json.dumps({"classes": CLASSES, "tiles": index}), encoding="utf-8")
    print(f"{count} real tiles -> {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], int(a[3]), int(a[4]) if len(a) > 4 else 0)
