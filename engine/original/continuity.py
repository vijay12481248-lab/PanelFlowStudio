"""Check the cut between two consecutive clips (the "outgoing -> incoming state" of the shot state cards, references/multi-clip.md).

MEASURED LIMIT (Dawn Gate, 157 adjacent pairs; ChronoFlow cat chains, 37 pairs): in a film that cuts between angles the last frame of one clip and the first frame of the next
differ a lot even inside one scene (colour-histogram distance median 0.46 same scene vs 0.56 different scene; mean gray difference ~53 vs ~65) and the edge audio level
steps by a median of 8 dB (90th percentile 21 dB) before the master normalises it. So these numbers CANNOT tell a continuity break from a normal cut, and this module never
flags a cut. It flags only a boundary the caller declares CONTINUOUS (the next clip is meant to start where the previous one ended: a sliding-window chain, a first frame
taken from the previous clip's tail), where the next clip's first frame must still look like the previous clip's last frame. Thresholds come from `docs/H3_CLIP_EVAL.md`.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from engine.original.clip_eval import SIZE, _hist

HIST_MAX = 0.25  # continuous boundary: colour-histogram distance above this = suspected jump (measured continuation pairs: docs/H3_CLIP_EVAL.md; cuts run 0.3-0.7)
GRAY_MAX = 25.0  # mean absolute gray difference, 0-255 (cuts run 40-90)


def edge_frames(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """(first frame, last frame) of a clip at the analysis size."""
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, first = cap.read()
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n - 2))
    ok2, last = cap.read()
    cap.release()
    if not (ok and ok2):
        raise ValueError(f"{path}: cannot read the first and last frames")
    r = lambda f: cv2.resize(f, SIZE, interpolation=cv2.INTER_AREA)  # noqa: E731
    return r(first), r(last)


def boundary(prev: Path, nxt: Path, continuous: bool = False) -> dict:
    """Measurements for the cut prev -> nxt; flags only when `continuous` (see the module note)."""
    last = edge_frames(prev)[1]
    first = edge_frames(nxt)[0]
    hist = float(cv2.compareHist(_hist(last).astype(np.float32), _hist(first).astype(np.float32), cv2.HISTCMP_BHATTACHARYYA))
    gray = float(np.abs(cv2.cvtColor(last, cv2.COLOR_BGR2GRAY).astype(np.float32) - cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)).mean())
    flags = []
    if continuous and (hist > HIST_MAX or gray > GRAY_MAX):
        flags.append({"axis": "temporal", "status": "suspected", "t": None,
                      "evidence": f"declared continuous, but the first frame of the next clip differs from the last frame of the previous one (histogram {hist:.2f} > {HIST_MAX}, gray {gray:.1f} > {GRAY_MAX})"})
    return {"prev": str(prev), "next": str(nxt), "continuous": continuous, "hist_distance": round(hist, 3), "gray_diff": round(gray, 1), "flags": flags}


def chain(paths: list[Path], continuous: bool = True) -> list[dict]:
    """`boundary` for every consecutive pair of a list of clips."""
    return [boundary(a, b, continuous) for a, b in zip(paths, paths[1:])]
