"""Zero-shot panel detection over a chapter strip, for model evaluation only.

Usage: python scripts/panel_truth/zero_shot.py <truth.json> <model> <out.json> [threshold]
model: gdino | owlv2
"""
import json
import sys
import time
from pathlib import Path

import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from render_strip_chunks import strip_pages  # noqa: E402

WINDOW, STRIDE, SCALE = 3840, 1920, 1 / 3
MODELS = {"gdino": "IDEA-Research/grounding-dino-base", "owlv2": "google/owlv2-base-patch16-ensemble"}


def load(name):
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    proc = AutoProcessor.from_pretrained(MODELS[name])
    model = AutoModelForZeroShotObjectDetection.from_pretrained(MODELS[name]).to("cuda").eval()
    return proc, model


PROMPT = "a comic panel."


@torch.inference_mode()
def detect(name, proc, model, image, threshold):
    if name == "gdino":
        inputs = proc(images=image, text=PROMPT, return_tensors="pt").to("cuda")
        out = model(**inputs)
        res = proc.post_process_grounded_object_detection(
            out, inputs.input_ids, threshold=threshold, text_threshold=threshold,
            target_sizes=[image.size[::-1]])[0]
    else:
        inputs = proc(text=[["a comic panel"]], images=image, return_tensors="pt").to("cuda")
        out = model(**inputs)
        side = max(image.size)  # owlv2 pads to a square
        res = proc.post_process_object_detection(out, threshold=threshold, target_sizes=[(side, side)])[0]
    return [(b.tolist(), float(s)) for b, s in zip(res["boxes"], res["scores"])]


def merge_cut(boxes, cuts, tol=40):
    """Join boxes split by a window edge: same x-span, one ends at a cut, the other starts near it."""
    boxes = sorted(boxes, key=lambda b: b[1])
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(boxes):
            for j, b in enumerate(boxes):
                if i == j:
                    continue
                ax2, bx2 = a[0] + a[2], b[0] + b[2]
                x_overlap = max(0, min(ax2, bx2) - max(a[0], b[0])) / max(1, min(a[2], b[2]))
                touches = any(abs(a[1] + a[3] - c) < tol for c in cuts) and b[1] <= a[1] + a[3] + tol and b[1] > a[1]
                if x_overlap > 0.8 and touches:
                    y2 = max(a[1] + a[3], b[1] + b[3])
                    boxes[i] = [min(a[0], b[0]), a[1], max(ax2, bx2) - min(a[0], b[0]), y2 - a[1], max(a[4], b[4])]
                    boxes.pop(j)
                    changed = True
                    break
            if changed:
                break
    return boxes


def nms(boxes, thr=0.6):
    from evaluate import iou
    keep = []
    for b in sorted(boxes, key=lambda b: -b[4]):
        if all(iou(b[:4], k[:4]) < thr for k in keep):
            keep.append(b)
    return keep


def main(truth_path, name, out_path, threshold=0.3):
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    proc, model = load(name)
    found, t0 = [], time.time()
    for y0, path, h in strip_pages(truth["project_id"]):
        with Image.open(path) as im:
            page = im.convert("RGB")
        tops = list(range(0, max(1, h - WINDOW + STRIDE), STRIDE))
        page_boxes, cuts = [], set()
        for top in tops:
            bottom = min(h, top + WINDOW)
            tile = page.crop((0, top, page.width, bottom))
            tile = tile.resize((round(tile.width * SCALE), round(tile.height * SCALE)))
            if top > 0:
                cuts.add(top)
            if bottom < h:
                cuts.add(bottom)
            for (x1, y1, x2, y2), score in detect(name, proc, model, tile, threshold):
                bx = [x1 / SCALE, top + y1 / SCALE, (x2 - x1) / SCALE, (y2 - y1) / SCALE, score]
                if bx[2] > 0.95 * page.width and bx[3] > 0.95 * (bottom - top):
                    continue  # the whole window, not a panel
                page_boxes.append(bx)
        found += [{"box": [round(b[0]), round(y0 + b[1]), round(b[2]), round(b[3])], "score": round(b[4], 3),
                   "page_y0": y0, "cuts": sorted(y0 + c for c in cuts)} for b in page_boxes]
    Path(out_path).write_text(json.dumps({"model": name, "panels": found}, indent=1), encoding="utf-8")
    print(f"{name}: {len(found)} boxes in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) > 4:
        PROMPT = a[4]
    main(a[0], a[1], a[2], float(a[3]) if len(a) > 3 else 0.3)
