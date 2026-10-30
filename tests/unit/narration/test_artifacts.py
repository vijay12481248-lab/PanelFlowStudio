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
