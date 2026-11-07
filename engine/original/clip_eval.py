"""Evaluate a generated H3 clip from evidence, not from a score.

Phase 0 of the H3 skill (see docs/H3_CLIP_EVAL.md): deterministic measurements first (camera path, cuts, flicker, stillness, appearance drift,
audio), then flags that carry a timestamp and a status. There is NO overall score: each axis stands alone, and a flag is `confirmed` only when a
measurement backs it. A vision-language witness is a separate, optional call (`vlm_witness`), because the local 9B model is a noisy judge.

Thresholds below are PROVISIONAL: they were set from synthetic clips and then checked against the labelled real clips (docs/H3_CLIP_EVAL.md).
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

SIZE = (384, 216)  # analysis size; every metric is relative to the frame so it does not depend on the clip's resolution
MAX_FRAMES = 400  # H3 tops out at 15 s * 24 fps = 362
SAMPLES = 8  # frames in a contact sheet

# provisional thresholds (percent of frame, gray levels, ...)
ZOOM_STATIC_PCT = 3.0  # |total zoom| above this in a clip that must have a fixed camera
PAN_STATIC_PCT = 3.0  # |total pan| (percent of width/height) above this in a fixed-camera clip
CAMERA_MAX_PCT = 50.0  # beyond this the tracker may have lost the picture (fast motion): `confirmed` only if the tracker also kept nearly all points
CAMERA_SURE_INLIERS = 0.9  # measured: Dawn Gate p046 +164% zoom had inliers 0.99 (real); the lost-track cases had 0.61-0.81
LOST_RATIO, LOST_STEPS = 0.3, 5  # a frame step where fewer than 30% of tracked points agree is a lost picture; this many in a clip = suspected transition (p005 variants 7-10, 19/140 Dawn clips >=3)
RING = 0.18  # outer band of the frame used to tell a camera move from a subject move
CAMERA_MIN_INLIERS = 0.5  # below this the dominant motion is probably the subject, not the camera: report `suspected`, never `confirmed`
CUT_RATIO, CUT_MIN = 8.0, 40.0  # a frame step this many times the median step (and at least this many gray levels) is a cut; measured: fast continuous action reaches ~28 (Dawn Gate p078, not a cut), a real scene change 57-92 (p005)
FLICKER_MAX = 1.5  # mean |L[i] - (L[i-1]+L[i+1])/2| in gray levels
STILL_MOTION = 0.3  # measured: calm approved clips (first frame = last frame) run 0.27-1.7; film.py's 0.9 would flag half of them
DRIFT_HIST = 0.35  # Bhattacharyya distance of the colour histogram, a sampled frame against frame 0


@dataclass
class Clip:
    path: Path
    fps: float
    bgr: list  # list[np.ndarray] at SIZE
    gray: list

    @property
    def n(self) -> int:
        return len(self.bgr)

    def t(self, i: int) -> float:
        return round(i / self.fps, 2)


def load_clip(path: Path, max_frames: int = MAX_FRAMES) -> Clip:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    bgr: list = []
    while len(bgr) < max_frames:
        ok, f = cap.read()
        if not ok:
            break
        bgr.append(cv2.resize(f, SIZE, interpolation=cv2.INTER_AREA))
    cap.release()
    if len(bgr) < 2:
        raise ValueError(f"{path}: fewer than 2 decodable frames")
    return Clip(Path(path), float(fps), bgr, [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in bgr])


# ------------------------------------------------------------------ measurements
def _ring_mask(shape: tuple, ring: float) -> np.ndarray:
    h, w = shape
    m = np.zeros((h, w), np.uint8)
    m[:] = 255
    m[int(h * ring): h - int(h * ring), int(w * ring): w - int(w * ring)] = 0
    return m


def camera_motion(gray: list, ring: float | None = None) -> dict:
    """Dominant (RANSAC similarity) motion of the picture between neighbouring frames, accumulated over the clip and measured about the frame
    centre: zoom about the centre gives no translation. Subject motion is rejected as outliers while the background dominates; in a close-up the
    subject IS the dominant motion, so `inliers` (share of tracked points that agree) says how far to trust the result. `ring`: track only the outer
    band of the frame (that fraction of each side), where the subject usually is not: a zoom seen there too is the camera."""
    h, w = gray[0].shape
    centre = np.array([w / 2, h / 2], dtype=np.float32)
    mask = _ring_mask(gray[0].shape, ring) if ring else np.full((h, w), 255, np.uint8)
    log_s = rot = tx = ty = 0.0
    inliers, path, lost = [], [(0.0, 0.0, 0.0)], []
    for i, (a, b) in enumerate(zip(gray, gray[1:])):
        pts = cv2.goodFeaturesToTrack(a, 300, 0.01, 7, mask=mask)
        ratio = 0.0
        if pts is not None and len(pts) >= 12:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None)
            ok = st.ravel() == 1
            p0, p1 = pts[ok].reshape(-1, 2), nxt[ok].reshape(-1, 2)
            if len(p0) >= 12:
                m, agree = cv2.estimateAffinePartial2D(p0 - centre, p1 - centre, method=cv2.RANSAC, ransacReprojThreshold=1.5)
                if m is not None:
                    log_s += math.log(max(1e-6, math.hypot(m[0, 0], m[1, 0])))
                    rot += math.atan2(m[1, 0], m[0, 0])
                    tx, ty = tx + float(m[0, 2]), ty + float(m[1, 2])
                    ratio = float(agree.sum()) / len(p0)
                    if ratio < LOST_RATIO:
                        lost.append(i + 1)
        inliers.append(ratio)
        path.append((math.exp(log_s) - 1, tx / w, ty / h))
    return {"zoom_pct": round((math.exp(log_s) - 1) * 100, 2), "pan_x_pct": round(tx / w * 100, 2), "pan_y_pct": round(ty / h * 100, 2),
            "roll_deg": round(math.degrees(rot), 2), "lost_steps": len(lost), "first_lost": lost[0] if lost else None, "inliers": round(float(np.median(inliers)), 2),
            "zoom_curve_pct": [round(path[min(len(path) - 1, round(k * (len(path) - 1) / 4))][0] * 100, 2) for k in range(5)]}


def camera_motion_area(gray: list, step: int = 6) -> dict:
    """Camera zoom/pan weighted by AREA, not by detail: dense optical flow on a regular grid of points, one robust similarity fit per frame pair `step` frames apart, accumulated.
    `camera_motion` tracks corner features, which sit on the most detailed object (a character), so a girl who steps toward the camera or an animal that moves reads as a camera zoom
    (measured: Dawn-Gate-style storyboard clips showed -35% zoom and -195% pan while the background did not move). Here every region of the frame has one vote and a subject covering
    less than half the frame is out-voted. Textureless sky gives ~zero flow, so a real camera move can read a little low: use it with `camera_motion`, not instead (flag only when both agree)."""
    h, w = gray[0].shape
    ys, xs = np.mgrid[h // 16:h:h // 8, w // 16:w:w // 8]
    pts = np.stack([xs.ravel(), ys.ravel()], axis=1).astype(np.float32)
    centre = np.array([w / 2, h / 2], dtype=np.float32)
    log_s = tx = ty = 0.0
    for a, b in zip(gray[::step], gray[step::step]):
        a, b = (cv2.normalize(x, None, 0, 255, cv2.NORM_MINMAX) for x in (a, b))  # dark storm scenes have little contrast: stretch it, or the flow reads low
        flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        moved = pts + flow[pts[:, 1].astype(int), pts[:, 0].astype(int)]
        m, _ = cv2.estimateAffinePartial2D(pts - centre, moved - centre, method=cv2.RANSAC, ransacReprojThreshold=0.6)
        if m is not None:
            log_s += math.log(max(1e-6, math.hypot(m[0, 0], m[1, 0])))
            tx, ty = tx + float(m[0, 2]), ty + float(m[1, 2])
    return {"zoom_pct": round((math.exp(log_s) - 1) * 100, 2), "pan_x_pct": round(tx / w * 100, 2), "pan_y_pct": round(ty / h * 100, 2)}


def step_diffs(gray: list) -> np.ndarray:
    return np.array([float(np.abs(b.astype(np.float32) - a.astype(np.float32)).mean()) for a, b in zip(gray, gray[1:])])


def motion_stats(diffs: np.ndarray) -> dict:
    win = np.convolve(diffs, np.ones(12) / 12, "valid") if len(diffs) > 12 else diffs
    return {"motion": round(float(diffs.mean()), 3), "motion_min_window": round(float(win.min()), 3)}


def find_cuts(diffs: np.ndarray) -> list[int]:
    """Frame indices (the first frame of the new shot) where the picture changes far more than anywhere else: an unrequested scene transition."""
    base = max(float(np.median(diffs)), 0.5)
    return [i + 1 for i, d in enumerate(diffs) if d > max(CUT_RATIO * base, CUT_MIN)]


def flicker(gray: list) -> float:
    lum = np.array([float(g.mean()) for g in gray])
    return round(float(np.abs(lum[1:-1] - (lum[:-2] + lum[2:]) / 2).mean()), 3) if len(lum) > 2 else 0.0


def _hist(bgr: np.ndarray) -> np.ndarray:
    h = cv2.calcHist([cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 8], [0, 180, 0, 256])
    return cv2.normalize(h, h, norm_type=cv2.NORM_L1).flatten()


def appearance_drift(clip: Clip, reference: np.ndarray | None = None, idx: list[int] | None = None) -> dict:
    """Colour-histogram distance of sampled frames to frame 0 (or to a reference picture). Catches outfit/colour change and scene change; it cannot
    tell the two apart and moves with the camera, so it is a trigger for a closer look, not a verdict."""
    idx = idx or sample_indices(clip.n)
    base = _hist(cv2.resize(reference, SIZE) if reference is not None else clip.bgr[0])
    d = [round(float(cv2.compareHist(base.astype(np.float32), _hist(clip.bgr[i]).astype(np.float32), cv2.HISTCMP_BHATTACHARYYA)), 3) for i in idx]
    k = int(np.argmax(d))
    return {"max": d[k], "at_s": clip.t(idx[k]), "final": d[-1], "series": d}


def audio_stats(path: Path) -> dict:
    """RMS level and share of silent 100 ms windows of the clip's own audio (16 kHz mono). `has_audio` False when there is no audio stream."""
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(pcm[: len(pcm) - len(pcm) % 4], dtype=np.float32)
    if x.size == 0:
        return {"has_audio": False}
    win = x[: x.size - x.size % 1600].reshape(-1, 1600)
    rms = np.sqrt((win ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    return {"has_audio": True, "rms_dbfs": round(float(20 * np.log10(np.sqrt((x ** 2).mean() + 1e-12))), 1), "silent_fraction": round(float((db < -50).mean()), 2)}


def sample_indices(n: int, k: int = SAMPLES) -> list[int]:
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def contact_sheet(clip: Clip, idx: list[int] | None = None, cols: int = 4) -> bytes:
    """One PNG of the sampled frames in time order, each labelled with its timestamp (for the VLM witness and for the human reading the report)."""
    idx = idx or sample_indices(clip.n)
    tiles = []
    for i in idx:
        t = clip.bgr[i].copy()
        cv2.putText(t, f"{clip.t(i):.2f}s", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(t, f"{clip.t(i):.2f}s", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(t)
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[r:r + cols]) for r in range(0, len(tiles), cols)]
    ok, png = cv2.imencode(".png", np.vstack(rows))
    return png.tobytes()


# ------------------------------------------------------------------ the report
def evaluate(path: Path, expect_camera: str = "static", reference: np.ndarray | None = None, expect_audio: bool = True, planned_cuts: list[float] | None = None,
             _clip: Clip | None = None) -> dict:
    """Measurements plus flags for one clip. `expect_camera`: "static" (a fixed camera was asked for) or "any" (a move was asked for: the camera
    path is reported but not flagged). Every flag: {axis, status: confirmed|suspected, t, evidence}. No overall score by design.
    `planned_cuts`: times (s) of cuts the plan put INSIDE this clip (a multi-shot take): each shot is measured on its own (`evaluate_take`) and a planned cut is not a defect."""
    if planned_cuts:
        return evaluate_take(path, planned_cuts, expect_camera, reference, expect_audio)
    clip = _clip or load_clip(Path(path))
    diffs = step_diffs(clip.gray)
    cam = camera_motion(clip.gray)
    cuts = find_cuts(diffs)
    flick = flicker(clip.gray)
    drift = appearance_drift(clip, reference)
    audio = audio_stats(Path(path))
    mot = motion_stats(diffs)
    flags: list[dict] = []

    def flag(axis: str, status: str, t: float | None, evidence: str) -> None:
        flags.append({"axis": axis, "status": status, "t": t, "evidence": evidence})

    ring = camera_motion(clip.gray, RING)
    # confirmed only when the whole frame and its border agree in sign, the tracker kept most points, and the numbers are sane
    trust = cam["inliers"] >= CAMERA_MIN_INLIERS and ring["inliers"] >= CAMERA_MIN_INLIERS and (abs(cam["zoom_pct"]) <= CAMERA_MAX_PCT or min(cam["inliers"], ring["inliers"]) >= CAMERA_SURE_INLIERS) and cam["zoom_pct"] * ring["zoom_pct"] > 0
    area = camera_motion_area(clip.gray)
    # the AREA-weighted estimate is the arbiter: the feature tracker follows the most detailed object, so a girl stepping toward the camera read as a zoom (storyboard clips: features +9.8%,
    # area +0.5%, background still by eye). A flag needs the area estimate to see it too; features alone are the subject moving, not the camera.
    big = lambda v, lim: abs(v) > lim  # noqa: E731
    if expect_camera == "static":
        if big(area["zoom_pct"], ZOOM_STATIC_PCT) and big(cam["zoom_pct"], ZOOM_STATIC_PCT / 2):
            flag("camera", "confirmed" if trust or big(area["zoom_pct"], 2 * ZOOM_STATIC_PCT) else "suspected", None,
                 f"total zoom {area['zoom_pct']:+.1f}% by area (features {cam['zoom_pct']:+.1f}%, border {ring['zoom_pct']:+.1f}%) over {clip.t(clip.n - 1)}s")
        if max(abs(area["pan_x_pct"]), abs(area["pan_y_pct"])) > PAN_STATIC_PCT and max(abs(cam["pan_x_pct"]), abs(cam["pan_y_pct"])) > PAN_STATIC_PCT / 2:
            flag("camera", "confirmed" if trust or max(abs(area["pan_x_pct"]), abs(area["pan_y_pct"])) > 2 * PAN_STATIC_PCT else "suspected", None,
                 f"total pan x {area['pan_x_pct']:+.1f}% y {area['pan_y_pct']:+.1f}% by area (features {cam['pan_x_pct']:+.1f}/{cam['pan_y_pct']:+.1f}, border {ring['pan_x_pct']:+.1f}/{ring['pan_y_pct']:+.1f})")
    if cam["lost_steps"] >= LOST_STEPS and not cuts:
        flag("temporal", "suspected", clip.t(cam["first_lost"]), f"tracker lost the picture in {cam['lost_steps']} frame steps (first at {clip.t(cam['first_lost'])}s): a scene transition or violent motion, look at the frames")
    for c in cuts:
        flag("temporal", "confirmed", clip.t(c), f"hard cut: frame step {diffs[c - 1]:.1f} vs median {float(np.median(diffs)):.1f}")
    if flick > FLICKER_MAX:
        flag("artifacts", "suspected", None, f"luminance flicker {flick} > {FLICKER_MAX}")
    if mot["motion"] < STILL_MOTION:
        flag("motion", "suspected", None, f"mean frame step {mot['motion']} < {STILL_MOTION}: reads as a still picture")
    if drift["max"] > DRIFT_HIST and not cuts:
        flag("consistency", "suspected", drift["at_s"], f"colour histogram distance {drift['max']} from frame 0 (outfit/colour change or lighting)")
    if expect_audio and not audio["has_audio"]:
        flag("audio", "confirmed", None, "no audio stream")
    return {"clip": str(path), "frames": clip.n, "seconds": clip.t(clip.n - 1) + round(1 / clip.fps, 2), "camera": cam, "camera_border": ring, "camera_area": area, "cuts_s": [clip.t(c) for c in cuts],
            "flicker": flick, "drift": drift, "audio": audio, **mot, "flags": flags}


def evaluate_take(path: Path, planned_cuts: list[float], expect_camera: str = "static", reference: np.ndarray | None = None, expect_audio: bool = True, trim: int = 4) -> dict:
    """A take with planned shot changes: split at the planned times, drop `trim` frames either side of each cut, measure every shot on its own (camera, drift against the shot's own
    first frame, flicker, unplanned cuts) and merge: flags keep their time (shifted to the take) and name the shot; the report carries the worst camera/drift/flicker and `segments`."""
    clip = load_clip(Path(path))
    diffs = step_diffs(clip.gray)
    marks, deviation = [], []
    for t in sorted(planned_cuts):  # H3 puts a planned cut near, not at, the asked time (measured: 7.2 s for 7.5 s): snap to the strongest real cut within +-1 s, else keep the plan
        m = round(t * clip.fps)
        win = range(max(0, m - 24), min(len(diffs), m + 24))
        best = max(win, key=lambda i: diffs[i], default=None)
        if best is not None and diffs[best] >= CUT_MIN:
            deviation.append(round((best + 1 - m) / clip.fps, 2))
            m = best + 1
        marks.append(m)
    bounds = [0] + [m for m in marks if 0 < m < clip.n] + [clip.n]
    segs, flags, cuts = [], [], []
    for k in range(len(bounds) - 1):
        a, b = bounds[k] + (trim if k else 0), bounds[k + 1] - (trim if k < len(bounds) - 2 else 0)
        if b - a < 14:
            continue
        sub = Clip(clip.path, clip.fps, clip.bgr[a:b], clip.gray[a:b])
        r = evaluate(path, expect_camera, reference if k == 0 else None, expect_audio=False, _clip=sub)
        off = a / clip.fps
        for f in r["flags"]:
            flags.append({**f, "t": None if f["t"] is None else round(f["t"] + off, 2), "evidence": f"[shot {k + 1}, {a / clip.fps:.1f}-{b / clip.fps:.1f}s] {f['evidence']}"})
        cuts += [round(c + off, 2) for c in r["cuts_s"]]
        segs.append({"shot": k + 1, "from_s": round(a / clip.fps, 2), "to_s": round(b / clip.fps, 2), "camera": r["camera"], "drift": r["drift"]["max"], "flicker": r["flicker"], "motion": r["motion"], "flags": [f["axis"] + ":" + f["status"] for f in r["flags"]]})
    audio = audio_stats(Path(path))
    if expect_audio and not audio["has_audio"]:
        flags.append({"axis": "audio", "status": "confirmed", "t": None, "evidence": "no audio stream"})
    worst = max((sg for sg in segs), key=lambda sg: max(abs(sg["camera"]["zoom_pct"]), abs(sg["camera"]["pan_x_pct"]), abs(sg["camera"]["pan_y_pct"])))
    return {"clip": str(path), "frames": clip.n, "seconds": clip.t(clip.n - 1) + round(1 / clip.fps, 2), "camera": worst["camera"], "camera_border": worst["camera"], "cuts_s": cuts, "planned_cuts_s": sorted(planned_cuts), "cut_deviation_s": deviation,
            "flicker": max(sg["flicker"] for sg in segs), "drift": {"max": max(sg["drift"] for sg in segs), "at_s": None, "final": 0.0, "series": []}, "audio": audio,
            "motion": round(float(np.mean([sg["motion"] for sg in segs])), 3), "motion_min_window": 0.0, "flags": flags, "segments": segs}


# ------------------------------------------------------------------ vision witness (optional, needs Ollama)
VLM_QUESTIONS = {
    "same_character": "Do all frames show the same character(s) with the same face, hair, outfit and body proportions? Answer true only if nothing changes.",
    "outfit_or_look_change": "Does any character's outfit, hair colour or face change between the first and the last frame?",
    "scene_cut": "Does the scene, location or camera angle change abruptly between any two neighbouring frames, as in a film cut?",
    "camera_zoom": "Does the picture get noticeably closer or farther (a camera zoom or push-in) from the first to the last frame?",
    "object_appears_or_vanishes": "Does any object or character appear, disappear or change shape between frames?",
    "distorted": "Is any face, hand or body visibly distorted, melted or malformed in any frame?",
}


async def vlm_witness(clip: Clip, provider, repeats: int = 1) -> dict:
    """Ask the local VLM narrow yes/no questions about the contact sheet; each answer cites the timestamp it relies on. `repeats` > 1 asks again
    (temperature stays low, wording identical, only the order of questions is rotated) so unstable answers can be seen. Returns the raw answers:
    deciding what they prove is the caller's job (agree with a measurement, or be reported as suspected)."""
    import json

    sheet = contact_sheet(clip)
    schema = {"type": "object", "properties": {k: {"type": "object", "properties": {"answer": {"type": "boolean"}, "at_s": {"type": "string"}, "why": {"type": "string"}},
                                                  "required": ["answer", "at_s", "why"]} for k in VLM_QUESTIONS}, "required": list(VLM_QUESTIONS)}
    qs = list(VLM_QUESTIONS.items())
    runs = []
    for r in range(repeats):
        order = qs[r % len(qs):] + qs[:r % len(qs)]
        prompt = ("The image is a contact sheet: 8 frames from ONE video clip in time order (left to right, top to bottom), each labelled with its timestamp. "
                  "Answer every question from what is visible. For each give answer (true/false), the timestamp(s) you rely on, and one short reason.\n"
                  + "\n".join(f"- {k}: {q}" for k, q in order))
        raw = await provider.analyze_vision(sheet, prompt, system_prompt="You are a strict video QA inspector. Output only JSON.", format_schema=schema, max_tokens=2000)
        try:
            runs.append(json.loads(raw))
        except Exception:
            runs.append({"error": raw[:200]})
    return {"runs": runs}


if __name__ == "__main__":  # python -m engine.original.clip_eval clip.mp4 [any]  -> JSON report (measurements and flags)
    import json
    import sys

    print(json.dumps(evaluate(Path(sys.argv[1]), expect_camera=sys.argv[2] if len(sys.argv) > 2 else "static"), indent=1))
