"""Hold the camera still after generation: remove the clip's global zoom/pan, measured against the BACKGROUND (area-weighted dense flow, `clip_eval.camera_motion_area`'s method).

H3 sometimes drifts the framing a few percent even when told the camera is fixed (storyboard clips: pan 5-10%, tilt 11%). A drift that small is cheap to undo: every frame is warped back to the
first frame's framing and the whole clip is zoomed in just enough to hide the borders. A drift beyond `max_drift_pct` would need a big crop (soft picture), so the clip is left alone and reported:
the cause is then in the pictures (a different scale between the start and end picture) and the shot should be redrawn, not stabilised.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2
import numpy as np

FLOW = (384, 216)  # the evaluator's analysis size (clip_eval.SIZE): the stabiliser and the judge must measure the same pixels (at 192x108 a walking subject made the estimate wrong and a clip got worse)


def steps(gray: list, stride: int = 6) -> list[tuple[float, float, float]]:
    """(log scale, tx, ty) between frames `stride` apart, about the frame centre, in FLOW pixels: one robust similarity per pair from a regular grid of flow vectors (every area one vote)."""
    h, w = gray[0].shape
    ys, xs = np.mgrid[h // 16:h:h // 8, w // 16:w:w // 8]
    pts = np.stack([xs.ravel(), ys.ravel()], axis=1).astype(np.float32)
    centre = np.array([w / 2, h / 2], dtype=np.float32)
    out = []
    for a, b in zip(gray[::stride], gray[stride::stride]):
        a, b = (cv2.normalize(x, None, 0, 255, cv2.NORM_MINMAX) for x in (a, b))
        flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        moved = pts + flow[pts[:, 1].astype(int), pts[:, 0].astype(int)]
        m, _ = cv2.estimateAffinePartial2D(pts - centre, moved - centre, method=cv2.RANSAC, ransacReprojThreshold=0.6)
        out.append((math.log(max(1e-6, math.hypot(m[0, 0], m[1, 0]))), float(m[0, 2]), float(m[1, 2])) if m is not None else (0.0, 0.0, 0.0))
    return out


def cumulative(st: list[tuple[float, float, float]], n: int, stride: int = 6) -> np.ndarray:
    """Per-frame (log scale, tx, ty) relative to frame 0 as a STRAIGHT RAMP to the net drift (the sum of the measured steps, the same number `clip_eval.camera_motion_area` reports). Camera drift
    is slow and near-linear; a character stepping toward the camera (a transient in the middle of the clip) is not, and must not be 'corrected' (measured: correcting every frame put a -6% zoom
    into three steady clips, and a least-squares line through the noisy samples invented 3-5% of drift in steady ones)."""
    net = np.array(st).sum(axis=0) if st else np.zeros(3)
    return (np.arange(n) / max(1, n - 1))[:, None] * net[None, :]


def drift_pct(c: np.ndarray) -> float:
    """The clip's net framing change, as a percentage of the frame: the biggest of zoom and pan at the end of the line."""
    w, h = FLOW
    return float(max(abs(math.expm1(c[-1, 0])), abs(c[-1, 1]) / w, abs(c[-1, 2]) / h) * 100)


def stabilize(src: Path, dst: Path, max_drift_pct: float = 12.0, min_drift_pct: float = 3.0) -> dict:
    """Write `dst` = `src` with the camera drift removed (sound copied). Returns {"applied": bool, "drift_pct", "crop_zoom", "reason"}; nothing is written unless applied."""
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    if len(frames) < 12:
        return {"applied": False, "reason": "too few frames"}
    h, w = frames[0].shape[:2]
    small = [cv2.cvtColor(cv2.resize(f, FLOW, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY) for f in frames]
    c = cumulative(steps(small), len(small))
    d = drift_pct(c)
    if d < min_drift_pct:
        return {"applied": False, "drift_pct": round(d, 2), "reason": "already steady"}
    if d > max_drift_pct:
        return {"applied": False, "drift_pct": round(d, 2), "reason": f"drift {d:.1f}% is beyond {max_drift_pct}%: it would need a soft crop; redraw the shot's pictures instead"}
    fw, fh = FLOW
    s = np.exp(c[:, 0])
    crop = float(np.max(np.maximum(s, 1.0)) * (1 + 2 * max(np.max(np.abs(c[:, 1])) / fw, np.max(np.abs(c[:, 2])) / fh)))  # enough zoom that no warped frame shows an empty border
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-", "-i", str(src), "-map", "0:v", "-map", "1:a?",
           "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", str(dst)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i, f in enumerate(frames):
        # undo frame i's camera (scale s_i, shift t_i, in frame-size units) then zoom by `crop` about the centre
        k = crop / s[i]
        tx, ty = -c[i, 1] / fw * w * k, -c[i, 2] / fh * h * k
        m = np.array([[k, 0, w / 2 - k * w / 2 + tx], [0, k, h / 2 - k * h / 2 + ty]], np.float32)
        proc.stdin.write(cv2.warpAffine(f, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        return {"applied": False, "reason": "ffmpeg failed"}
    from engine.original.clip_eval import camera_motion_area, load_clip

    def worst(p: Path) -> float:
        a = camera_motion_area(load_clip(p).gray)
        return max(abs(a["zoom_pct"]), abs(a["pan_x_pct"]), abs(a["pan_y_pct"]))

    before, after = worst(src), worst(dst)
    if after > 0.6 * before:  # the evaluator must agree it got better, or the original is kept
        dst.unlink(missing_ok=True)
        return {"applied": False, "drift_pct": round(d, 2), "reason": f"did not help: the evaluator still measures {after:.1f}% (was {before:.1f}%)"}
    return {"applied": True, "drift_pct": round(d, 2), "crop_zoom": round(crop, 3), "before_pct": round(before, 1), "after_pct": round(after, 1)}
