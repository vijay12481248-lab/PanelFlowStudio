"""Clip evaluator: known camera moves, cuts, flicker and still pictures made synthetically, so the measurements are checked against ground truth."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from engine.original import clip_eval as ce

W, H, N = 384, 216, 48


def _scene() -> np.ndarray:
    rng = np.random.default_rng(3)
    img = cv2.GaussianBlur(rng.integers(0, 255, (H * 2, W * 2, 3), dtype=np.uint8), (0, 0), 2)
    for _ in range(40):
        cv2.circle(img, (int(rng.integers(0, W * 2)), int(rng.integers(0, H * 2))), int(rng.integers(6, 22)), [int(c) for c in rng.integers(0, 255, 3)], -1)
    return img


def _write(path: Path, frames: list) -> Path:
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24, (W, H))
    for f in frames:
        vw.write(f)
    vw.release()
    return path


def _view(scene: np.ndarray, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0) -> np.ndarray:
    """The central WxH window of the big scene, zoomed by `scale` about the window centre and shifted by (dx, dy) pixels."""
    m = np.array([[scale, 0, W / 2 - scale * W + dx], [0, scale, H / 2 - scale * H + dy]], np.float32)
    big = scene[H // 2: H // 2 + H, W // 2: W // 2 + W]
    return cv2.warpAffine(big, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _ev(path, **kw):
    return ce.evaluate(path, expect_audio=False, **kw)


def test_fixed_camera_has_no_camera_flag(tmp_path):
    s = _scene()
    r = _ev(_write(tmp_path / "fix.mp4", [_view(s)] * 2 + [_view(s)] * N))
    assert abs(r["camera"]["zoom_pct"]) < 1 and not [f for f in r["flags"] if f["axis"] == "camera"]


def test_push_in_is_measured_and_flagged_when_camera_must_be_static(tmp_path):
    s = _scene()
    r = _ev(_write(tmp_path / "zoom.mp4", [_view(s, 1 + 0.12 * i / (N - 1)) for i in range(N)]))
    assert r["camera"]["zoom_pct"] == pytest.approx(12, abs=2)
    assert any(f["axis"] == "camera" and f["status"] == "confirmed" for f in r["flags"])
    assert not _ev(tmp_path / "zoom.mp4", expect_camera="any")["flags"] or all(f["axis"] != "camera" for f in _ev(tmp_path / "zoom.mp4", expect_camera="any")["flags"])


def test_pan_is_measured(tmp_path):
    s = _scene()
    r = _ev(_write(tmp_path / "pan.mp4", [_view(s, 1.0, dx=-0.15 * W * i / (N - 1)) for i in range(N)]))
    assert r["camera"]["pan_x_pct"] == pytest.approx(-15, abs=3) and abs(r["camera"]["zoom_pct"]) < 2


def test_subject_motion_alone_is_not_a_camera_move(tmp_path):
    s = _scene()
    frames = []
    for i in range(N):
        f = _view(s).copy()
        cv2.circle(f, (110 + 3 * i, 108), 30, (0, 0, 255), -1)  # a moving subject on a fixed background
        frames.append(f)
    r = _ev(_write(tmp_path / "subj.mp4", frames))
    assert abs(r["camera"]["zoom_pct"]) < 2 and not [f for f in r["flags"] if f["axis"] == "camera"]


def test_hard_cut_is_confirmed_with_time(tmp_path):
    s = _scene()
    other = np.roll(s, 300, axis=1) // 4  # a different, darker picture, as in a film cut
    frames = [_view(s)] * 20 + [_view(other)] * 20
    r = _ev(_write(tmp_path / "cut.mp4", frames))
    assert r["cuts_s"] and r["cuts_s"][0] == pytest.approx(20 / 24, abs=0.1)
    assert any(f["axis"] == "temporal" and f["status"] == "confirmed" for f in r["flags"])


def test_still_picture_is_flagged(tmp_path):
    r = _ev(_write(tmp_path / "still.mp4", [_view(_scene())] * N))
    assert any(f["axis"] == "motion" for f in r["flags"])


def test_flicker_is_measured(tmp_path):
    s = _scene()
    frames = [cv2.convertScaleAbs(_view(s), alpha=1.0, beta=(25 if i % 2 else 0)) for i in range(N)]
    steady = _ev(_write(tmp_path / "steady.mp4", [_view(s)] * N))["flicker"]
    assert _ev(_write(tmp_path / "flick.mp4", frames))["flicker"] > 10 * max(steady, 0.05)


def test_appearance_drift_triggers_on_colour_change(tmp_path):
    s = _scene()
    frames = [cv2.addWeighted(_view(s), 1 - i / (N - 1), np.full((H, W, 3), (200, 40, 40), np.uint8), i / (N - 1), 0) for i in range(N)]
    r = _ev(_write(tmp_path / "drift.mp4", frames))
    assert r["drift"]["max"] > ce.DRIFT_HIST


def test_contact_sheet_is_a_png_with_all_samples(tmp_path):
    clip = ce.load_clip(_write(tmp_path / "c.mp4", [_view(_scene())] * N))
    sheet = cv2.imdecode(np.frombuffer(ce.contact_sheet(clip), np.uint8), cv2.IMREAD_COLOR)
    assert sheet.shape[:2] == (H * 2, W * 4)


def test_too_short_clip_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ce.load_clip(_write(tmp_path / "one.mp4", [_view(_scene())]))


def test_a_planned_cut_is_not_a_defect_but_an_unplanned_one_is_and_each_shot_is_measured_alone(tmp_path):
    a, b = _scene(), np.roll(_scene(), 300, axis=1) // 4
    frames = [_view(a)] * 40 + [_view(b, 1 + 0.15 * i / 39) for i in range(40)]  # shot 2 zooms 15%; shot 1 is steady; the cut is at 40/24 s
    path = _write(tmp_path / "take.mp4", frames)
    plain = ce.evaluate(path, expect_audio=False)
    assert any(f["axis"] == "temporal" and f["status"] == "confirmed" for f in plain["flags"])  # without the plan the cut is a defect
    planned = ce.evaluate(path, expect_audio=False, planned_cuts=[40 / 24])
    assert not any(f["axis"] == "temporal" for f in planned["flags"]) and planned["cuts_s"] == []
    cam = [f for f in planned["flags"] if f["axis"] == "camera"]
    assert cam and all("[shot 2" in f["evidence"] for f in cam) and len(planned["segments"]) == 2  # only shot 2 zooms
    c = np.roll(_scene(), 150, axis=0) // 2
    stray = _write(tmp_path / "stray.mp4", [_view(a)] * 14 + [_view(c)] * 70 + [_view(b)] * 36)  # a stray cut at 14/24 s, the planned one at 84/24 s
    other = ce.evaluate(stray, expect_audio=False, planned_cuts=[84 / 24])
    assert any(f["axis"] == "temporal" and f["status"] == "confirmed" and f["t"] < 1.5 for f in other["flags"])  # a cut that is NOT near where the plan put one


def test_a_planned_cut_that_lands_a_little_early_is_still_planned(tmp_path):
    a, b = _scene(), np.roll(_scene(), 300, axis=1) // 4
    path = _write(tmp_path / "early.mp4", [_view(a)] * 36 + [_view(b)] * 44)  # the cut is at 1.5 s; the plan said 1.9 s
    r = ce.evaluate(path, expect_audio=False, planned_cuts=[1.9])
    assert not any(f["axis"] == "temporal" for f in r["flags"]) and r["cut_deviation_s"] and abs(r["cut_deviation_s"][0] + 0.4) < 0.1
