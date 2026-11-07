"""Boundary check between consecutive clips: measurements always, flags only for a boundary declared continuous."""
import cv2
import numpy as np

from engine.original import continuity as ct

W, H = 384, 216


def _clip(path, frames):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24, (W, H))
    for f in frames:
        vw.write(f)
    vw.release()
    return path


def _scene(seed):
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.integers(0, 255, (H, W, 3), dtype=np.uint8), (0, 0), 2)
    for _ in range(12):
        cv2.circle(img, (int(rng.integers(0, W)), int(rng.integers(0, H))), int(rng.integers(10, 40)), [int(c) for c in rng.integers(0, 255, 3)], -1)
    return img


def test_a_true_continuation_passes_and_an_unrelated_next_clip_is_flagged(tmp_path):
    a, b = _scene(1), _scene(2)
    first = _clip(tmp_path / "a.mp4", [a] * 20)
    cont = _clip(tmp_path / "b.mp4", [a] * 20)  # starts exactly where the first ended
    other = _clip(tmp_path / "c.mp4", [b] * 20)
    ok = ct.boundary(first, cont, continuous=True)
    assert ok["flags"] == [] and ok["hist_distance"] < 0.05 and ok["gray_diff"] < 5
    bad = ct.boundary(first, other, continuous=True)
    assert [f["axis"] for f in bad["flags"]] == ["temporal"] and bad["flags"][0]["status"] == "suspected"


def test_a_normal_cut_is_measured_but_never_flagged(tmp_path):
    first = _clip(tmp_path / "a.mp4", [_scene(1)] * 20)
    other = _clip(tmp_path / "c.mp4", [_scene(2)] * 20)
    r = ct.boundary(first, other)  # continuous defaults to False: a cut is a cut
    assert r["flags"] == [] and r["hist_distance"] > 0.2


def test_chain_reports_every_pair(tmp_path):
    clips = [_clip(tmp_path / f"{i}.mp4", [_scene(i % 2)] * 10) for i in range(4)]
    r = ct.chain(clips)
    assert len(r) == 3 and [bool(x["flags"]) for x in r] == [True, True, True]
