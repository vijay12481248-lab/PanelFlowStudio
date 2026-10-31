"""Draw ground-truth (green/orange) and optional predicted (magenta) boxes onto strip chunks.

Usage: python scripts/panel_truth/overlay.py <truth.json> <out_dir> [predictions.json] [chunk_px] [scale]
predictions.json: {"panels": [{"box": [x, y, w, h]}, ...]} in strip coordinates.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from render_strip_chunks import strip_pages  # noqa: E402

KIND_COLOURS = {"story": (0, 230, 0), "cover": (255, 140, 0), "outro": (255, 140, 0),
                "banner": (255, 140, 0), "credits": (255, 140, 0)}


def main(truth_path: str, out_dir: str, pred_path: str | None = None, chunk: int = 5000, scale: float = 0.16):
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    preds = json.loads(Path(pred_path).read_text(encoding="utf-8"))["panels"] if pred_path else []
    pages = strip_pages(truth["project_id"])
    total = pages[-1][0] + pages[-1][2]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for i, top in enumerate(range(0, total, chunk)):
        bottom = min(total, top + chunk)
        canvas = Image.new("RGB", (round(1920 * scale), round((bottom - top) * scale)), "black")
        for y0, path, h in pages:
            if y0 + h <= top or y0 >= bottom:
                continue
            with Image.open(path) as im:
                part = im.convert("RGB").crop((0, max(0, top - y0), im.width, min(h, bottom - y0)))
                part = part.resize((round(part.width * scale), max(1, round(part.height * scale))))
                canvas.paste(part, (0, round((max(y0, top) - top) * scale)))
        draw = ImageDraw.Draw(canvas)

        def rect(box, colour, width):
            x, y, w, h = box
            if y + h < top or y > bottom:
                return
            draw.rectangle([x * scale, (y - top) * scale, (x + w) * scale, (y + h - top) * scale],
                           outline=colour, width=width)

        for n, p in enumerate(truth["panels"]):
            rect(p["box"], KIND_COLOURS.get(p["kind"], (0, 230, 0)), 3)
            x, y, _, _ = p["box"]
            if top <= y < bottom:
                draw.text((x * scale + 4, (y - top) * scale + 2), f"T{n}", fill=(0, 255, 0))
        for w in truth.get("watermarks", []):
            rect(w["box"], (0, 160, 255), 2)
        for n, p in enumerate(preds):
            rect(p["box"], (255, 0, 255), 2)
        canvas.save(out / f"overlay_{i:03d}_{top}-{bottom}.png")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2] if len(a) > 2 and a[2] != "-" else None,
         int(a[3]) if len(a) > 3 else 5000, float(a[4]) if len(a) > 4 else 0.16)
