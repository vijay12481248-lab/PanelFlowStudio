"""Scoring of the judges against labelled pictures, and the gate that decides whether the cross-check ships (plan Task 3).

Per item (camera, people, each person's action) a method either answers (right or wrong) or abstains. The vote and the cross-check abstain on what the judges
could not settle; abstaining is never wrong, so the comparison is by WRONG answers delivered and by coverage.
"""
from __future__ import annotations

from typing import Callable

from engine.original.crosscheck import CrossCheck
from engine.original.judges import JudgeAnswer, item_value

METHODS = ("judge_A", "judge_B", "vote", "crosscheck")
COVERAGE_BAR = 0.7


def _keys(label: dict) -> list[tuple[str, str, int | None]]:
    keys: list[tuple[str, str, int | None]] = [("camera", "camera", None), ("people", "people", None)]
    return keys + [(f"action:{i}", "action", i) for i in range(len(label.get("actions", [])))]


def _truth(label: dict, topic: str, idx: int | None) -> str:
    return str(label["camera"] if topic == "camera" else label["people"] if topic == "people" else label["actions"][idx])


def score(labels: list[dict], answers: dict[str, dict], same_state: Callable[[str, str], bool] = lambda a, b: a == b) -> dict:
    """`answers[file]` = {"A": JudgeAnswer, "B": JudgeAnswer, "cc": CrossCheck}."""
    tally = {m: {"answered": 0, "correct": 0, "wrong": 0} for m in METHODS}
    total = 0
    same = lambda topic, x, y: same_state(x, y) if topic == "action" else x == y
    for label in labels:
        got = answers[label["file"]]
        cc: CrossCheck = got["cc"]
        by_key = {i.key: i for i in cc.items}
        for key, topic, idx in _keys(label):
            total += 1
            truth = _truth(label, topic, idx)
            values: dict[str, str | None] = {}
            for m, who in (("judge_A", "A"), ("judge_B", "B")):
                ans: JudgeAnswer = got[who]
                values[m] = item_value(ans, topic, idx) if ans.ok else None
            a, b = values["judge_A"], values["judge_B"]
            values["vote"] = a if a is not None and b is not None and same(topic, a, b) else None
            it = by_key.get(key)
            values["crosscheck"] = it.value if it and it.status in ("agreed", "resolved", "single") else None
            for m, v in values.items():
                if v is None:
                    continue
                tally[m]["answered"] += 1
                tally[m]["correct" if same(topic, v, truth) else "wrong"] += 1
    for m in METHODS:
        t = tally[m]
        t["coverage"] = t["answered"] / total if total else 0.0
        t["accuracy_of_answered"] = t["correct"] / t["answered"] if t["answered"] else 0.0
    return {"items": total, **tally}


def gate(report: dict) -> bool:
    """The cross-check ships only if it delivers strictly fewer wrong answers than each judge alone while still answering at least 70% of the items."""
    cc = report["crosscheck"]
    return cc["wrong"] < report["judge_A"]["wrong"] and cc["wrong"] < report["judge_B"]["wrong"] and cc["coverage"] >= COVERAGE_BAR
