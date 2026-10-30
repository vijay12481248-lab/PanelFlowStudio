import pytest
from pydantic import ValidationError

from engine.narration.artifacts import (
    ArtifactIdError, Beat, OcrDialogue, PanelFacts, SeriesBible, assert_known_ids,
)


def test_panel_facts_round_trip():
    facts = PanelFacts(panel_id="p1", order=1, is_story=True, shot="close", characters_visible=["c1", "unknown_1"],
                       unknown_cues={"unknown_1": "masked man"}, action="Yulin draws his sword.", emotion="anger",
                       dialogue=[OcrDialogue(region_id="r1", text="You dare?", speaker_id="c1", speaker_confidence=0.8)],
                       importance=4, confidence=0.9)
    assert PanelFacts.model_validate_json(facts.model_dump_json()) == facts


def test_action_longer_than_20_words_is_rejected():
    with pytest.raises(ValidationError):
        PanelFacts(panel_id="p", order=1, is_story=True, shot="wide", action=" ".join(["word"] * 21),
                   emotion="calm", importance=1, confidence=0.5)


def test_plot_so_far_capped_at_150_words():
    with pytest.raises(ValidationError):
        SeriesBible(series_key="s", plot_so_far=" ".join(["w"] * 151))


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        Beat(beat_id="b", panel_ids=["p"], what_happens="x", function="setup", intensity=0.5, made_up=1)


def test_assert_known_ids_names_every_unknown():
    with pytest.raises(ArtifactIdError, match=r"scene s1.*p9.*p10"):
        assert_known_ids(["p1", "p9", "p10"], {"p1"}, "scene s1")


from engine.narration.artifacts import (
    LineCheck, LineCritique, ScriptIR, ScriptLine, check_script_ids,
)


def _line(pid, lid=None, **kw):
    return ScriptLine(line_id=lid or f"l_{pid}", panel_id=pid, text="He draws.", facts_used=["action"],
                      kind="narration", **kw)


def test_script_line_rejects_bad_fact_ref():
    with pytest.raises(ValidationError):
        ScriptLine(line_id="l1", panel_id="a", text="x", facts_used=["vibes"], kind="narration")
    with pytest.raises(ValidationError):
        ScriptLine(line_id="l1", panel_id="a", text="  ", facts_used=[], kind="narration")
    ScriptLine(line_id="l1", panel_id="a", text="x", facts_used=["beat:b_1", "dialogue"], kind="hook")


def test_script_ir_rejects_duplicate_line_ids():
    with pytest.raises(ValidationError):
        ScriptIR(project_id="p", lines=[_line("a", "l1"), _line("b", "l1")])


def test_check_script_ids_reports_order_and_count():
    def probs(ids):
        return check_script_ids(ScriptIR(project_id="p", lines=[_line(i) for i in ids]), ["a", "b", "c"])
    assert len(probs(["a", "c"])) == 1 and "count" in probs(["a", "c"])[0]
    assert len(probs(["b", "a", "c"])) == 1 and "order" in probs(["b", "a", "c"])[0]
    assert any("z" in p for p in probs(["a", "z", "c"]))
    assert probs(["a", "b", "c"]) == []


def test_critique_blocked_property():
    warn = LineCheck(rule="pace", passed=False, severity="warn")
    block = LineCheck(rule="names", passed=False, severity="block")
    assert not LineCritique(line_id="l", checks=[warn]).blocked
    assert LineCritique(line_id="l", checks=[warn, block]).blocked
    with pytest.raises(ValidationError):
        LineCritique(line_id="l", checks=[], scores={"bogus": True})


def _marks(**kw):
    from engine.narration.artifacts import LineMarks
    return LineMarks(**{"line_id": "L001", "emotion": "calm", "energy": "med", "rate": 1.0, "pause_after_ms": 250, **kw})


def test_marks_rate_bounds():
    for bad in ({"rate": 0.89}, {"rate": 1.11}, {"pause_after_ms": 149}, {"pause_after_ms": 801}):
        with pytest.raises(ValidationError):
            _marks(**bad)
    assert _marks(rate=0.9, pause_after_ms=800).rate == 0.9
    from engine.narration.artifacts import PerformancePlan
    with pytest.raises(ValidationError):
        PerformancePlan(project_id="p", script_revision=0, lines=[_marks(), _marks()])


def test_voice_take_word_order():
    from engine.narration.artifacts import VoiceTake, Word
    with pytest.raises(ValidationError):
        Word(text="a", start=1.0, end=0.5)
    with pytest.raises(ValidationError):
        Word(text="a", start=-0.1, end=0.5)
    take = dict(line_id="L001", audio_path="a.wav", duration=1.0, words=[Word(text="a", start=0, end=0.5)], lead_ms=80,
                tail_ms=80, stt_text="a", wer=0.0, tts_model="kokoro-82m", voice_id="af", rate=1.0, attempt=1)
    assert VoiceTake(**take).flagged is False
    for bad in ({"duration": 0}, {"wer": 1.1}, {"attempt": 4}):
        with pytest.raises(ValidationError):
            VoiceTake(**{**take, **bad})


def _tl(panels, clips):
    from engine.narration.artifacts import LockedTimeline, TimelineClip, TimelinePanel
    return LockedTimeline(
        project_id="p", duration=panels[-1][2],
        panels=[TimelinePanel(panel_id=a, start=s, end=e, cut_reason="line-start", scene_id="s0") for a, s, e in panels],
        clips=[TimelineClip(line_id=f"L{a}", panel_id=a, start=s, end=e, audio_path="a.wav") for a, s, e in clips])


def test_timeline_rejects_gap_and_overlap():
    _tl([("p1", 0, 2), ("p2", 2, 4)], [])
    for panels in ([("p1", 0, 2), ("p2", 2.5, 4)], [("p1", 0, 2), ("p2", 1.5, 4)], [("p1", 0.5, 2)]):
        with pytest.raises(ValidationError):
            _tl(panels, [])


def test_timeline_clip_inside_its_panel():
    panels = [("p1", 0, 2), ("p2", 2, 4)]
    _tl(panels, [("p1", 0.1, 1.9), ("p2", 2.1, 3.9)])
    for clips in ([("p1", 0.1, 2.1)], [("p1", 0.1, 1.5), ("p2", 1.4, 3)], [("p9", 0, 1)]):
        with pytest.raises(ValidationError):
            _tl(panels, clips)


def test_timeline_clip_overlap_and_tolerance():
    panels = [("p1", 0, 2), ("p2", 2, 4)]
    with pytest.raises(ValidationError, match="overlaps"):
        _tl(panels, [("p1", 0.1, 1.5), ("p1", 1.0, 1.9)])
    _tl(panels, [("p1", 0.1, 2 + 1e-9)])
    with pytest.raises(ValidationError):
        _tl(panels, [("p1", 0.1, 2.001)])


def test_timeline_rejects_duplicate_panel_ids():
    with pytest.raises(ValidationError, match="unique"):
        _tl([("p1", 0, 2), ("p1", 2, 4)], [])
