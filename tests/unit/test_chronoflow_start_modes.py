"""Start modes for the ChronoFlow "New Video" wizard: slot table, segment count, plan builder, missing-input check."""
import pytest

from engine.chronoflow import start_modes as sm


def test_segment_count_rounds_and_clamps():
    assert sm.segment_count(300) == 58
    assert sm.segment_count(15) == 3
    assert sm.segment_count(1) == 1
    for bad in (0, 5000, -3):
        with pytest.raises(ValueError):
            sm.segment_count(bad)


def test_slots_for_each_mode():
    assert sm.START_MODES == ("text", "first", "first_last", "last", "reference", "from_video")
    assert sm.slots_for("text") == ()
    assert sm.slots_for("first") == ("first",)
    assert sm.slots_for("from_video") == ("first",)
    assert sm.slots_for("first_last") == ("first", "last")
    assert sm.slots_for("last") == ("last",)
    assert sm.slots_for("reference") == ("ref1", "ref2")
    with pytest.raises(ValueError):
        sm.slots_for("sideways")


def test_build_plan_five_minutes():
    plan = sm.build_plan("first_last", 300, "Five minutes")
    scenes = plan["scenes"]
    assert plan["title"] == "Five minutes" and len(scenes) == 58
    assert [s["shot_index"] for s in scenes] == list(range(1, 59))
    assert scenes[0]["inherits_tail"] is False and scenes[1]["inherits_tail"] is False  # first_last carries its own keyframes
    assert all(s["start_mode"] == "first_last" and s["state"] == "empty" and s["approved"] is False for s in scenes)
    assert abs(sum(s["duration"] for s in scenes) - 300) < 5.2
    assert scenes[-1]["duration"] >= 1.0


def test_first_mode_plan_chains_after_the_first_card():
    scenes = sm.build_plan("first", 15)["scenes"]
    assert [s["inherits_tail"] for s in scenes] == [False, True, True]


def test_text_plan_continues_from_tail():
    scenes = sm.build_plan("text", 15)["scenes"]
    assert sm.effective_mode(scenes[0], 0) == "text"
    assert sm.effective_mode(scenes[1], 1) == "first"
    assert sm.effective_mode(scenes[2], 2) == "first"


def test_missing_inputs_names_slots():
    s = sm.build_plan("first_last", 15)["scenes"][0]
    s["prompt"] = "a door opens"
    s["first_frame"] = "a.png"
    assert sm.missing_inputs(s, 0) == ["last"]
    r = sm.build_plan("reference", 15)["scenes"][0]
    r["prompt"] = "x"
    assert sm.missing_inputs(r, 0) == ["ref1"]
    r["ref_images"] = ["one.png"]
    assert sm.missing_inputs(r, 0) == []  # the second reference is optional
    assert "prompt" in sm.missing_inputs(sm.build_plan("text", 15)["scenes"][0], 0)
    chained = sm.build_plan("first", 15)["scenes"][1]
    chained["prompt"] = "x"
    assert sm.missing_inputs(chained, 1) == []  # the tail frame is supplied at render time
    head = sm.build_plan("from_video", 15)["scenes"][0]
    head["prompt"] = "x"
    assert sm.missing_inputs(head, 0) == ["first"]  # no video picked yet
