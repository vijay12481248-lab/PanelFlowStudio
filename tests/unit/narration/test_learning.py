import json

import pytest

from engine.config.settings import settings
from engine.narration import learning, review
from engine.narration.artifacts import BeatSheet, BibleProposal, SeriesBible
from tests.unit.narration.test_review import _parked
from tests.unit.narration.test_understand import _facts


@pytest.fixture(autouse=True)
def _app_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "app_data_dir", tmp_path / "appdata")


def _pairs():
    return [json.loads(s) for s in (learning.learning_root() / "pairs.jsonl").read_text(encoding="utf-8").splitlines()]


def _seed(*afters, facts="chars: Kai | action: Kai runs", key="s"):
    for a in afters:
        learning.record_pair("edit", "old", a, facts, [], key)


def test_edit_records_pair(tmp_path):
    comp, res = _parked(tmp_path)
    review.edit_line(res.run_dir, "L002", "He walks through the quiet hall slowly", comp.bibles)
    (p,) = _pairs()
    assert p["kind"] == "edit" and p["after"] == "He walks through the quiet hall slowly"
    assert p["series_key"] and p["before"] != p["after"] and "action:" in p["facts"] and not p["facts"].startswith("P1")


def test_refresh_needs_min_pairs():
    _seed("one two three four five", "six seven eight nine ten")
    assert learning.refresh_fewshot("s") is None


def test_refresh_filters_and_dedupes():
    _seed("too short", "In this panel the man stands still", "a b c d e f g h i j k",
          "Kai runs through the dark hall", "Kai runs through the dark hall", "Mira waits by the old gate",
          "Ren hands over the sealed scroll", "Kai blocks the sword with bare hands", "Mira finds the cage empty")
    path = learning.refresh_fewshot("s")
    rows = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
    assert [r["line"] for r in rows] == ["Mira finds the cage empty", "Kai blocks the sword with bare hands",
                                        "Ren hands over the sealed scroll", "Mira waits by the old gate",
                                        "Kai runs through the dark hall"]
    assert set(rows[0]) == {"facts", "line"}


def test_write_prompt_uses_user_rows_first(tmp_path):
    from tests.unit.narration.test_write import _answer, _facts as wf, _run, _sheet
    _seed(*[f"owner row {w} stays in the prompt" for w in "abcde"])
    learning.refresh_fewshot("s")
    _, client = _run(tmp_path, [wf(1)], _sheet(("p1", "p1")), [_answer] * 3)
    prompt = client.calls[0][1]
    assert prompt.index("owner row e stays") < prompt.index("Kai stops the assassin's blade")


def test_place_named_character_becomes_location():
    from engine.narration.steps.understand import MergeDraft, _proposals
    merge = MergeDraft.model_validate({
        "hook": "h", "chapter_summary": "s", "character_resolutions": {},
        "new_characters": [{"name": "Flying Cloud Manor", "unknown_ids": ["unknown_1"]},
                           {"name": "Yulin", "unknown_ids": ["unknown_2"]}]})
    out, _ = _proposals(merge, SeriesBible(series_key="s"), {"unknown_1": "a", "unknown_2": "b"},
                        [_facts(1, names_mentioned=["Flying Cloud Manor", "Yulin"])])
    assert [(p.kind, p.payload["name"]) for p in out] == [("add_character", "Yulin"), ("add_location", "Flying Cloud Manor")]
    assert out[1].payload == {"id": "l_1", "name": "Flying Cloud Manor"}


def test_malformed_pack_and_pair_lines_are_skipped():
    _seed("Kai runs through the dark hall", "Mira waits by the old gate", "Ren hands over the sealed scroll",
          "Kai blocks the sword with bare hands", "Mira finds the cage empty")
    with (learning.learning_root() / "pairs.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"torn": \n[1, 2]\n{"series_key": "s"}\n')
    path = learning.refresh_fewshot("s")
    with path.open("a", encoding="utf-8") as f:
        f.write('{torn\n[1]\n{"line": "x"}\n')
    assert len(learning.user_fewshot("s")) == 5


def test_series_packs_are_isolated():
    _seed(*[f"series a row {w} stays in here" for w in "abcde"], key="a")
    _seed(*[f"series b row {w} stays in here" for w in "abcde"], key="b")
    learning.refresh_fewshot("a")
    assert learning.refresh_fewshot("b") is not None
    assert all("series a" in r["line"] for r in learning.user_fewshot("a"))
    assert all("series b" in r["line"] for r in learning.user_fewshot("b"))
    assert learning.user_fewshot("c") == [] and learning.user_fewshot("../x") == []


def test_series_banned_phrases_filter_pairs(tmp_path):
    from engine.narration.bible.store import BibleStore
    from engine.narration.artifacts import NarratorVoice
    store = BibleStore()
    store.save(SeriesBible(series_key="s", narrator_voice=NarratorVoice(banned_phrases=["moonlit"])), "p", [])
    _seed("Kai runs through the moonlit hall", *[f"owner row {w} stays in the prompt" for w in "abcd"])
    assert [r["line"] for r in learning._usable_pairs("s")] == [f"owner row {w} stays in the prompt" for w in "dcba"]


def test_failed_save_records_no_pair(tmp_path, monkeypatch):
    comp, res = _parked(tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(review, "_save", boom)
    with pytest.raises(OSError):
        review.edit_line(res.run_dir, "L002", "He walks through the quiet hall slowly", comp.bibles)
    assert not (learning.learning_root() / "pairs.jsonl").exists()


def test_place_does_not_claim_unknowns_a_character_needs():
    from engine.narration.steps.understand import MergeDraft, _proposals
    merge = MergeDraft.model_validate({
        "hook": "h", "chapter_summary": "s", "character_resolutions": {},
        "new_characters": [{"name": "Flying Cloud Manor", "unknown_ids": ["unknown_1"]},
                           {"name": "Yulin", "unknown_ids": ["unknown_1"]}]})
    out, _ = _proposals(merge, SeriesBible(series_key="s"), {"unknown_1": "a"},
                        [_facts(1, names_mentioned=["Flying Cloud Manor", "Yulin"])])
    assert out[0].kind == "add_character" and out[0].payload["unknown_ids"] == ["unknown_1"]