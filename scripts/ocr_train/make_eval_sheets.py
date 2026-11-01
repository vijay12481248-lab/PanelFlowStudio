"""Cut real speech-bubble lines out of a project's panels into numbered contact sheets for hand transcription.

The eval set lives in app data (not git): it holds cropped pages of a copyrighted series.
Usage: python scripts/ocr_train/make_eval_sheets.py <project_id> <out_dir> [count] [per_sheet] [seed]
"""
import json
import random
import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.config.settings import settings  # noqa: E402
from engine.imaging.content_cleanup import is_promo_text, load_rules  # noqa: E402


def main(project_id, out_dir, count=72, per_sheet=12, seed=3):
    db = sqlite3.connect(f"file:{(settings.app_data_dir / 'database/panelflow.db').as_posix()}?mode=ro", uri=True)
    ws = Path(db.execute("select workspace_path from projects where id=?", (project_id,)).fetchone()[0])
    labels = load_rules().labels
    lines = []
    for panel_id, crop, blocks in db.execute(
            "select p.id, p.crop_filename, o.raw_blocks from ocr_results o join panels p on p.id=o.panel_id "
            "where o.project_id=? and p.status!='IGNORED' order by p.sequence", (project_id,)):
        for b in json.loads(blocks):
            x, y, w, h = b["bbox"]
            if w >= 60 and h >= 14 and not is_promo_text(b["detected_text"], labels):
                lines.append({"panel_id": panel_id, "crop": crop, "bbox": [x, y, w, h], "windows_text": b["detected_text"]})
    random.Random(seed).shuffle(lines)
    picked = lines[:count]
    out = Path(out_dir)
    (out / "lines").mkdir(parents=True, exist_ok=True)
    for i, ln in enumerate(picked):
        x, y, w, h = ln["bbox"]
        with Image.open(ws / "panels" / ln["crop"]) as im:
            pad = 4
            crop = im.convert("RGB").crop((max(0, x - pad), max(0, y - pad), min(im.width, x + w + pad), min(im.height, y + h + pad)))
        crop.save(out / "lines" / f"line_{i:03d}.png")
        ln["file"] = f"line_{i:03d}.png"
    (out / "candidates.json").write_text(json.dumps(picked, indent=1), encoding="utf-8")
    for s in range(0, len(picked), per_sheet):
        chunk = picked[s:s + per_sheet]
        tiles = []
        for k, ln in enumerate(chunk, start=s):
            im = Image.open(out / "lines" / ln["file"])
            scale = min(900 / im.width, 3.0)
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
            tile = Image.new("RGB", (940, im.height + 22), "white")
            ImageDraw.Draw(tile).text((4, 4), f"#{k}", fill="red")
            tile.paste(im, (36, 20))
            tiles.append(tile)
        sheet = Image.new("RGB", (940, sum(t.height + 6 for t in tiles)), (200, 200, 200))
        y = 0
        for t in tiles:
            sheet.paste(t, (0, y))
            y += t.height + 6
        sheet.save(out / f"sheet_{s // per_sheet:02d}.png")
    print(f"{len(picked)} lines of {len(lines)} candidates -> {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], *(int(v) for v in a[2:]))
