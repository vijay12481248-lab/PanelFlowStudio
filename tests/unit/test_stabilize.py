"""Stabilisation: a drifting background is held still (checked with the area-weighted estimator), a steady clip and a huge drift are left alone, sound is kept."""
import subprocess

import cv2
import numpy as np
import pytest

from engine.original import clip_eval as ce
from engine.original import stabilize as st

W, H, N = 384, 216, 60


def _scene():
    rng = np.random.default_rng(3)
    img = cv2.GaussianBlur(rng.integers(0, 255, (H * 2, W * 2, 3), dtype=np.uint8), (0, 0), 2)
    for _ in range(40):
        cv2.circle(img, (int(rng.integers(0, W * 2)), int(rng.integers(0, H * 2))), int(rng.integers(6, 22)), [int(c) for c in rng.integers(0, 255, 3)], -1)
    return img


def _clip(path, scale_end=1.0, dx_end=0.0, with_audio=True):
    s = _scene()
    raw = path.with_suffix(".raw.mp4")
    vw = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), 24, (W, H))
    for i in range(N):
        t = i / (N - 1)
        sc, dx = 1 + (scale_end - 1) * t, dx_end * t
        m = np.array([[sc, 0, W / 2 - sc * W + dx], [0, sc, H / 2 - sc * H]], np.float32)
        vw.write(cv2.warpAffine(s[H // 2: H // 2 + H, W // 2: W // 2 + W], m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT))
    vw.release()
    args = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw)] + (["-f", "lavfi", "-i", "sine=frequency=440:duration=3"] if with_audio else []) + ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if with_audio else []) + [str(path)]
    subprocess.run(args, check=True)
    return path


def _area(p):
    return ce.camera_motion_area(ce.load_clip(p).gray)


def test_a_small_pan_and_zoom_drift_is_removed_and_the_sound_is_kept(tmp_path):
    src = _clip(tmp_path / "drift.mp4", scale_end=1.06, dx_end=-0.08 * W)
    before = _area(src)
    assert abs(before["zoom_pct"]) > 4 and abs(before["pan_x_pct"]) > 5
    r = st.stabilize(src, tmp_path / "steady.mp4")
    assert r["applied"] and 5 < r["drift_pct"] < 12
    after = _area(tmp_path / "steady.mp4")
    assert abs(after["zoom_pct"]) < 2 and abs(after["pan_x_pct"]) < 2  # the framing is held
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(tmp_path / "steady.mp4")], capture_output=True, text=True).stdout
    assert "audio" in probe and "video" in probe


def test_a_steady_clip_and_a_huge_drift_are_left_alone(tmp_path):
    steady = _clip(tmp_path / "s.mp4")
    r = st.stabilize(steady, tmp_path / "s2.mp4")
    assert r["applied"] is False and r["reason"] == "already steady" and not (tmp_path / "s2.mp4").exists()
    big = _clip(tmp_path / "b.mp4", scale_end=1.4)
    r = st.stabilize(big, tmp_path / "b2.mp4")
    assert r["applied"] is False and "redraw" in r["reason"] and not (tmp_path / "b2.mp4").exists()
