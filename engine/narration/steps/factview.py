"""Compact fact rendering and the few-shot pack shared by the writing prompts."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from engine.narration.artifacts import BeatSheet, PanelFacts, SeriesBible

FEWSHOT_DIR = Path(__file__).resolve().parents[1] / "fewshot"


FACT_REF = re.compile(r"^(action|emotion|dialogue|characters|setting|sfx|beat:[A-Za-z0-9_-]+)$")
_FACT_TOKENS = {"action", "emotion", "dialogue", "characters", "setting", "sfx"}


def normalize_facts(items: list[str]) -> list[str]:
    """The model writes 'action: P4'; keep the leading token. Entries that stay invalid are left for the re-ask."""
    out = []
    for s in items:
        tok = re.split(r"[:\s(]", s.strip().lower(), maxsplit=1)[0]
        out.append(tok if tok in _FACT_TOKENS else s)
    return list(dict.fromkeys(out))


def load_fewshot(pack: str = "recap_v1") -> list[dict]:
    rows = [json.loads(s) for s in (FEWSHOT_DIR / f"{pack}.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    for r in rows:
        if not isinstance(r, dict) or "facts" not in r or "line" not in r:
            raise ValueError(f"few-shot pack {pack}: row needs 'facts' and 'line': {r!r}")
    return rows


def cues_of(facts: Iterable[PanelFacts]) -> dict[str, str]:
    return {u: c for f in facts for u, c in f.unknown_cues.items()}


_TRAILING = {"with", "and", "in", "of", "on", "at", "a", "an", "the", "or", "to", "holding", "wearing"}


def _short(cue: str) -> str:
    """The cue's head noun phrase: up to 4 words, cut at the first connector ('bald man with pink eyes' -> 'bald man')."""
    words = re.sub(r"^(?:the|a|an)\s+", "", " ".join(cue.split()), flags=re.I).split()
    head = [words[0]] if words else []
    for w in words[1:4]:
        if w.lower().strip(",;") in _TRAILING:
            break
        head.append(w)
    return " ".join(head).strip(",;")


def char_names(bible: SeriesBible, sheet: BeatSheet, cues: dict[str, str]) -> dict[str, str]:
    """id -> display name. Unknowns get, in rising priority: 'the <cue>', a name proposed this chapter, a bible match."""
    names = {c.id: c.name for c in bible.characters}
    described = {u: "the " + _short(c) for u, c in cues.items() if c.strip()}
    proposed = {u: p.payload["name"] for p in sheet.bible_proposals if p.kind == "add_character"
                for u in p.payload.get("unknown_ids", [])}
    return described | proposed | names | {u: names[c] for u, c in sheet.character_resolutions.items() if c in names}


def display_name(char_id: str, names: dict[str, str]) -> str:
    if char_id in names:
        return names[char_id]
    return "a stranger" if char_id.startswith("unknown_") else char_id


def present_ids(facts: Iterable[PanelFacts]) -> list[str]:
    """Character ids seen or heard in these panels, in first-appearance order."""
    out: dict[str, None] = {}
    for f in facts:
        for c in [*f.characters_visible, *(d.speaker_id for d in f.dialogue if d.speaker_id)]:
            out.setdefault(c, None)
    return list(out)


def cast_line(ids: Iterable[str], names: dict[str, str], bible: SeriesBible) -> str:
    """'Gu Yifan (he) - protagonist; the stranger' for the characters actually present."""
    known = {c.id: c for c in bible.characters}
    parts = []
    for cid in dict.fromkeys(ids):
        name = display_name(cid, names)
        c = known.get(cid)
        if c is None:
            parts.append(name)
            continue
        extra = ", ".join(x for x in (c.pronouns, c.role) if x)
        parts.append(f"{name} ({extra})" if extra else name)
    return "; ".join(parts) or "(nobody identified)"


def scene_panels(sheet: BeatSheet, panel_id: str, facts: dict[str, PanelFacts]) -> list[PanelFacts]:
    """The facts of every panel in the scene that holds panel_id (by reading order)."""
    for s in sheet.scenes:
        if s.first_panel_id in facts and s.last_panel_id in facts:
            lo, hi = facts[s.first_panel_id].order, facts[s.last_panel_id].order
            if panel_id in facts and lo <= facts[panel_id].order <= hi:
                return [f for f in facts.values() if lo <= f.order <= hi]
    return [facts[panel_id]] if panel_id in facts else []


def beat_context(sheet: BeatSheet, panel_id: str) -> str:
    """The story a panel belongs to: its scene's goal and turn, and the beat that covers it."""
    for s in sheet.scenes:
        beat = next((b for b in s.beats if panel_id in b.panel_ids), None)
        if beat is not None:
            return f"scene goal: {s.goal} | scene turn: {s.turn} | this beat: {beat.what_happens}"
    return f"chapter: {sheet.chapter_summary}"


def panel_line(k: int, f: PanelFacts, names: dict[str, str]) -> str:
    chars = ", ".join(display_name(c, names) for c in f.characters_visible) or "-"
    said = " / ".join(d.text for d in f.dialogue) or "-"
    return (f"P{k} | chars: {chars} | action: {f.action} | emotion: {f.emotion}"
            f" | said: {said} | sfx: {', '.join(f.sfx) or '-'}")
