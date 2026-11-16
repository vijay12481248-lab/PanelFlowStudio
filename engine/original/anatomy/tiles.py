"""Zoomed tiles of a picture, cut deterministically (no detector): the whole picture plus three overlapping bands along its long side, plus left and right
halves when two or more people are in it. Each tile is upscaled so a hand is readable to a small vision model; a thumbnail is what hid four arms from the agent."""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

OVERLAP = 0.15  # of one third, on each side of a band


@dataclass(frozen=True)
class Tile:
    name: str
    box: tuple[int, int, int, int]  # in the original picture's pixels
    png: bytes


def _png(image: Image.Image, box: tuple[int, int, int, int], target_side: int) -> bytes:
    tile = image.crop(box)
    scale = target_side / max(tile.size)
    tile = tile.resize((max(1, round(tile.width * scale)), max(1, round(tile.height * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    tile.save(buf, "PNG")
    return buf.getvalue()


def _band(length: int, i: int) -> tuple[int, int]:
    third, pad = length / 3, length / 3 * OVERLAP
    start = max(0, int(i * third - pad))
    end = min(length, max(start + 1, int((i + 1) * third + pad)))
    return start, end


def make_tiles(image: bytes, people: int | None = None, target_side: int = 1280) -> list[Tile]:
    with Image.open(io.BytesIO(image)) as opened:
        img = opened.convert("RGB")
    w, h = img.size
    tall = h >= w
    names = ["upper", "middle", "lower"] if tall else ["left_third", "middle", "right_third"]
    specs: list[tuple[str, tuple[int, int, int, int]]] = [("whole", (0, 0, w, h))]
    for i, name in enumerate(names):
        a, b = _band(h if tall else w, i)
        specs.append((name, (0, a, w, b) if tall else (a, 0, b, h)))
    if people is not None and people >= 2:
        half = max(1, w // 2)
        specs += [("left", (0, 0, half, h)), ("right", (min(half, w - 1), 0, w, h))]
    return [Tile(name, box, _png(img, box, target_side)) for name, box in specs]
