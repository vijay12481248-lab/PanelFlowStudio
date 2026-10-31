"""Render a chapter as ruler-annotated strip chunks for labelling panel ground truth.

Strip coordinates: pages stacked top to bottom at normalized width; y is the strip offset.
Usage: python scripts/panel_truth/render_strip_chunks.py <project_id> <out_dir> [chunk_px] [scale]
"""
import os
import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw

DB = Path(os.environ.get("PANELFLOW_APP_DATA", Path.home() / "AppData/Local/PanelFlow Studio")) / "database/panelflow.db"


def strip_pages(project_id: str) -> list[tuple[int, Path, int]]:
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    ws = Path(db.execute("select workspace_path from projects where id=?", (project_id,)).fetchone()[0])
    rows = db.execute("select sequence, filename from pages where project_id=? order by sequence", (project_id,))
    out, y = [], 0
    for seq, filename in rows:
        path = ws / "normalized" / f"page_{seq:04d}.jpg"
        if not path.exists():
            path = ws / "source" / filename
        with Image.open(path) as im:
            h = im.height
        out.append((y, path, h))
        y += h
    return out


def render(project_id: str, out_dir: Path, chunk: int = 5000, scale: float = 0.16) -> None:
    pages = strip_pages(project_id)
    total = pages[-1][0] + pages[-1][2]
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, top in enumerate(range(0, total, chunk)):
        bottom = min(total, top + chunk)
        canvas = Image.new("RGB", (round(1920 * scale) + 70, round((bottom - top) * scale)), "black")
        for y0, path, h in pages:
            if y0 + h <= top or y0 >= bottom:
                continue
            with Image.open(path) as im:
                part = im.convert("RGB").crop((0, max(0, top - y0), im.width, min(h, bottom - y0)))
                part = part.resize((round(part.width * scale), max(1, round(part.height * scale))))
                canvas.paste(part, (70, round((max(y0, top) - top) * scale)))
        draw = ImageDraw.Draw(canvas)
        for y in range(top - top % 250, bottom, 250):
            if y < top:
                continue
            sy = round((y - top) * scale)
            draw.line([(0, sy), (68 if y % 1000 else 70 + round(1920 * scale), sy)],
                      fill=(0, 255, 255) if y % 1000 == 0 else (90, 90, 90))
            draw.text((2, sy + 1), str(y), fill=(0, 255, 255) if y % 1000 == 0 else (200, 200, 200))
        for y0, _, _ in pages:
            if top <= y0 < bottom:
                sy = round((y0 - top) * scale)
                draw.line([(70, sy), (canvas.width, sy)], fill=(255, 0, 0), width=2)
        for x in range(0, 1921, 480):
            sx = 70 + round(x * scale)
            draw.line([(sx, 0), (sx, 6)], fill=(255, 255, 0))
        canvas.save(out_dir / f"chunk_{i:03d}_{top}-{bottom}.png")
    print(f"total strip height {total}px, {len(pages)} pages, page starts: {[p[0] for p in pages]}")


if __name__ == "__main__":
    args = sys.argv[1:]
    render(args[0], Path(args[1]), int(args[2]) if len(args) > 2 else 5000, float(args[3]) if len(args) > 3 else 0.16)
