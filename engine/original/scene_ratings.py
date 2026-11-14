"""Owner ratings of delivered scene pictures: the store and the numbers the Scene Director is judged by (docs/SCENE_DIRECTOR.md)."""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

REASONS = ("emotion", "pose", "camera", "identity", "style", "other")


class Rating(BaseModel):
    brief_id: str
    mode: str  # "raw" (brief straight to the image model) | "director" (scene plan + check)
    good: bool
    reason: str = ""  # one of REASONS, only meaningful when not good
    seconds: float = 0.0
    plan_path: str = ""


def load_ratings(path: Path) -> list[Rating]:
    path = Path(path)
    if not path.exists():
        return []
    return [Rating(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def save_rating(path: Path, r: Rating) -> None:
    """One rating per (brief, mode): a new one replaces the old. Written through a temp file so a crash never leaves half a file."""
    path = Path(path)
    rows = [x for x in load_ratings(path) if (x.brief_id, x.mode) != (r.brief_id, r.mode)] + [r]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps([x.model_dump() for x in rows], indent=2), encoding="utf-8")
    os.replace(tmp, path)


def summary(ratings: list[Rating]) -> dict:
    n = len(ratings)
    if n == 0:
        return {"n": 0, "good_rate": 0.0, "by_reason": {}, "mean_seconds": 0.0}
    return {
        "n": n,
        "good_rate": sum(r.good for r in ratings) / n,
        "by_reason": dict(Counter(r.reason or "other" for r in ratings if not r.good)),
        "mean_seconds": sum(r.seconds for r in ratings) / n,
    }
