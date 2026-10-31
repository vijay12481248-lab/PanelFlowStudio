"""Chapter-level panel / speech-bubble / promotion detection for vertical-scroll manhua and webtoons.

Pages are stacked into one strip so panels split across page files come out whole. A fine-tuned
RT-DETRv2 model (Apache-2.0 base) scans overlapping windows of the strip; window results are fused.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from engine.config.settings import settings

logger = logging.getLogger(__name__)

WIN_W, WIN_H, STRIDE = 1920, 3840, 1920  # strip pixels; the model sees 512x1024
MODEL_W = 512
EDGE = 30
CLASSES = ("panel", "bubble", "promo")
THRESHOLDS = {"panel": 0.5, "bubble": 0.4, "promo": 0.4}


def model_dir() -> Path:
    return settings.app_data_dir / "models" / "panel_detector"


def model_available() -> bool:
    return (model_dir() / "config.json").is_file()


@dataclass
class StripBox:
    cls: str
    box: list[float]  # x, y, w, h in strip pixels
    score: float
    cut: bool = False


@dataclass
class StripPage:
    page_id: str
    path: Path
    y0: int
    height: int


@dataclass
class StripResult:
    pages: list[StripPage]
    panels: list[StripBox] = field(default_factory=list)
    bubbles: list[StripBox] = field(default_factory=list)
    promos: list[StripBox] = field(default_factory=list)


def iou(a, b):
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / (a[2] * a[3] + b[2] * b[3] - inter) if inter else 0.0


def visible_elsewhere(box: list[float], top: float, total: float) -> bool:
    """Windows overlap by half: a box truncated by this window lies wholly inside a neighbour if it is short enough."""
    y0, y1 = box[1], box[1] + box[3]
    cut_bottom = top + WIN_H < total and top + WIN_H - y1 < EDGE
    cut_top = top > 0 and y0 - top < EDGE
    if cut_bottom and not cut_top:
        return y0 >= top + STRIDE  # the next window starts at top + STRIDE and holds it whole
    if cut_top and not cut_bottom:
        return y1 <= top + WIN_H - STRIDE  # the previous window ended there
    return False


def fuse(boxes: list[StripBox]) -> list[StripBox]:
    """Join pieces of one tall object seen by overlapping windows, then drop duplicates."""
    boxes = sorted(boxes, key=lambda b: b.box[1])
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a.cls != b.cls or not (a.cut or b.cut):
                    continue
                ax, ay, aw, ah = a.box
                bx, by, bw, bh = b.box
                x_iou = max(0, min(ax + aw, bx + bw) - max(ax, bx)) / max(1, max(ax + aw, bx + bw) - min(ax, bx))
                y_overlap = min(ay + ah, by + bh) - max(ay, by)
                if x_iou > 0.75 and y_overlap >= 0.3 * min(ah, bh):  # both windows saw the same rows
                    x0, y0 = min(ax, bx), min(ay, by)
                    x1, y1 = max(ax + aw, bx + bw), max(ay + ah, by + bh)
                    boxes[i] = StripBox(a.cls, [x0, y0, x1 - x0, y1 - y0], max(a.score, b.score), a.cut and b.cut)
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    keep: list[StripBox] = []
    for b in sorted(boxes, key=lambda b: (not b.cut, b.score), reverse=True):
        if all(k.cls != b.cls or iou(k.box, b.box) < 0.5 for k in keep):
            keep.append(b)
    return keep


def _scaled_strip(pages: list[StripPage], scale: float) -> np.ndarray:
    total = pages[-1].y0 + pages[-1].height
    strip = np.full((round(total * scale) + 2, round(WIN_W * scale), 3), 255, np.uint8)
    for p in pages:
        with Image.open(p.path) as im:
            small = np.asarray(im.convert("RGB").resize((strip.shape[1], max(1, round(p.height * scale))),
                                                        Image.BILINEAR))
        top = round(p.y0 * scale)
        strip[top:top + small.shape[0]] = small[:strip.shape[0] - top]
    return strip


class StripDetector:
    def __init__(self, path: Path | None = None, device: str | None = None):
        import torch
        from transformers import RTDetrV2ForObjectDetection
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = RTDetrV2ForObjectDetection.from_pretrained(str(path or model_dir())).to(self.device).eval()

    def detect(self, pages: list[StripPage], per_window: int = 60, cancelled=lambda: False) -> StripResult:
        torch = self.torch
        scale = MODEL_W / WIN_W
        strip = _scaled_strip(pages, scale)
        total = pages[-1].y0 + pages[-1].height
        win = round(WIN_H * scale)
        tops = list(range(0, max(1, total - WIN_H) + 1, STRIDE))
        if tops[-1] + WIN_H < total:
            tops.append(total - WIN_H)
        found: list[StripBox] = []
        with torch.inference_mode():
            for top in tops:
                if cancelled():
                    raise RuntimeError("Panel detection cancelled")
                crop = strip[round(top * scale):round(top * scale) + win]
                if crop.shape[0] < win:
                    crop = np.vstack([crop, np.full((win - crop.shape[0],) + crop.shape[1:], 255, np.uint8)])
                x = torch.from_numpy(crop.astype(np.float32) / 255.0).permute(2, 0, 1)[None].to(self.device)
                out = self.model(pixel_values=x)
                scores, labels = out.logits.sigmoid()[0].max(-1)
                order = scores.argsort(descending=True)[:per_window].tolist()
                boxes, scores, labels = out.pred_boxes[0].tolist(), scores.tolist(), labels.tolist()
                for k in order:
                    cls = CLASSES[labels[k]]
                    if scores[k] < THRESHOLDS[cls]:
                        continue
                    cx, cy, w, h = boxes[k]
                    x0, y0 = (cx - w / 2) * WIN_W, top + (cy - h / 2) * WIN_H
                    x1, y1 = (cx + w / 2) * WIN_W, top + (cy + h / 2) * WIN_H
                    x0, x1, y1 = max(0.0, x0), min(float(WIN_W), x1), min(float(total), y1)
                    y0 = max(0.0, y0)
                    box = [x0, y0, x1 - x0, y1 - y0]
                    if visible_elsewhere(box, top, total):
                        continue
                    cut = (y0 - top < EDGE and top > 0) or (top + WIN_H - y1 < EDGE and top + WIN_H < total)
                    found.append(StripBox(cls, box, scores[k], cut))
        result = StripResult(pages=pages)
        for b in fuse(found):
            getattr(result, {"panel": "panels", "bubble": "bubbles", "promo": "promos"}[b.cls]).append(b)
        result.panels = split_tall(result.panels, result.bubbles, strip, scale)
        result.panels += fill_uncovered(result, strip, scale)
        result.panels = [p for p in result.panels if has_art(strip, p.box, scale)]
        result.panels.sort(key=lambda b: (round(b.box[1] / 200), b.box[0]))
        return result


def content_rows(strip: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """Rows (in the scaled strip) holding artwork or text rather than plain gutter background."""
    import cv2
    gray = cv2.cvtColor(strip, cv2.COLOR_RGB2GRAY).astype(np.int16)
    margin = max(2, strip.shape[1] // 100)
    background = np.median(np.concatenate([gray[:, :margin], gray[:, -margin:]], axis=1), axis=1)
    return (np.abs(gray - background[:, None]) > 14).mean(axis=1) >= threshold


def has_art(strip: np.ndarray, box: list[float], scale: float, min_share: float = 0.04) -> bool:
    """False for a shot that is only flat colour or a gradient (e.g. the fade between two scenes)."""
    import cv2
    x, y, w, h = box
    crop = strip[round(y * scale):round((y + h) * scale), round(x * scale):round((x + w) * scale)]
    if crop.size == 0:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.int16)
    detail = np.abs(gray - np.median(gray, axis=1, keepdims=True)) > 20  # a row-wise gradient has no detail
    return float(detail.mean()) >= min_share


def split_tall(panels: list[StripBox], bubbles: list[StripBox], strip: np.ndarray, scale: float,
               max_ratio: float = 3.0) -> list[StripBox]:
    """A crop far taller than wide shows up tiny on screen; split it at seams that avoid speech bubbles."""
    from engine.imaging.panels.smart_slicer import SmartPanelSlicer
    out = []
    for p in panels:
        x, y, w, h = p.box
        if h <= max_ratio * w:
            out.append(p)
            continue
        seg = strip[round(y * scale):round((y + h) * scale), round(x * scale):round((x + w) * scale)]
        text = [(round((bx - x) * scale), round((by - y) * scale), round(bw * scale), round(bh * scale))
                for bx, by, bw, bh in (b.box for b in bubbles) if by < y + h and by + bh > y]
        slicer = SmartPanelSlicer(min_panel_height=round(0.5 * w * scale), max_panel_height=round(1.8 * w * scale))
        cuts = slicer.find_safe_horizontal_cut_lines(seg[:, :, ::-1].copy(), text_boxes=text,
                                                     target_height_range=(round(0.6 * w * scale), round(1.8 * w * scale)))
        edges = [0] + cuts + [seg.shape[0]]
        out += [StripBox(p.cls, [x, y + a / scale, w, (b - a) / scale], p.score) for a, b in zip(edges, edges[1:])]
    return out


def fill_uncovered(result: StripResult, strip: np.ndarray, scale: float, min_height: int = 300,
                   max_height: int = 2400) -> list[StripBox]:
    """Turn art the detector left uncovered (full-bleed webtoon art) into shots cut at safe seams."""
    from engine.imaging.panels.smart_slicer import SmartPanelSlicer
    art = strip.copy()
    for b in result.bubbles + result.promos:  # dialogue floating in a gutter is not a shot of its own
        x, y, w, h = [round(v * scale) for v in b.box]
        art[y:y + h, x:x + w] = art[y:y + h, :max(1, art.shape[1] // 100)].mean(axis=1, keepdims=True)
    rows = content_rows(art, threshold=0.2)
    covered = np.zeros_like(rows)
    for b in result.panels + result.promos:  # rows beside a narrow panel are taken too: shots are full rows
        _, y, _, h = b.box
        covered[round(y * scale):round((y + h) * scale)] = True
    free = rows & ~covered
    import cv2
    gap = max(1, round(40 * scale))
    free = cv2.morphologyEx(free.astype(np.uint8).reshape(-1, 1), cv2.MORPH_CLOSE,
                            np.ones((2 * gap + 1, 1), np.uint8)).reshape(-1).astype(bool) & ~covered
    bubbles = [b.box for b in result.bubbles]
    slicer = SmartPanelSlicer(min_panel_height=round(min_height * scale), max_panel_height=round(max_height * scale))
    added: list[StripBox] = []
    y = 0
    while y < len(free):
        if not free[y]:
            y += 1
            continue
        start = y
        while y < len(free) and free[y]:
            y += 1
        top, bottom = start / scale, y / scale
        if bottom - top < min_height:
            continue
        segment = strip[start:y]
        text = [(round(bx * scale), round((by - top) * scale), round(bw * scale), round(bh * scale))
                for bx, by, bw, bh in bubbles if by < bottom and by + bh > top]
        cuts = slicer.find_safe_horizontal_cut_lines(segment[:, :, ::-1].copy(), text_boxes=text,
                                                     target_height_range=(round(900 * scale), round(max_height * scale)))
        edges = [0] + cuts + [segment.shape[0]]
        for a, b in zip(edges, edges[1:]):
            if (b - a) / scale >= min_height / 2:
                added.append(StripBox("panel", [0.0, top + a / scale, float(WIN_W), (b - a) / scale], 0.0))
    return added


def page_of(pages: list[StripPage], y: float) -> StripPage:
    for p in pages:
        if p.y0 <= y < p.y0 + p.height:
            return p
    return pages[-1]


def crop_strip(pages: list[StripPage], box: list[float]) -> Image.Image:
    """Cut a strip-coordinate box out of the page files, stitching across page boundaries."""
    x, y, w, h = [int(round(v)) for v in box]
    out = Image.new("RGB", (max(1, w), max(1, h)), "white")
    for p in pages:
        if p.y0 + p.height <= y or p.y0 >= y + h:
            continue
        with Image.open(p.path) as im:
            part = im.convert("RGB").crop((x, max(0, y - p.y0), x + w, min(p.height, y + h - p.y0)))
        out.paste(part, (0, max(0, p.y0 - y)))
    return out


def is_vertical_scroll(page_sizes: list[tuple[int, int]]) -> bool:
    """Webtoon/manhua chapters are uniform-width slices of one strip, usually taller than a book page."""
    widths = {w for w, _ in page_sizes}
    tall = sorted(h / max(1, w) for w, h in page_sizes)
    return len(widths) == 1 and bool(tall) and tall[len(tall) // 2] >= 1.6


@dataclass
class PagePanel:
    page: StripPage
    box: list[int]  # x, y, w, h relative to the page; y + h may run into the next page
    strip_box: list[float]
    score: float
    promos: list[list[int]]  # promo boxes relative to the panel crop


def page_panels(result: StripResult, min_side: int = 80) -> list[PagePanel]:
    out = []
    for b in result.panels:
        x, y, w, h = b.box
        if w < min_side or h < min_side:
            continue
        page = page_of(result.pages, y)
        promos = []
        for p in result.promos:
            px, py, pw, ph = p.box
            ix0, iy0 = max(px, x), max(py, y)
            ix1, iy1 = min(px + pw, x + w), min(py + ph, y + h)
            if ix1 > ix0 and iy1 > iy0:
                promos.append([round(ix0 - x), round(iy0 - y), round(ix1 - ix0), round(iy1 - iy0)])
        out.append(PagePanel(page, [round(x), round(y - page.y0), round(w), round(h)], b.box, b.score, promos))
    return out


def save_debug(result: StripResult, path: Path) -> None:
    data = {k: [{"box": [round(v) for v in b.box], "score": round(b.score, 3)} for b in getattr(result, k)]
            for k in ("panels", "bubbles", "promos")}
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
