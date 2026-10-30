"""Learning loop: owner edits and regenerations become preference pairs; the newest good ones form a user few-shot pack."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from engine.config.settings import settings
from engine.narration.steps.critique.rules import DEFAULT_BANNED


def learning_root() -> Path:
    return Path(settings.app_data_dir) / "narration_learning"


def record_pair(kind: Literal["edit", "regenerate"], before: str, after: str, facts: str, reasons: list[str]) -> None:
    root = learning_root()
    root.mkdir(parents=True, exist_ok=True)
    row = dict(kind=kind, before=before, after=after, facts=facts, reasons=reasons)
    with (root / "pairs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _usable_pairs() -> list[dict]:
    path = learning_root() / "pairs.jsonl"
    if not path.exists():
        return []
    out, seen = [], set()
    for s in reversed(path.read_text(encoding="utf-8").splitlines()):  # newest first
        try:
            p = json.loads(s)
            line, low = " ".join(p["after"].split()), p["after"].lower()
            ok = 5 <= len(line.split()) <= 10 and not any(re.search(rf"\b{re.escape(b)}\b", low) for b in DEFAULT_BANNED)
            if ok and line not in seen and p["facts"]:
                seen.add(line)
                out.append({"facts": p["facts"], "line": line})
        except (ValueError, KeyError, AttributeError):  # one torn line must not stop the refresh
            continue
    return out


def refresh_fewshot(min_pairs: int = 5, max_rows: int = 10) -> Path | None:
    rows = _usable_pairs()
    if len(rows) < min_pairs:
        return None
    path = learning_root() / "fewshot_user.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[:max_rows]), encoding="utf-8")
    return path


def user_fewshot() -> list[dict]:
    path = learning_root() / "fewshot_user.jsonl"
    if not path.exists():
        return []
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
