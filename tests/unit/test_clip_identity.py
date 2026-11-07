"""Character presence / look check: the judging rules, with a fake VLM (no GPU, no Ollama)."""
import asyncio
import json
from pathlib import Path

import cv2
import numpy as np

from engine.original import clip_identity as ci


def _s(vis, match=True):
    return {"visible": vis, "match": match}


def test_agree_needs_both_witnesses():
    assert ci.agree([{"visible": True}, {"visible": True}], "visible") is True
    assert ci.agree([{"visible": False}, {"visible": False}], "visible") is False
    assert ci.agree([{"visible": True}, {"visible": False}], "visible") is None  # disagreement = unknown, never a verdict
    assert ci.agree([{"visible": True}, None], "visible") is None


def test_character_that_vanishes_is_flagged_suspected_with_time():
    times = [0.0, 0.6, 1.2, 1.8, 2.4, 3.0]
    flags, d = ci.judge("Pip", [_s(True), _s(True), _s(False, None), _s(False, None), _s(False, None), _s(False, None)], times)
    assert d["presence"] == "PP...." and [f["axis"] for f in flags] == ["object"] and flags[0]["status"] == "suspected" and flags[0]["t"] == 1.2


def test_a_character_who_was_never_there_or_stays_is_not_flagged():
    times = [0.0, 0.6, 1.2, 1.8]
    assert ci.judge("Pip", [_s(False, None)] * 4, times)[0] == []  # never visible: nothing vanished
    assert ci.judge("Mira", [_s(True)] * 4, times)[0] == []
    assert ci.judge("Mira", [_s(True), _s(None, None), _s(True), _s(None, None)], times)[0] == []  # unknowns are not absences


def test_one_absent_frame_out_of_many_is_tolerated_but_a_quarter_is_not():
    flags, _ = ci.judge("Mira", [_s(True)] * 4 + [_s(False, None)] + [_s(True)] * 4, [float(i) for i in range(9)])
    assert flags == []  # 1 of 8 later frames
    flags, _ = ci.judge("Mira", [_s(True), _s(True), _s(True), _s(False, None)], [0.0, 1.0, 2.0, 3.0])
    assert [f["axis"] for f in flags] == ["object"]  # 1 of 3 later frames is a quarter or more


def test_colour_answers_are_reported_but_never_flagged():
    times = [0.0, 0.6, 1.2, 1.8, 2.4, 3.0]
    flags, d = ci.judge("Mira", [_s(True), _s(True), _s(True, False), _s(True, False), _s(True, False), _s(True)], times)
    assert d["colours"] == "MMxxxM" and flags == []  # measured recall was 0 of 2, so the colour answer is not allowed to raise a flag


def test_check_runs_the_questions_per_frame_and_character(tmp_path):
    vw = cv2.VideoWriter(str(tmp_path / "c.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (64, 48))
    for i in range(30):
        vw.write(np.full((48, 64, 3), i * 8, np.uint8))
    vw.release()
    calls = []

    class Fake:
        async def analyze_vision(self, png, prompt, **kw):
            calls.append(prompt)
            return json.dumps({"visible": "Pip" not in prompt or len(calls) < 9, "colours_match": True, "note": "x"})

    r = asyncio.run(ci.check(tmp_path / "c.mp4", [("Mira", "red hair"), ("Pip", "white kit")], Fake(), frames=4))
    assert len(calls) == 2 * 2 * 4 and set(r["characters"]) == {"Mira", "Pip"} and r["characters"]["Mira"]["presence"] == "PPPP"


def test_objects_use_their_own_wording_and_the_same_judging(tmp_path):
    vw = cv2.VideoWriter(str(tmp_path / "o.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (64, 48))
    for i in range(30):
        vw.write(np.full((48, 64, 3), i * 8, np.uint8))
    vw.release()
    seen = []

    class Fake:
        async def analyze_vision(self, png, prompt, **kw):
            seen.append(prompt)
            gone = "white cup" in prompt and len(seen) > 4  # the cup disappears after the second sampled frame
            return json.dumps({"visible": not gone, "colours_match": True, "note": "x"})

    r = asyncio.run(ci.check(tmp_path / "o.mp4", [], Fake(), frames=4, objects=[("white cup", "a white ceramic cup")]))
    assert r["objects"]["white cup"]["presence"] == "PP.." and [f["axis"] for f in r["flags"]] == ["object"]
    assert all("object or thing" in p or "visible in the picture: white cup" in p for p in seen)

    class P:
        key_visuals = ["a glowing crystal", "a brass compass"]

    assert ci.shot_objects(P()) == [("a glowing crystal", "a glowing crystal"), ("a brass compass", "a brass compass")]


def test_counts_need_both_answers_and_flag_an_extra_only_from_a_quarter_of_frames():
    times = [0.0, 1.0, 2.0, 3.0]
    assert ci.judge_counts("cat", 1, [1, 1, 1, 1], times) == []
    assert ci.judge_counts("cat", 1, [1, None, 1, 1], times) == []  # unknown is not an extra
    f = ci.judge_counts("cat", 1, [1, 2, 3, 1], times)
    assert [x["axis"] for x in f] == ["object"] and f[0]["status"] == "suspected" and f[0]["t"] == 1.0 and "cats" in f[0]["evidence"]
    assert ci.judge_counts("woman", 1, [1, 1, 1, 1, 1, 1, 1, 2], list(range(8))) == []  # 1 of 8 agreed frames: tolerated
    assert [ci.plural(k) for k in ("woman", "man", "cat", "child", "sky-fox kit")] == ["women", "men", "cats", "children", "sky-fox kits"]


def test_count_check_asks_twice_without_the_expected_number(tmp_path):
    vw = cv2.VideoWriter(str(tmp_path / "c.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (64, 48))
    for i in range(30):
        vw.write(np.full((48, 64, 3), i * 8, np.uint8))
    vw.release()
    seen = []

    class Fake:
        async def analyze_vision(self, png, prompt, **kw):
            seen.append(prompt)
            return json.dumps({"count": 2})

    r = asyncio.run(ci.count_check(tmp_path / "c.mp4", {"cat": 1}, Fake(), frames=4))
    assert len(seen) == 8 and r["counts"]["cat"] == [2, 2, 2, 2] and [f["axis"] for f in r["flags"]] == ["object"]
    assert not any("1" in p.replace("{", "") and "expected" in p for p in seen)  # the prompt never says how many there should be
