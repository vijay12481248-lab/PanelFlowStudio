"""Turn raw detector candidates into a non-overlapping panel set (evaluation prototype).

Usage: python scripts/panel_truth/postprocess.py <truth.json> <raw.json> <out.json> [min_score]
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from evaluate import coverage, iou  # noqa: E402
from render_strip_chunks import strip_pages  # noqa: E402
from zero_shot import merge_cut  # noqa: E402

SCALE = 0.25


class Strip:
    """Lazy low-res flatness map of the whole chapter strip."""

    def __init__(self, project_id):
        self.pages = strip_pages(project_id)
        self.cache = {}

    def flat_fraction(self, box, mask_boxes, background_boxes=()):
        """Share of `box` outside `mask_boxes` that is flat background; `background_boxes` count as background."""
        x, y, w, h = box
        rows = []
        for y0, path, ph in self.pages:
            if y0 + ph <= y or y0 >= y + h:
                continue
            if y0 not in self.cache:
                img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
                small = cv2.resize(img, (round(img.shape[1] * SCALE), round(img.shape[0] * SCALE)),
                                   interpolation=cv2.INTER_AREA)
                grad = cv2.GaussianBlur(np.abs(cv2.Laplacian(small, cv2.CV_32F)), (5, 5), 0)
                self.cache[y0] = grad < 4
            flat = self.cache[y0]
            top, bottom = max(y, y0), min(y + h, y0 + ph)
            rows.append(flat[round((top - y0) * SCALE):round((bottom - y0) * SCALE),
                             round(x * SCALE):round((x + w) * SCALE)])
        if not rows:
            return 0.0
        flat = np.concatenate(rows, axis=0).copy()

        def region(b):
            mx, my, mw, mh = b
            return (slice(max(0, round((my - y) * SCALE)), max(0, round((my + mh - y) * SCALE))),
                    slice(max(0, round((mx - x) * SCALE)), max(0, round((mx + mw - x) * SCALE))))

        for b in background_boxes:
            flat[region(b)] = True
        free = np.ones_like(flat, dtype=bool)
        for b in mask_boxes:
            free[region(b)] = False
        return float(flat[free].mean()) if free.any() else 0.0


def fill_gaps(page_y0, panels, bubbles, strip, min_side=0.25, min_solidity=0.5, margin=40):
    """Add boxes for art the detector left uncovered so no story content is dropped."""
    strip.flat_fraction([0, page_y0, 1, 1], [])  # loads the page's flatness map
    flat = strip.cache[page_y0]
    h, w = flat.shape
    content = (~flat).astype(np.uint8)
    content = cv2.morphologyEx(content, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    for b, pad in [(p, margin) for p in panels] + [(b, 0) for b in bubbles]:
        x, y, bw, bh = b  # panels get a margin: art bleeding past a frame is not a new panel
        content[max(0, round((y - pad - page_y0) * SCALE)):max(0, round((y + bh + pad - page_y0) * SCALE)),
                max(0, round((x - pad) * SCALE)):max(0, round((x + bw + pad) * SCALE))] = 0
    content = cv2.morphologyEx(content, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(content, connectivity=8)
    added = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bw < min_side * w or bh < min_side * w or area < min_solidity * bw * bh:
            continue
        added.append({"box": [round(x / SCALE), round(page_y0 + y / SCALE), round(bw / SCALE), round(bh / SCALE)],
                      "score": 0.0, "source": "gap_fill"})
    return added


def select(cands, strip, bubbles=(), group_flat=0.55, empty_flat=0.7):
    cands = [c for c in cands if not any(iou(c["box"], b) >= 0.5 or coverage(c["box"], b) >= 0.8 for b in bubbles)]
    boxes = sorted(cands, key=lambda c: -c["box"][2] * c["box"][3])
    dropped = set()
    for i, p in enumerate(boxes):
        kids = [c for j, c in enumerate(boxes) if j != i and coverage(c["box"], p["box"]) >= 0.85
                and c["box"][2] * c["box"][3] < 0.8 * p["box"][2] * p["box"][3]]
        disjoint = []
        for k in sorted(kids, key=lambda c: -c["score"]):
            if all(iou(k["box"], d["box"]) < 0.2 and coverage(k["box"], d["box"]) < 0.5 for d in disjoint):
                disjoint.append(k)
        inner = [b for b in bubbles if coverage(b, p["box"]) >= 0.6]
        flat = strip.flat_fraction(p["box"], [d["box"] for d in disjoint], inner)
        if (len(disjoint) >= 2 and flat >= group_flat) or flat >= empty_flat:
            dropped.add(i)  # a group of panels, or mostly gutter and bubbles
    kept = [b for i, b in enumerate(boxes) if i not in dropped]
    final = []
    for b in kept:  # largest first: an atomic panel swallows detail boxes inside it
        if any(coverage(b["box"], f["box"]) >= 0.8 for f in final):
            continue
        final.append(b)
    return final


def main(truth_path, raw_path, out_path, min_score=0.3, bubble_path=None, bubble_score=0.35):
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    raw = [c for c in json.loads(Path(raw_path).read_text(encoding="utf-8"))["panels"] if c["score"] >= min_score]
    bubbles = [c["box"] for c in json.loads(Path(bubble_path).read_text(encoding="utf-8"))["panels"]
               if c["score"] >= bubble_score and c["box"][2] <= 0.75 * 1920 and c["box"][3] <= 0.6 * 1920] \
        if bubble_path else []
    # A "bubble" box holding other bubbles is a group, not a balloon.
    bubbles = [b for b in bubbles if sum(coverage(o, b) >= 0.8 for o in bubbles if o is not b) == 0]
    strip = Strip(truth["project_id"])
    out = []
    for y0 in sorted({c["page_y0"] for c in raw}):
        page = [c for c in raw if c["page_y0"] == y0]
        cuts = page[0]["cuts"]
        joined = merge_cut([c["box"] + [c["score"]] for c in page], cuts)
        page = [{"box": [round(v) for v in b[:4]], "score": b[4]} for b in joined]
        chosen = select(page, strip, bubbles)
        page_bubbles = [b for b in bubbles if b[1] < y0 + 10 ** 6]
        out += chosen + fill_gaps(y0, [c["box"] for c in chosen], page_bubbles, strip)
    Path(out_path).write_text(json.dumps({"panels": out}, indent=1), encoding="utf-8")
    print(len(out), "panels")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], float(a[3]) if len(a) > 3 else 0.3, a[4] if len(a) > 4 else None,
         float(a[5]) if len(a) > 5 else 0.35)
