"""Deterministic rules: one judge's answers about a picture and its tiles -> defects. Pure functions, no model calls.

Counts are never added across tiles (the bands overlap, one hand can be in two tiles): every view's list of hands or feet is a total for that view and is compared
with two per person, which needs the number of people; without it no count is judged.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from engine.original.anatomy.questions import Answer

DEFECT_KINDS = ("extra_hands", "extra_feet", "stray_text", "duplicate_object", "pose_missing", "merged_bodies")
COUNT_KINDS = ("extra_hands", "extra_feet")  # judged from the judge's own list of hands and feet
LIMBS = (("hands", "extra_hands"), ("feet", "extra_feet"))

# pose key, regex over the prompt, yes/no question. A pose the prompt asks for but the picture does not show is a defect (a woman asked to rest her hands on her knees
# but drawn with them clasped in her lap is wrong even when she has two arms).
POSES: tuple[tuple[str, str, str], ...] = (
    ("cross_legged", r"cross[- ]?legged|legs? crossed", "Is the person sitting on the floor with their legs crossed?"),
    ("hands_on_knees", r"hands?\b.{0,30}\bknees?", "Are the person's hands resting on their own knees, with nothing in their lap?"),
    ("kick", r"\bkick", "Is one leg raised high and extended in a kick?"),
    ("raised_leg", r"\b(raised?|lifted|extended) (a |one |his |her )?leg|leg (fully )?(raised|extended)", "Is one leg raised high off the ground?"),
    ("two_hands", r"\b(both|two) hands?\b.{0,25}\b(grip\w*|hold\w*|clasp\w*)|\b(grip\w*|hold\w*)\b.{0,40}\bwith (both|two) hands",
     "Are both of the person's hands gripping the same object?"),
)


class Defect(BaseModel):
    kind: str
    judge: str
    tile: str
    detail: str
    pose: str | None = None


def pose_asks(prompt: str) -> tuple[list[tuple[str, str]], list[str]]:
    """The yes/no checks the prompt asks for, and why nothing was checked when it names no pose from the list."""
    low = (prompt or "").lower()
    asks = [(key, question) for key, pattern, question in POSES if re.search(pattern, low)]
    return asks, [] if asks else ["no pose word from the list"]


def text_requested(prompt: str) -> bool:
    return bool(re.search(r"\b(says?|saying|word|words|letters?|text|caption|label(?:led|ed)?|sign|title)\b", (prompt or "").lower()))


def judge_defects(answers: list[Answer], people: int | None, pose_answers: dict[str, bool | None], text_asked: bool = False, judge: str = "") -> list[Defect]:
    who = answers[0].judge if answers else judge
    out: list[Defect] = []
    for a in answers:
        if not a.ok:
            continue
        for attr, kind in LIMBS:
            n = getattr(a, attr)
            if n is not None and people is not None and n > 2 * people:
                out.append(Defect(kind=kind, judge=a.judge, tile=a.tile, detail=f"{n} {attr} listed for {people} people ({a.tile}): {a.evidence}"))
        if a.text and not text_asked:
            out.append(Defect(kind="stray_text", judge=a.judge, tile=a.tile, detail=f"letters or writing drawn: {a.evidence}"))
        if a.double:
            out.append(Defect(kind="duplicate_object", judge=a.judge, tile=a.tile, detail=f"an object is drawn twice: {a.evidence}"))
        if a.merged:
            out.append(Defect(kind="merged_bodies", judge=a.judge, tile=a.tile, detail=f"bodies merged: {a.evidence}"))
    for pose, seen in pose_answers.items():
        if seen is False:
            out.append(Defect(kind="pose_missing", judge=who, tile="whole", detail=f"the asked pose '{pose}' is not shown", pose=pose))
    return out
