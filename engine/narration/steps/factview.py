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


def panel_line(k: int, f: PanelFacts, names: dict[str, str]) -> str:
    chars = ", ".join(display_name(c, names) for c in f.characters_visible) or "-"
    said = " / ".join(d.text for d in f.dialogue) or "-"
    return (f"P{k} | chars: {chars} | action: {f.action} | emotion: {f.emotion}"
            f" | said: {said} | sfx: {', '.join(f.sfx) or '-'}")
