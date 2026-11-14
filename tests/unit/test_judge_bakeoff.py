"""Task 3 of the review-page plan: scoring the judges against labelled pictures, and the gate that decides whether the cross-check ships."""
from engine.original.crosscheck import CrossCheck, Item
from engine.original.judge_eval import gate, score
from engine.original.judges import JudgeAnswer

LABELS = [
    {"file": "p1.png", "camera": "looks_up", "people": 2, "actions": ["striking", "blocking"]},
    {"file": "p2.png", "camera": "level", "people": 1, "actions": ["readying"]},
]


def a(judge, camera, people, actions, ok=True):
    return JudgeAnswer(judge=judge, ok=ok, camera=camera, people=people, actions=actions)


def cc(**items):
    return CrossCheck(judges=["A", "B"], items=[Item(key=k, status=s, value=v, confidence=0.5) for k, (s, v) in items.items()])


def test_each_method_is_scored_on_every_label_item():
    answers = {
        "p1.png": {"A": a("A", "looks_up", 2, ["striking", "blocking"]), "B": a("B", "level", 2, ["striking", "blocking"]),
                   "cc": cc(camera=("resolved", "looks_up"), people=("agreed", "2"), **{"action:0": ("agreed", "striking"), "action:1": ("agreed", "blocking")})},
        "p2.png": {"A": a("A", "level", 1, ["readying"]), "B": a("B", "level", 1, ["striking"]),
                   "cc": cc(camera=("agreed", "level"), people=("agreed", "1"), **{"action:0": ("disputed", None)})},
    }
    r = score(LABELS, answers)
    assert r["items"] == 7  # camera + people + actions for p1, the same for p2
    assert (r["judge_A"]["answered"], r["judge_A"]["wrong"]) == (7, 0)
    assert (r["judge_B"]["answered"], r["judge_B"]["wrong"]) == (7, 2)  # p1 camera, p2 action
    assert (r["vote"]["answered"], r["vote"]["wrong"]) == (5, 0)  # disagreements abstain
    assert (r["crosscheck"]["answered"], r["crosscheck"]["wrong"]) == (6, 0)  # the disputed item abstains
    assert r["crosscheck"]["coverage"] == 6 / 7 and r["judge_B"]["accuracy_of_answered"] == 5 / 7


def test_an_abstaining_method_is_never_counted_wrong():
    answers = {lab["file"]: {"A": a("A", None, None, [], ok=False), "B": a("B", None, None, [], ok=False), "cc": CrossCheck(judges=[], items=[])} for lab in LABELS}
    r = score(LABELS, answers)
    assert all(r[m]["wrong"] == 0 and r[m]["answered"] == 0 and r[m]["coverage"] == 0.0 for m in ("judge_A", "judge_B", "vote", "crosscheck"))


def test_state_groups_count_synonyms_as_correct():
    labels = [{"file": "e.png", "camera": "level", "people": 1, "actions": ["grieving"]}]
    answers = {"e.png": {"A": a("A", "level", 1, ["lost"]), "B": a("B", "level", 1, ["lost"]), "cc": cc(camera=("agreed", "level"), people=("agreed", "1"), **{"action:0": ("agreed", "lost")})}}
    assert score(labels, answers)["judge_A"]["wrong"] == 1
    assert score(labels, answers, same_state=lambda x, y: {x, y} <= {"grieving", "lost"} or x == y)["judge_A"]["wrong"] == 0


def report(wrong_cc, coverage, wrong_a=3, wrong_b=4):
    return {"judge_A": {"wrong": wrong_a}, "judge_B": {"wrong": wrong_b}, "crosscheck": {"wrong": wrong_cc, "coverage": coverage}}


def test_gate_passes_only_with_strictly_fewer_wrong_answers_and_enough_coverage():
    assert gate(report(1, 0.8))
    assert not gate(report(1, 0.6))  # answers too little
    assert not gate(report(3, 0.9))  # ties the better single judge
    assert not gate(report(4, 0.9))
    assert gate(report(2, 0.7))  # exactly the coverage bar
