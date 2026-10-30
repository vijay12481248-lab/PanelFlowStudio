import pytest

from engine.narration.artifacts import OcrDialogue, PanelFacts
from engine.narration.steps import factview
from engine.narration.steps.factview import display_name, load_fewshot, panel_line


def _facts(**kw):
    base = dict(panel_id="p1", order=1, is_story=True, shot="medium", action="Kai draws his sword",
                emotion="tense", importance=3, confidence=0.9)
    base.update(kw)
    return PanelFacts(**base)


def test_fewshot_rows_valid():
    rows = load_fewshot()
    assert len(rows) == 8
    for r in rows:
        assert 5 <= len(r["line"].split()) <= 10
        assert "panel" not in (r["facts"] + r["line"]).lower()


def test_fewshot_row_missing_key_raises(tmp_path, monkeypatch):
    (tmp_path / "bad.jsonl").write_text('{"facts": "x"}\n', encoding="utf-8")
    monkeypatch.setattr(factview, "FEWSHOT_DIR", tmp_path)
    with pytest.raises(ValueError):
        load_fewshot("bad")


def test_panel_line_hides_unknown_labels():
    out = panel_line(2, _facts(characters_visible=["c1", "unknown_1"]), {"c1": "Kai"})
    assert out.startswith("P2 | chars: Kai, a stranger | action: Kai draws his sword")
    assert "unknown_1" not in out
    assert out.endswith("said: - | sfx: -")


def test_panel_line_dialogue_verbatim():
    f = _facts(dialogue=[OcrDialogue(region_id="r1", text="You're TOO slow!"),
                         OcrDialogue(region_id="r2", text="Hmph...")], sfx=["CLANG"])
    out = panel_line(1, f, {})
    assert "said: You're TOO slow! / Hmph... | sfx: CLANG" in out
    assert display_name("zzz", {}) == "zzz"


def test_proposed_names_and_cues_describe_unknowns():
    from engine.narration.artifacts import Beat, BeatSheet, BibleProposal, Scene, SeriesBible
    sheet = BeatSheet(project_id="p", hook="h", chapter_summary="s", scenes=[Scene(scene_id='s0', first_panel_id='p1', last_panel_id='p1', goal='g', conflict='c', turn='t', beats=[Beat(beat_id='b', panel_ids=['p1'], what_happens='w', function='setup', intensity=0.5)])], bible_proposals=[
        BibleProposal(kind="add_character", payload={"id": "c_1", "name": "Yulin", "unknown_ids": ["unknown_1"]})])
    cues = {"unknown_1": "blue skinned man", "unknown_2": "The blue-skinned bald man"}
    names = factview.char_names(SeriesBible(series_key="s"), sheet, cues)
    assert display_name("unknown_1", names) == "Yulin"
    assert display_name("unknown_2", names) == "the blue-skinned bald man"
    assert display_name("unknown_3", names) == "a stranger"
