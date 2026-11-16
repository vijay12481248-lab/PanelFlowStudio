"""The questions the two judges are asked about a picture and its zoomed tiles, and a strict parser for their replies.

Same rules as `engine/original/judges.py`: the judge is never told what to expect, a reply that echoes the template or gives two different numbers is not an
answer (`None`), and nothing is guessed. The whole-picture question asks for the largest number any ONE person has; a tile question asks for what is visible in
that crop (the rules compare tile totals with two per person, never add tiles together: bands overlap).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from engine.original.judges import TEMPLATE_MARKERS, _people as _count

WHOLE_PROMPT = (
    "Look at the whole picture and answer exactly in this format, nothing else:\n"
    "PEOPLE: <how many people are visible, as a number>\n"
    "ARMS: <the largest number of arms any ONE person has, counting every separate arm, as a number>\n"
    "HANDS: <the largest number of hands any ONE person has, as a number>\n"
    "LEGS: <the largest number of legs any ONE person has, as a number>\n"
    "FEET: <the largest number of feet any ONE person has, as a number>\n"
    "TEXT: <yes or no: are any letters, numbers or writing drawn in the picture>\n"
    "DOUBLE: <yes or no: is any object drawn twice or doubled, for example two blades on one sword>\n"
    "MERGED: <yes or no: are any two people's bodies merged so you cannot tell whose arms or legs are whose>\n"
    "EVIDENCE: <one short sentence naming what each visible hand is doing or touching>")

TILE_PROMPT = (
    "Look at this zoomed crop of a picture and answer exactly in this format, nothing else:\n"
    "ARMS: <how many separate arms are visible in this crop, as a number>\n"
    "HANDS: <how many separate hands are visible in this crop, as a number>\n"
    "LEGS: <how many separate legs are visible in this crop, as a number>\n"
    "FEET: <how many separate feet are visible in this crop, as a number>\n"
    "TEXT: <yes or no: are any letters, numbers or writing drawn in this crop>\n"
    "DOUBLE: <yes or no: is any object drawn twice or doubled in this crop>\n"
    "EVIDENCE: <one short sentence naming what each visible hand is doing or touching>")


def pose_prompt(question: str) -> str:
    return ("Look at the picture and answer the question with the word yes or no first, then one short sentence naming what you can see.\n"
            f"QUESTION: {question}")


@dataclass
class Answer:
    tile: str
    judge: str
    ok: bool = False
    people: int | None = None
    arms: int | None = None
    hands: int | None = None
    legs: int | None = None
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


def parse_reply(text: str, judge: str, tile: str) -> Answer:
    counts = {k: (_count(_line(text, k.upper())) if _line(text, k.upper()) else None) for k in ("people", "arms", "hands", "legs", "feet")}
    flags = {k: parse_yes_no(_line(text, k.upper())) for k in ("text", "double", "merged")}
    evidence = _line(text, "EVIDENCE") or ""
    ok = any(v is not None for v in counts.values()) or any(v is not None for v in flags.values())
    return Answer(tile=tile, judge=judge, ok=ok, evidence=evidence, **counts, **flags)
