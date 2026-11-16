"""The questions the two judges are asked about a picture and its zoomed tiles, and a strict parser for their replies.

Same rules as `engine/original/judges.py`: the judge is never told what to expect, a reply that echoes the template is not an answer, and nothing is guessed.
Counting by number is unreliable (measured 2026-11-16: "ARMS: 2" for a picture with four), so the judge LISTS every hand and every foot, one per line, and the code counts
the lines. The flags (people, writing, doubled object, merged bodies) are a second, short question so a small judge's reply is never cut off.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from engine.original.judges import TEMPLATE_MARKERS, _people as _count

ENUM_PROMPT = (
    "Look at this picture and list the body parts of every person, one per line, exactly like this:\n"
    "HAND 1: <which side of the picture, and what the hand is touching or doing>\n"
    "HAND 2: <...>\n"
    "FOOT 1: <which side of the picture, and what the foot is touching>\n"
    "FOOT 2: <...>\n"
    "Write one line for each separate hand and one line for each separate foot, counting a part once even if it is partly hidden, and look at every part of the "
    "picture including the lap and between the legs. Write NO HANDS or NO FEET when you can see none.")

WHOLE_FLAGS_PROMPT = (
    "Look at the whole picture and answer exactly in this format, nothing else:\n"
    "PEOPLE: <how many people are visible, as a number>\n"
    "TEXT: <yes or no: are any letters, numbers or writing drawn in the picture>\n"
    "DOUBLE: <yes or no: is any held object or weapon drawn twice, for example two blades on one sword>\n"
    "MERGED: <yes or no: are any two people's bodies merged so you cannot tell whose arms or legs are whose>\n"
    "EVIDENCE: <one short sentence naming what you can see>")

TILE_FLAGS_PROMPT = (
    "Look at this zoomed crop of a picture and answer exactly in this format, nothing else:\n"
    "TEXT: <yes or no: are any letters, numbers or writing drawn in this crop>\n"
    "DOUBLE: <yes or no: is any held object or weapon drawn twice in this crop>\n"
    "EVIDENCE: <one short sentence naming what you can see>")


def pose_prompt(question: str) -> str:
    return ("Look at the picture and answer the question with the word yes or no first, then one short sentence naming what you can see.\n"
            f"QUESTION: {question}")


@dataclass
class Answer:
    tile: str
    judge: str
    ok: bool = False
    people: int | None = None
    hands: int | None = None
    feet: int | None = None
    text: bool | None = None
    double: bool | None = None
    merged: bool | None = None
    evidence: str = ""


def _line(text: str, name: str) -> str | None:
    """The value on the `NAME: value` line; None when absent or when the judge echoed the template."""
    m = re.search(rf"(?im)^\s*{name}\s*:[ \t]*(.*)$", text or "")
    value = m.group(1).strip() if m else None
    if value is None:
        return None
    if name != "EVIDENCE" and any(t in value.lower() for t in TEMPLATE_MARKERS):
        return None
    return value or None


def parse_yes_no(text: str | None) -> bool | None:
    low = (text or "").strip().lower()
    tokens = re.findall(r"[a-z']+", low)
    if not tokens or re.search(r"\b(yes|no)\b.*\bor\b.*\b(yes|no)\b", low):
        return None
    if tokens[0] in {"yes", "y", "true"}:
        return True
    if tokens[0] in {"no", "not", "false", "n", "never", "none"}:
        return False
    return None


def _listed(text: str, part: str) -> int | None:
    """How many `PART n: description` lines the judge wrote (distinct numbers, template echoes skipped); 0 for NO <PART>S; None when it listed nothing usable."""
    numbers = {m.group(1) for m in re.finditer(rf"(?im)^\s*{part}\s*(\d+)\s*:[ \t]*(?!.*[<>])\S", text or "")}
    if numbers:
        return len(numbers)
    plural = {"HAND": r"hands?", "FOOT": r"(?:foot|feet)"}[part]
    return 0 if re.search(rf"(?i)\bno\s+{plural}\b", text or "") else None


def parse_enum_reply(text: str) -> tuple[int | None, int | None]:
    """(hands, feet) counted from the judge's list; (None, None) when it echoed the question's template instead of answering."""
    if re.search(r"(?im)^\s*(HAND|FOOT)\s*\d+\s*:[^\n]*<", text or ""):
        return None, None
    return _listed(text, "HAND"), _listed(text, "FOOT")


def parse_flags_reply(text: str, judge: str, tile: str) -> Answer:
    people = _count(_line(text, "PEOPLE")) if _line(text, "PEOPLE") else None
    flags = {k: parse_yes_no(_line(text, k.upper())) for k in ("text", "double", "merged")}
    ok = people is not None or any(v is not None for v in flags.values())
    return Answer(tile=tile, judge=judge, ok=ok, people=people, evidence=_line(text, "EVIDENCE") or "", **flags)
