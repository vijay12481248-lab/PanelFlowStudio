"""Compact fact rendering and the few-shot pack shared by the writing prompts."""
from __future__ import annotations

import json
import re
from pathlib import Path

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


def char_names(bible: SeriesBible, sheet: BeatSheet) -> dict[str, str]:
    names = {c.id: c.name for c in bible.characters}
    return names | {u: names[c] for u, c in sheet.character_resolutions.items() if c in names}


def display_name(char_id: str, names: dict[str, str]) -> str:
    if char_id in names:
        return names[char_id]
    return "a stranger" if char_id.startswith("unknown_") else char_id


def panel_line(k: int, f: PanelFacts, names: dict[str, str]) -> str:
    chars = ", ".join(display_name(c, names) for c in f.characters_visible) or "-"
    said = " / ".join(d.text for d in f.dialogue) or "-"
    return (f"P{k} | chars: {chars} | action: {f.action} | emotion: {f.emotion}"
            f" | said: {said} | sfx: {', '.join(f.sfx) or '-'}")
