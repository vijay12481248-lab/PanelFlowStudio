"""Correction loop: levers, keep-best, history, stop conditions - with a fake generator and synthetic clips (known camera moves), no GPU."""
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from engine.original import clip_loop as cl

W, H, N = 384, 216, 48


def _scene():
    rng = np.random.default_rng(3)
    img = cv2.GaussianBlur(rng.integers(0, 255, (H * 2, W * 2, 3), dtype=np.uint8), (0, 0), 2)
    for _ in range(40):
        cv2.circle(img, (int(rng.integers(0, W * 2)), int(rng.integers(0, H * 2))), int(rng.integers(6, 22)), [int(c) for c in rng.integers(0, 255, 3)], -1)
    return img


def _view(s, scale=1.0):
    m = np.array([[scale, 0, W / 2 - scale * W], [0, scale, H / 2 - scale * H]], np.float32)
    return cv2.warpAffine(s[H // 2: H // 2 + H, W // 2: W // 2 + W], m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _write(path, frames):
    path.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24, (W, H))
    for f in frames:
        vw.write(f)
    vw.release()
    return path


def _clips(tmp):
    s = _scene()
    zoom = _write(tmp / "zoom.mp4", [_view(s, 1 + 0.12 * i / (N - 1)) for i in range(N)])
    steady = _write(tmp / "steady.mp4", [_view(s, 1 + 0.002 * (i % 2)) for i in range(N)])  # fixed camera with a little life in it
    cut = _write(tmp / "cut.mp4", [_view(s)] * 20 + [np.roll(s, 300, axis=1)[H // 2: H // 2 + H, W // 2: W // 2 + W] // 4] * 28)
    return zoom, steady, cut


def _ws(tmp, baseline):
    ws = tmp / "ws"
    (ws / "film" / "clips").mkdir(parents=True)
    shutil.copy2(baseline, ws / "film" / "clips" / "p001.mp4")
    return ws


def _run(ws, gen, **kw):
    return cl.improve_clip("p001", ws, gen, {"seed": 7, "static_camera": False, "native_voice": False}, expect_audio=False, **kw)


def test_static_camera_lever_fixes_zoom_and_is_kept(tmp_path):
    zoom, steady, _ = _clips(tmp_path)
    ws = _ws(tmp_path, zoom)
    calls = []
    out = _run(ws, lambda work, s: calls.append(dict(s)) or (steady if s["static_camera"] else zoom))
    assert out["stopped"].startswith("no confirmed defect left") and not out["defects_left"]
    assert calls == [{"seed": 7, "static_camera": True, "native_voice": False}]  # exactly one input changed
    assert [h["decision"] for h in out["history"]] == ["baseline", "kept"]
    assert json.loads((ws / "film" / "history" / "p001.json").read_text())[1]["lever"] == "static_camera"


def test_real_clip_only_replaced_when_applied(tmp_path):
    zoom, steady, _ = _clips(tmp_path)
    ws = _ws(tmp_path, zoom)
    before = (ws / "film" / "clips" / "p001.mp4").read_bytes()
    _run(ws, lambda w, s: steady)
    assert (ws / "film" / "clips" / "p001.mp4").read_bytes() == before
    ws2 = _ws(tmp_path / "b", zoom)
    assert _run(ws2, lambda w, s: steady, apply=True)["applied"] and (ws2 / "film" / "clips" / "p001.mp4").read_bytes() != before


def test_worse_result_is_discarded_and_next_lever_tried(tmp_path):
    zoom, steady, cut = _clips(tmp_path)
    ws = _ws(tmp_path, zoom)

    def gen(work, s):
        return cut if s["static_camera"] else steady  # static_camera makes it worse (new cut), the seed lever fixes it

    out = _run(ws, gen)
    dec = [(h["lever"], h["decision"]) for h in out["history"]]
    assert dec == [(None, "baseline"), ("static_camera", "discarded"), ("seed", "kept")]
    assert "worst defect camera -> temporal" in out["history"][1]["reason"]
    assert out["settings"]["static_camera"] is False and out["settings"]["seed"] != 7


def test_budget_and_seeds_are_reproducible(tmp_path):
    zoom, _, _ = _clips(tmp_path)
    seeds = []
    out = _run(_ws(tmp_path / "a", zoom), lambda w, s: seeds.append(s["seed"]) or zoom, attempts=3)
    assert out["stopped"] == "no lever left for the remaining defect" or out["stopped"] == "attempts used up"
    assert len(out["history"]) <= 4 and len(set(seeds)) == len(seeds)
    seeds2 = []
    _run(_ws(tmp_path / "b", zoom), lambda w, s: seeds2.append(s["seed"]) or zoom, attempts=3)
    assert seeds == seeds2


def test_defect_without_lever_is_reported_not_hidden(tmp_path):
    zoom, steady, _ = _clips(tmp_path)  # these clips have no audio stream, so with expect_audio the defect is `audio`, which has no lever
    ws = _ws(tmp_path, steady)
    out = cl.improve_clip("p001", ws, lambda w, s: steady, {"seed": 1, "static_camera": False, "native_voice": False}, expect_audio=True)
    assert out["stopped"] == "no lever left for the remaining defect" and out["defects_left"] == ["audio (confirmed)"] and len(out["history"]) == 1


def test_suspected_flags_are_not_acted_on_by_default(tmp_path):
    rep = {"flags": [{"axis": "consistency", "status": "suspected"}]}
    assert cl.defects(rep) == [] and len(cl.defects(rep, act_on_suspected=True)) == 1
    assert cl.next_lever(rep, {"static_camera": False}, set(), True) == ("seed", "consistency")


def test_severity_order_and_static_not_repeated():
    rep = {"flags": [{"axis": "artifacts", "status": "confirmed"}, {"axis": "camera", "status": "confirmed"}, {"axis": "temporal", "status": "confirmed"}]}
    assert [f["axis"] for f in cl.defects(rep)] == ["temporal", "camera", "artifacts"]
    assert cl.next_lever(rep, {"static_camera": True}, set(), False) == ("seed", "temporal")


def test_smaller_defect_of_the_same_kind_is_kept_but_marginal_change_is_not(tmp_path):
    s = _scene()
    big = _write(tmp_path / "big.mp4", [_view(s, 1 + 0.20 * i / (N - 1)) for i in range(N)])
    small = _write(tmp_path / "small.mp4", [_view(s, 1 + 0.05 * i / (N - 1)) for i in range(N)])
    ev = lambda p: cl.evaluate(p, "static", expect_audio=False)  # noqa: E731
    assert cl.better(ev(small), ev(big))[0] and not cl.better(ev(big), ev(small))[0]
    assert not cl.better(ev(big), ev(big))[0]


def test_fixing_the_worse_defect_beats_adding_a_minor_one(tmp_path):
    zoom, _, cut = _clips(tmp_path)
    ev = lambda p: cl.evaluate(p, "static", expect_audio=False)  # noqa: E731
    ok, why = cl.better(ev(zoom), ev(cut))  # a hard cut (severe) replaced by a zoom (less severe)
    assert ok and "temporal -> camera" in why


def _rep(flags, zoom=0.0, drift=0.05):
    return {"flags": [{"axis": a, "status": st} for a, st in flags], "camera": {"zoom_pct": zoom, "pan_x_pct": 0, "pan_y_pct": 0}, "drift": {"max": drift},
            "flicker": 0.1, "motion": 2.0, "cuts_s": []}


def test_tie_on_the_worst_defect_falls_through_to_the_next(tmp_path):
    best = _rep([("consistency", "suspected"), ("camera", "confirmed")], zoom=19.9, drift=0.60)
    new = _rep([("consistency", "suspected"), ("camera", "confirmed")], zoom=3.3, drift=0.64)
    ok, why = cl.better(new, best, act_on_suspected=True)
    assert ok and why.startswith("camera 19.90 -> 3.30")  # drift is a tie, the zoom is much smaller
    assert not cl.better(best, new, act_on_suspected=True)[0]


def test_remaining_suspected_flags_are_reported_not_called_fixed(tmp_path):
    s = _scene()
    zoom = _write(tmp_path / "z.mp4", [_view(s, 1 + 0.12 * i / (N - 1)) for i in range(N)])
    still = _write(tmp_path / "still.mp4", [_view(s)] * N)  # no confirmed defect, but a suspected "reads as a still"
    out = _run(_ws(tmp_path, zoom), lambda w, sset: still)
    assert out["stopped"].startswith("no confirmed defect left") and "SUSPECTED" in out["stopped"] and out["needs_look"]


def test_lost_picture_is_a_suspected_transition_but_a_single_cut_is_not_double_counted(tmp_path):
    from engine.original import clip_eval as ce

    s = _scene()
    m = lambda dx: cv2.warpAffine(s[H // 2: H // 2 + H, W // 2: W // 2 + W], np.float32([[1, 0, dx], [0, 1, 0]]), (W, H), borderMode=cv2.BORDER_REFLECT)  # noqa: E731
    whip = [m(0)] * 15 + [m(90 * i) for i in range(1, 13)] + [m(90 * 12)] * 15  # a violent whip: the tracker loses the picture, the steps are not hard cuts
    r = ce.evaluate(_write(tmp_path / "whip.mp4", whip), expect_audio=False)
    assert any(f["axis"] == "temporal" and f["status"] == "suspected" for f in r["flags"]) and not r["cuts_s"]
    cut = ce.evaluate(_write(tmp_path / "cut.mp4", [_view(s)] * 20 + [np.roll(s, 300, axis=1)[H // 2: H // 2 + H, W // 2: W // 2 + W] // 4] * 28), expect_audio=False)
    assert [f["status"] for f in cut["flags"] if f["axis"] == "temporal"] == ["confirmed"]


# ---------------------------------------------------------------- levers: simplify_action, redraw_frame
def test_simplify_motion_rules():
    t = "they walk up the path, Mira laughing, Rook scowling, the blue light growing"
    assert cl.simplify_motion(t, "consistency") == "they walk up the path, Mira laughing, Rook scowling"  # only the light clause goes
    assert cl.simplify_motion(t, "temporal") == "they walk up the path"  # the first clause is the main action
    assert cl.simplify_motion("she waves", "temporal") is None and cl.simplify_motion("she waves", "consistency") is None
    assert cl.simplify_motion("a quiet room, a clock ticks", "consistency") is None  # no light clause: nothing to cut


def test_lever_order_availability_and_one_input_changed():
    rep = {"flags": [{"axis": "consistency", "status": "suspected"}]}
    s = {"seed": 5, "static_camera": False, "motion": "they walk, Mira laughing, the light growing", "frame_attempt": 0, "frame_shot": "medium"}
    assert cl.next_lever(rep, s, set(), True) == ("simplify_action", "consistency")
    assert cl.next_lever(rep, s, {("simplify_action", "consistency")}, True) == ("seed", "consistency")  # redraw not available without a runner
    avail = cl.DEFAULT_LEVERS | cl.FRAME_LEVERS
    assert cl.next_lever(rep, s, {("simplify_action", "consistency")}, True, avail) == ("redraw_frame", "consistency")
    for lever in ("static_camera", "simplify_action", "redraw_frame", "widen_frame", "seed"):
        new = cl.apply_lever(lever, s, 1, "consistency")
        assert len([k for k in new if new[k] != s[k]]) == 1, lever
    assert cl.next_lever(rep, {**s, "motion": "she waves"}, set(), True) == ("seed", "consistency")  # nothing to simplify -> next lever


def test_film_generate_applies_motion_and_redraws_only_when_asked(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("dg", Path(__file__).resolve().parents[2] / "stories" / "dawn_gate_source.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    story = mod.story
    sid = story.panels[0].id
    ws = tmp_path / "ws"
    (ws / "film" / "frames").mkdir(parents=True)
    (ws / "film" / "frames" / f"{sid}.png").write_bytes(b"orig")
    seen = {}

    def fake_clips(st, work, ids, seeds, native_voice, camera):
        seen["motion"] = next(p.motion for p in st.panels if p.id == sid)
        seen["camera"] = camera
        out = work / "film" / "clips" / f"{sid}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"clip")
        return {"failed": []}

    def fake_frames(st, work, runner, ids, rerolls):
        seen["rerolls"] = rerolls
        seen["frame_shot"] = next(p.shot for p in st.panels if p.id == ids[0])
        (work / "film" / "frames" / f"{ids[0]}.png").write_bytes(b"new")

    monkeypatch.setattr(cl.film, "make_clips", fake_clips)
    monkeypatch.setattr(cl.film, "make_frames", fake_frames)
    base = {"seed": 1, "static_camera": False, "native_voice": False, "motion": story.panels[0].motion, "frame_attempt": 0, "frame_shot": story.panels[0].shot}
    gen = cl.film_generate(story, ws, sid, runner=object(), baseline=base)
    gen(tmp_path / "w1", base)
    assert (tmp_path / "w1" / "film" / "frames" / f"{sid}.png").read_bytes() == b"orig" and "rerolls" not in seen and seen["motion"] == story.panels[0].motion
    gen(tmp_path / "w2", {**base, "motion": "just this", "frame_attempt": 1, "static_camera": True})
    assert seen["motion"] == "just this" and seen["rerolls"] == {sid: 1} and seen["camera"] == cl.STATIC_CAMERA
    assert (tmp_path / "w2" / "film" / "frames" / f"{sid}.png").read_bytes() == b"new"
    assert story.panels[0].motion != "just this"  # the real story object is untouched
    import pytest as _p

    with _p.raises(RuntimeError):
        cl.film_generate(story, ws, sid, runner=None, baseline=base)(tmp_path / "w3", {**base, "frame_attempt": 2})


def test_widen_frame_changes_only_the_first_frame_shot_size(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("dg", Path(__file__).resolve().parents[2] / "stories" / "dawn_gate_source.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    story = mod.story
    panel = next(p for p in story.panels if p.shot in ("close", "medium"))
    sid, wider = panel.id, cl.widen(panel.shot)
    ws = tmp_path / "ws"
    (ws / "film" / "frames").mkdir(parents=True)
    (ws / "film" / "frames" / f"{sid}.png").write_bytes(b"orig")
    seen = {}

    def fake_clips(st, work, ids, seeds, native_voice, camera):
        seen["clip_shot"] = next(p.shot for p in st.panels if p.id == sid)
        out = work / "film" / "clips" / f"{sid}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"clip")
        return {"failed": []}

    def fake_frames(st, work, runner, ids, rerolls):
        seen["frame_shot"] = next(p.shot for p in st.panels if p.id == sid)
        (work / "film" / "frames" / f"{sid}.png").write_bytes(b"wide")

    monkeypatch.setattr(cl.film, "make_clips", fake_clips)
    monkeypatch.setattr(cl.film, "make_frames", fake_frames)
    base = {"seed": 1, "static_camera": False, "native_voice": False, "motion": panel.motion, "frame_attempt": 0, "frame_shot": panel.shot}
    cl.film_generate(story, ws, sid, runner=object(), baseline=base)(tmp_path / "w", cl.apply_lever("widen_frame", base, 1))
    assert seen["frame_shot"] == wider and seen["clip_shot"] == panel.shot  # the frame is wider, the clip keeps the shot's own size and length
    assert cl.widen("wide") is None and cl.widen(None) is None and cl.widen("extreme_close") == "close"
    rep = {"flags": [{"axis": "temporal", "status": "confirmed"}]}
    order = []
    s = {**base, "static_camera": True}
    tried = set()
    while (pick := cl.next_lever(rep, s, tried, False, cl.DEFAULT_LEVERS | cl.FRAME_LEVERS)) and len(order) < 6:
        order.append(pick[0])
        tried.add(pick)
    assert order[0] == "widen_frame" and len(order) == len(set(order)) and order[-1] == "seed"  # temporal: static is done, so widen comes first, seed last
