"""The structured cross-check between two judges (design: approach B).

Round 1: each judge reads the picture blind. Round 2: only the items where they differ go back, one narrow question each, with the other judge's claim and
evidence in front of the judge and a request to say what is visible (never "do you agree?"). A judge that switches to the other's answer without giving new
evidence is recorded as a suspect flip: a model giving in is not a second opinion. What is still different afterwards is `disputed`: low confidence, no value,
for the owner to decide.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from engine.original.judges import Judge, JudgeAnswer, Topic, item_value

CONFIDENCE = {"agreed": 0.9, "resolved": 0.7, "single": 0.5, "disputed": 0.3, "unjudged": 0.0}
MIN_EVIDENCE_WORDS = 4


class Item(BaseModel):
    key: str  # "camera" | "people" | "action:<i>"
    status: Literal["agreed", "resolved", "disputed", "single", "unjudged"]
    value: str | None = None  # the final value; None when disputed or unjudged
    confidence: float = 0.0
    answers: dict[str, dict] = Field(default_factory=dict)  # judge -> {"round1", "round2", "evidence"}
    suspect_flips: list[str] = Field(default_factory=list)


class CrossCheck(BaseModel):
    judges: list[str]  # the judges that answered
    items: list[Item]
    single_judge: bool = False
    seconds: float = 0.0


def _keys(answers: list[JudgeAnswer]) -> list[tuple[str, Topic, int | None]]:
    keys: list[tuple[str, Topic, int | None]] = [("camera", "camera", None), ("people", "people", None)]
    lengths = {len(a.actions) for a in answers}
    if len(answers) > 0 and len(lengths) == 1:  # persons can only be matched by position when everyone saw the same number of them
        keys += [(f"action:{i}", "action", i) for i in range(lengths.pop())]
    return keys


def _safe(fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception:
        pass


async def cross_check(judges: list[Judge], image: Path | bytes, states: list[str], *, same_state: Callable[[str, str], bool] = lambda a, b: a == b,
                      between: Callable[[], None] = lambda: None) -> CrossCheck:
    """`between` runs between two judges (e.g. unload the Ollama model before the ComfyUI judge starts); its failure is ignored."""
    t0 = time.monotonic()
    answered: list[tuple[Judge, JudgeAnswer]] = []
    for n, judge in enumerate(judges):
        if n:
            _safe(between)
        try:
            a = await judge.read(image, states)
        except Exception:
            continue
        if a.ok:
            answered.append((judge, a))
    first = [a for _, a in answered]
    keys = _keys(first)
    same = lambda topic, x, y: same_state(x, y) if topic == "action" else x == y

    items: dict[str, Item] = {}
    disputed: list[tuple[str, Topic, int | None]] = []
    for key, topic, idx in keys:
        values = {a.judge: item_value(a, topic, idx) for a in first}
        known = [v for v in values.values() if v is not None]
        answers = {a.judge: {"round1": values[a.judge], "round2": None, "evidence": a.evidence} for a in first}
        if not known:
            items[key] = Item(key=key, status="unjudged", confidence=0.0, answers=answers)
        elif len(known) < len(first) or len(first) == 1:
            items[key] = Item(key=key, status="single", value=known[0], confidence=CONFIDENCE["single"], answers=answers)
        elif same(topic, known[0], known[1]):
            items[key] = Item(key=key, status="agreed", value=known[0], confidence=CONFIDENCE["agreed"], answers=answers)
        else:
            items[key] = Item(key=key, status="disputed", confidence=CONFIDENCE["disputed"], answers=answers)
            disputed.append((key, topic, idx))

    if disputed and len(answered) == 2:
        for n, (judge, own) in enumerate(answered):
            if n:
                _safe(between)
            other = answered[1 - n][1]
            for key, topic, idx in disputed:
                try:
                    again = await judge.reread(image, topic, idx, other, states)
                except Exception:
                    again = JudgeAnswer(judge=judge.name, ok=False)
                value = item_value(again, topic, idx, reread=True) if again.ok else None
                entry = items[key].answers[judge.name]
                entry["round2"] = value
                if again.ok and again.evidence:
                    entry["round2_evidence"] = again.evidence
        for key, topic, idx in disputed:
            it = items[key]
            (name_a, ans_a), (name_b, ans_b) = [(j.name, a) for j, a in answered]
            r2a, r2b = it.answers[name_a]["round2"], it.answers[name_b]["round2"]
            if r2a is not None and r2b is not None and same(topic, r2a, r2b):
                it.status, it.value, it.confidence = "resolved", r2a, CONFIDENCE["resolved"]
            for name, own, other in ((name_a, ans_a, ans_b), (name_b, ans_b, ans_a)):
                e = it.answers[name]
                new_evidence = e.get("round2_evidence", "")
                gave_in = e["round2"] is not None and same(topic, e["round2"], item_value(other, topic, idx)) and not same(topic, e["round2"], e["round1"] or "")
                if gave_in and (len(new_evidence.split()) < MIN_EVIDENCE_WORDS or new_evidence == own.evidence):
                    it.suspect_flips.append(name)
            for e in it.answers.values():
                e["evidence"] = e.pop("round2_evidence", e["evidence"])

    return CrossCheck(judges=[a.judge for a in first], items=[items[k] for k, _, _ in keys], single_judge=len(first) == 1, seconds=round(time.monotonic() - t0, 2))
