import pytest

from engine.narration.artifacts import (
    BibleCharacter, OcrDialogue, PanelFacts, ScriptIR, ScriptLine, SeriesBible, NarratorVoice,
)
from engine.narration.steps.critique.rules import chapter_stats, rule_checks


def _facts(k, said=()):
    return PanelFacts(panel_id=f"p{k}", order=k, is_story=True, shot="medium", action="a", emotion="e",
                      importance=3, confidence=0.9,
                      dialogue=[OcrDialogue(region_id=f"r{k}{j}", text=t) for j, t in enumerate(said)])


def _run(texts, said=None, banned=(), swap=False):
    said = said or {}
    lines = [ScriptLine(line_id=f"L{k:03d}", panel_id=f"p{k}", text=t, facts_used=[], kind="narration")
             for k, t in enumerate(texts, start=1)]
    ids = [ln.panel_id for ln in lines]
    if swap:
        lines[0], lines[1] = lines[1], lines[0]
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", aliases=["the Blade"])],
                        glossary={"Qi": "energy"}, narrator_voice=NarratorVoice(banned_phrases=list(banned)))
    facts = {f"p{k}": _facts(k, said.get(k, ())) for k in range(1, len(texts) + 1)}
    script = ScriptIR(project_id="p", lines=lines)
    return script, rule_checks(script, facts, ids, bible)


def _failed(res, line, rule):
    return [c for c in res[line] if c.rule == rule and not c.passed]


def test_order_blocks_every_line_when_ids_mismatch():
    _, res = _run(["Kai strikes the gate hard now", "Kai strikes the gate hard again"], swap=True)
    assert all(_failed(res, k, "order") and _failed(res, k, "order")[0].severity == "block" for k in res)
    _, ok = _run(["Kai strikes the gate hard now", "Kai strikes the gate hard again"])
    assert not _failed(ok, "L001", "order")


def test_word_budget():
    _, res = _run(["Too short here", "Kai walks to the old gate slowly", "one two three four five six seven eight nine ten eleven twelve thirteen"])
    assert _failed(res, "L001", "word_budget") and _failed(res, "L003", "word_budget")
    assert not _failed(res, "L002", "word_budget")


def test_banned_phrase_default_and_bible():
    _, res = _run(["In this panel Kai strikes the gate", "Kai quietly Fades into the dark", "Kai rests by the gate tonight"],
                  banned=["fades into"])
    assert _failed(res, "L001", "banned_phrase") and _failed(res, "L002", "banned_phrase")
    assert not _failed(res, "L003", "banned_phrase")


def test_unknown_name_ignores_sentence_start_and_ocr_names():
    _, res = _run(["Kai strikes. Then Ryu falls down.", "Kai faces Zorath at the gate"], said={1: ["Ryu!"]})
    assert not _failed(res, "L001", "unknown_name")
    bad = _failed(res, "L002", "unknown_name")
    assert bad and "Zorath" in bad[0].reason and bad[0].severity == "block"


def test_unknown_name_allows_aliases_glossary_quotes_and_stopwords():
    _, res = _run(['He says "Run" and the Blade uses Qi today', "Then I think Monday comes — Alone he waits"])
    assert not _failed(res, "L001", "unknown_name")
    assert not _failed(res, "L002", "unknown_name")


def test_raw_unknown_label():
    _, res = _run(["unknown_3 attacks the gate with force", "Kai attacks the gate with force"])
    assert _failed(res, "L001", "raw_unknown_label") and not _failed(res, "L002", "raw_unknown_label")


def test_warn_rules_do_not_block():
    texts = ["Kai strikes the gate with force", "Kai strikes the gate with force now", "Kai leaves for the long road"]
    script, res = _run(texts)
    warns = [c for c in res["L002"] if not c.passed]
    assert {c.rule for c in warns} == {"repeated_opener", "similar_to_previous"}
    assert all(c.severity == "warn" for c in warns)
    assert not any(not c.passed and c.severity == "block" for cs in res.values() for c in cs)
    pace, rep = chapter_stats(script)
    assert rep == 3  # L002 opener+similar, L003 opener (two lines back)
    assert pace == pytest.approx((6 + 7 + 6) / 3 / 2.75)


def test_banned_phrase_matches_whole_words_only():
    _, res = _run(["Kai says we seek the gate now", "Kai says we see the gate now"])
    assert not _failed(res, "L001", "banned_phrase")
    assert _failed(res, "L002", "banned_phrase")


def test_chapter_stats_empty_script_does_not_divide_by_zero():
    assert chapter_stats(ScriptIR.model_construct(lines=[])) == (0.0, 0)
