import pytest

from engine.original.anatomy.store import append_check, flag_missed, stats


def check(path, model="flux2_klein_4b", kinds=(), rules_used=False, attempt=0, picture="p.png"):
    report = {"status": "defects" if kinds else "clean", "confirmed": [{"kind": k} for k in kinds], "suspected": []}
    append_check(path, model=model, picture=picture, prompt="a girl", rules_used=rules_used, report=report, attempt=attempt)


def test_stats_count_checks_defect_rate_kinds_and_redraws(tmp_path):
    p = tmp_path / "c.jsonl"
    check(p, kinds=("extra_arms",))
    check(p, kinds=(), attempt=1)
    check(p, kinds=())
    check(p, kinds=("extra_arms", "duplicate_object"))
    s = stats(p)
    m = s["by_model"]["flux2_klein_4b"]
    assert s["checked"] == 4 and m["checked"] == 4 and m["defect_rate"] == 0.5
    assert m["by_kind"] == {"extra_arms": 2, "duplicate_object": 1} and m["redraws"] == 1


def test_rates_with_rules_off_and_on_are_separate(tmp_path):
    p = tmp_path / "c.jsonl"
    check(p, kinds=("extra_arms",), rules_used=False)
    check(p, kinds=("extra_arms",), rules_used=False)
    check(p, kinds=(), rules_used=True)
    check(p, kinds=("extra_arms",), rules_used=True)
    m = stats(p)["by_model"]["flux2_klein_4b"]
    assert m["rate_rules_off"] == 1.0 and m["rate_rules_on"] == 0.5


def test_a_missing_file_gives_zeros_and_empty_rates(tmp_path):
    s = stats(tmp_path / "none.jsonl")
    assert s == {"checked": 0, "by_model": {}, "owner_flags": 0, "flagged": []}


def test_a_flagged_miss_is_counted_and_listed_and_needs_a_note(tmp_path):
    p = tmp_path / "c.jsonl"
    flag_missed(p, picture="hug.png", model="flux2_klein_4b", note="four arms")
    s = stats(p)
    assert s["owner_flags"] == 1 and s["flagged"][0]["picture"] == "hug.png" and s["flagged"][0]["note"] == "four arms"
    with pytest.raises(ValueError):
        flag_missed(p, picture="hug.png", model="flux2_klein_4b", note="  ")


def test_a_half_written_last_line_is_skipped_not_fatal(tmp_path):
    p = tmp_path / "c.jsonl"
    check(p, kinds=())
    with open(p, "a", encoding="utf-8") as f:
        f.write('{"kind": "check", "model": "flux2_kl')
    assert stats(p)["checked"] == 1
