"""The stop points: the decisions the workflow pauses for."""
import json

from engine.narration.artifacts import Beat, BeatSheet, Scene, StopPoint
from engine.narration.casting import CastPlan, resolve_cast
from engine.narration.runtime.roles import VoiceProfile
from engine.narration.stoppoints import (
    add_stop_point, load_stop_points, open_stop_points, resolve_stop_point, save_stop_points,
)
from engine.narration.steps.understand import uncertain_beats


CATALOG = [
    VoiceProfile(id="narrator", name="The Narrator", voice="am_michael", gender="male"),
    VoiceProfile(id="aria", name="Aria", voice="af_heart", gender="female"),
    VoiceProfile(id="adam", name="Adam", voice="am_adam", gender="male"),
]


def _bible(*chars):
    from engine.narration.artifacts import BibleCharacter, SeriesBible
    return SeriesBible(series_key="s", characters=[BibleCharacter(id=cid, name=nm, pronouns=p)
                                                   for cid, nm, p in chars])


def test_a_stop_point_is_recorded_and_waiting(tmp_path):
    add_stop_point(tmp_path, StopPoint(kind="brief", detail="the speaker of P4 is unclear",
                                       line_ids=["P4"], options=["accept as read", "edit the beat"]))
    waiting = open_stop_points(tmp_path)
    assert len(waiting) == 1
    assert waiting[0].kind == "brief" and waiting[0].line_ids == ["P4"]
    assert waiting[0].options == ["accept as read", "edit the beat"]


def test_the_same_stop_point_is_not_recorded_twice(tmp_path):
    point = StopPoint(kind="brief", detail="the speaker of P4 is unclear")
    add_stop_point(tmp_path, point)
    add_stop_point(tmp_path, point)
    assert len(open_stop_points(tmp_path)) == 1


def test_answering_a_stop_point_settles_it(tmp_path):
    add_stop_point(tmp_path, StopPoint(kind="brief", detail="the speaker of P4 is unclear"))
    remaining = resolve_stop_point(tmp_path, "brief", "accept as read")
    assert remaining == []
    assert open_stop_points(tmp_path) == []
    # the answer is kept with the point
    assert load_stop_points(tmp_path)[0].resolution == "accept as read"


def test_answering_one_stop_point_leaves_the_others(tmp_path):
    add_stop_point(tmp_path, StopPoint(kind="brief", detail="the speaker of P4 is unclear"))
    add_stop_point(tmp_path, StopPoint(kind="voice", detail="Kai has no voice yet"))
    remaining = resolve_stop_point(tmp_path, "brief", "accept as read")
    assert [p.kind for p in remaining] == ["voice"]


def test_a_corrupt_stop_point_file_is_ignored(tmp_path):
    (tmp_path / "stop_points.json").write_text("{not json", encoding="utf-8")
    assert load_stop_points(tmp_path) == []


def test_a_beat_the_analyst_is_unsure_about_is_a_stop_point():
    sheet = BeatSheet(project_id="p", scenes=[Scene(
        scene_id="s1", first_panel_id="P1", last_panel_id="P4", goal="g", conflict="c", turn="t",
        beats=[Beat(beat_id="s1b0", panel_ids=["P1", "P2"], what_happens="w", function="setup", intensity=0.5,
                    confidence=0.9),
               Beat(beat_id="s1b1", panel_ids=["P3", "P4"], what_happens="w", function="reveal", intensity=0.8,
                    confidence=0.4)])], hook="h", chapter_summary="s")
    unsure = uncertain_beats(sheet)
    assert [b.beat_id for b in unsure] == ["s1b1"]


def test_a_beat_that_says_what_it_is_unsure_about_is_a_stop_point():
    sheet = BeatSheet(project_id="p", scenes=[Scene(
        scene_id="s1", first_panel_id="P1", last_panel_id="P2", goal="g", conflict="c", turn="t",
        beats=[Beat(beat_id="s1b0", panel_ids=["P1", "P2"], what_happens="w", function="setup", intensity=0.5,
                    confidence=0.9, uncertain="the speaker of P2 is not clear")])], hook="h", chapter_summary="s")
    assert [b.beat_id for b in uncertain_beats(sheet)] == ["s1b0"]


def test_a_sure_beat_is_not_a_stop_point():
    sheet = BeatSheet(project_id="p", scenes=[Scene(
        scene_id="s1", first_panel_id="P1", last_panel_id="P2", goal="g", conflict="c", turn="t",
        beats=[Beat(beat_id="s1b0", panel_ids=["P1", "P2"], what_happens="w", function="setup", intensity=0.5,
                    confidence=0.95)])], hook="h", chapter_summary="s")
    assert uncertain_beats(sheet) == []


def test_a_voice_that_would_replace_an_assignment_is_offered_not_applied():
    """The owner cast Kai to a voice; a better fit is a change they must approve."""
    bible = _bible(("c1", "Kai", "she"))
    plan = resolve_cast("s", bible, ["c1"], CATALOG, {"c1": "adam"})
    assert [(a.character_id, a.profile_id, a.source) for a in plan.assignments] == [("c1", "adam", "assigned")]
    assert [(c.character_id, c.profile_id, c.source) for c in plan.changes] == [("c1", "aria", "change")]


def test_a_character_with_no_voice_gets_a_recommendation_not_a_change():
    bible = _bible(("c1", "Kai", "she"))
    plan = resolve_cast("s", bible, ["c1"], CATALOG, {})
    assert plan.changes == []
    assert [r.source for r in plan.recommendations] == ["recommended"]
