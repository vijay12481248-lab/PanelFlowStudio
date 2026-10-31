"""Summarise a project's cleanup report and save a contact sheet of every blurred or excluded panel.

Usage: python scripts/panel_truth/cleanup_sheet.py <project_id> <out.png>
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from evaluate import DB  # noqa: E402
import sqlite3  # noqa: E402


def main(project_id, out):
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    ws, settings = db.execute("select workspace_path, settings from projects where id=?", (project_id,)).fetchone()
    report = (json.loads(settings or "{}").get("content_cleanup_report") or {}).get("panels", {})
    rows = {r[0]: r[1:] for r in db.execute("select id, sequence, status, crop_filename from panels where project_id=?",
                                            (project_id,))}
    counts = {}
    tiles = []
    for pid, item in sorted(report.items(), key=lambda kv: rows.get(kv[0], (0,))[0]):
        counts[item["action"]] = counts.get(item["action"], 0) + 1
        if item["action"] == "KEEP" or pid not in rows:
            continue
        seq, status, crop = rows[pid]
        im = Image.open(Path(ws) / "panels" / crop).convert("RGB")
        for m in item["matches"]:
            x, y, w, h = m["bbox"]
            pad = 200
            tile = im.crop((max(0, x - pad), max(0, y - pad), min(im.width, x + w + pad), min(im.height, y + h + pad)))
            tile.thumbnail((420, 300))
            label = Image.new("RGB", (420, 330), "white")
            label.paste(tile, (0, 30))
            ImageDraw.Draw(label).text((4, 4), f"#{seq} {item['action']} {status} {m['text'][:30]}", fill="black")
            tiles.append(label)
            if item["action"] == "EXCLUDE":
                break
    print("cleanup actions:", counts, "| panels:", len(rows),
          "| excluded:", sum(1 for r in rows.values() if r[1] == "IGNORED"))
    cols = 4
    sheet = Image.new("RGB", (cols * 425, max(1, (len(tiles) + cols - 1) // cols) * 335), "gray")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 425, (i // cols) * 335))
    sheet.save(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
