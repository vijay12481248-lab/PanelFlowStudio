"""Score panel predictions against strip ground truth.

Usage:
  python scripts/panel_truth/evaluate.py <truth.json> db            # panels currently stored for the project
  python scripts/panel_truth/evaluate.py <truth.json> <pred.json>   # {"panels": [{"box": [...], "ignored": bool}]}
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np

DB = Path(os.environ.get("PANELFLOW_APP_DATA", Path.home() / "AppData/Local/PanelFlow Studio")) / "database/panelflow.db"


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / (aw * ah + bw * bh - inter) if inter else 0.0


def coverage(inner, outer):
    """Fraction of `inner` that lies inside `outer`."""
    ix = max(0, min(inner[0] + inner[2], outer[0] + outer[2]) - max(inner[0], outer[0]))
    iy = max(0, min(inner[1] + inner[3], outer[1] + outer[3]) - max(inner[1], outer[1]))
    return ix * iy / max(1, inner[2] * inner[3])


def db_predictions(project_id):
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    starts, y = {}, 0
    for pid, h in db.execute("select id, height from pages where project_id=? order by sequence", (project_id,)):
        starts[pid], y = y, y + h
    rows = db.execute("select page_id, x, y, width, height, status from panels where project_id=? order by sequence",
                      (project_id,))
    return [{"box": [x, starts[page] + py, w, h], "ignored": status == "IGNORED"} for page, x, py, w, h, status in rows]


def evaluate(truth, preds, threshold=0.5):
    story = [p["box"] for p in truth["panels"] if p["kind"] == "story"]
    non_story = [p["box"] for p in truth["panels"] if p["kind"] != "story"]
    shown = [p["box"] for p in preds if not p.get("ignored")]
    pairs = sorted(((iou(g, p), gi, pi) for gi, g in enumerate(story) for pi, p in enumerate(shown)), reverse=True)
    used_g, used_p, matched = set(), set(), 0
    for score, gi, pi in pairs:
        if score < threshold:
            break
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        matched += 1
    merged = [pi for pi, p in enumerate(shown) if sum(coverage(g, p) >= 0.6 for g in story) >= 2]
    split = [gi for gi, g in enumerate(story) if sum(coverage(p, g) >= 0.6 and p[2] * p[3] >= 0.1 * g[2] * g[3]
                                                       for p in shown) >= 2]
    leaked = [n for n in non_story if any(coverage(n, p) >= 0.5 or coverage(p, n) >= 0.5 for p in shown)]
    missed = [gi for gi, g in enumerate(story) if not any(coverage(g, p) >= 0.6 for p in shown)]
    precision = matched / max(1, len(shown))
    recall = matched / max(1, len(story))
    return {
        "story_panels": len(story), "shown_crops": len(shown), "matched": matched,
        "precision": round(precision, 3), "recall": round(recall, 3),
        "f1": round(2 * precision * recall / max(1e-9, precision + recall), 3),
        "merged_crops": len(merged), "split_panels": len(split),
        "story_panels_not_shown": len(missed), "non_story_leaked": len(leaked),
        "tallest_crop_ratio": round(max((p[3] / max(1, p[2]) for p in shown), default=0), 2),
    }


def evaluate_shots(project_id, shown, bubbles):
    """Label-free checks for any chapter: art rows shown, tall crops, and crop edges slicing a bubble."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.imaging.panels import strip_detector as sd
    from render_strip_chunks import strip_pages
    pages = [sd.StripPage(str(i), p, y0, h) for i, (y0, p, h) in enumerate(strip_pages(project_id))]
    scale = 0.1
    rows = sd.content_rows(sd._scaled_strip(pages, scale))
    covered = np.zeros_like(rows)
    for x, y, w, h in shown:
        covered[round(y * scale):round((y + h) * scale)] = True
    sliced = sum(1 for x, y, w, h in shown for bx, by, bw, bh in bubbles
                 if (by + 0.15 * bh < y < by + 0.85 * bh or by + 0.15 * bh < y + h < by + 0.85 * bh)
                 and min(x + w, bx + bw) > max(x, bx))
    return {"art_rows_shown": round(float((rows & covered).sum() / max(1, rows.sum())), 3),
            "crops_over_2.5x_tall": sum(h > 2.5 * w for _, _, w, h in shown), "bubble_slices": sliced}


def evaluate_promos(truth, promos):
    """Recall of promo stamps/banners (any overlap counts: the whole box is blurred) and false alarms."""
    marks = [w["box"] for w in truth["watermarks"]]
    found = [m for m in marks if any(coverage(m, p) >= 0.5 for p in promos)]
    false = [p for p in promos if not any(iou(p, m) > 0 or coverage(p, m) > 0 for m in marks)]
    return {"promos": len(marks), "promo_recall": round(len(found) / max(1, len(marks)), 3),
            "false_promos": len(false)}


if __name__ == "__main__":
    truth = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    source = sys.argv[2]
    data = None if source == "db" else json.loads(Path(source).read_text(encoding="utf-8"))
    preds = db_predictions(truth["project_id"]) if data is None else data["panels"]
    if truth["panels"]:
        for t in (0.5, 0.7):
            print(f"IoU>={t}:", json.dumps(evaluate(truth, preds, t)))
    shown = [p["box"] for p in preds if not p.get("ignored")]
    print("shots:", json.dumps(evaluate_shots(truth["project_id"], shown, [b["box"] for b in (data or {}).get("bubbles", [])])))
    if data and "promos" in data:
        print("promo:", json.dumps(evaluate_promos(truth, [p["box"] for p in data["promos"]])))
