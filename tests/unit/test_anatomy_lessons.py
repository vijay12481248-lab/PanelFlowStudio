from engine.creative.mistakes import MistakeLedger
from engine.original.anatomy.lessons import domain, record_report, rules_for, seed_known_rules
from engine.original.anatomy.review import AnatomyReport
from engine.original.anatomy.rules import Defect

MODEL = "hidream_i1_fast"


def report(*defects):
    return AnatomyReport(status="defects", confirmed=list(defects))


def D(kind, pose=None):
    return Defect(kind=kind, judge="j", tile="whole", detail="x", pose=pose)


def test_one_sighting_is_recorded_but_not_yet_a_rule_the_second_activates_it(tmp_path):
    ledger = MistakeLedger(file_path=tmp_path / "l.json")
    assert record_report(ledger, MODEL, report(D("extra_hands"))) == 1
    assert rules_for(ledger, MODEL, "a girl sitting") == ""
    record_report(ledger, MODEL, report(D("extra_hands")))
    assert "two arms" in rules_for(ledger, MODEL, "a girl sitting")
    assert ledger.load_mistakes(domain(MODEL))[0].recurrence_count == 2


def test_only_confirmed_defects_are_recorded(tmp_path):
    ledger = MistakeLedger(file_path=tmp_path / "l.json")
    r = AnatomyReport(status="clean", suspected=[D("extra_hands")])
    assert record_report(ledger, MODEL, r) == 0 and ledger.load_mistakes(domain(MODEL)) == []


def test_a_pose_rule_applies_only_to_prompts_that_ask_for_that_pose(tmp_path):
    ledger = MistakeLedger(file_path=tmp_path / "l.json")
    for _ in range(2):
        record_report(ledger, MODEL, report(D("pose_missing", "cross_legged")))
    assert "legs" in rules_for(ledger, MODEL, "a woman sitting cross-legged on the floor")
    assert rules_for(ledger, MODEL, "a boy running") == ""


def test_rules_are_per_model(tmp_path):
    ledger = MistakeLedger(file_path=tmp_path / "l.json")
    for _ in range(2):
        record_report(ledger, MODEL, report(D("extra_hands")))
    assert rules_for(ledger, "zimage", "a girl") == ""


def test_seeded_rules_are_active_at_once_and_seeding_twice_adds_nothing(tmp_path):
    ledger = MistakeLedger(file_path=tmp_path / "l.json")
    n = seed_known_rules(ledger)
    assert n >= 2 and seed_known_rules(ledger) == 0
    text = rules_for(ledger, MODEL, "any prompt")
    assert "two arms" in text
    assert all("agent-labelled" in r.example_good for r in ledger.load_mistakes(domain(MODEL)))


def test_a_corrupt_ledger_file_gives_no_rules_instead_of_an_error(tmp_path):
    path = tmp_path / "l.json"
    ledger = MistakeLedger(file_path=path)
    path.write_text("{not json", encoding="utf-8")
    assert rules_for(ledger, MODEL, "a girl") == ""


def test_the_doubled_object_rule_names_no_object_and_applies_only_to_prompts_with_a_held_object(tmp_path):
    # real run 2026-11-16: the rule "exactly one sword" made klein draw a sword into calm sitting pictures
    ledger = MistakeLedger(file_path=tmp_path / "l.json")
    seed_known_rules(ledger)
    assert "sword" not in rules_for(ledger, MODEL, "a swordsman holding a sword overhead").lower().replace("swordsman", "")
    assert "nothing doubled" in rules_for(ledger, MODEL, "a swordsman holding a sword overhead")
    assert "doubled" not in rules_for(ledger, MODEL, "a young woman sitting cross-legged on the floor")
    assert "two arms" in rules_for(ledger, MODEL, "a young woman sitting cross-legged on the floor")  # the general hand rule still applies
