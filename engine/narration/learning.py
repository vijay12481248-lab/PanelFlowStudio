"""Learning loop: owner edits and regenerations become preference pairs; the newest good ones form a per-series user few-shot pack."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

from engine.config.settings import settings
from engine.narration.bible.store import BibleStore, _check_key
from engine.narration.steps.critique.rules import DEFAULT_BANNED


def learning_root() -> Path:
    return Path(settings.app_data_dir) / "narration_learning"


def record_pair(kind: Literal["edit", "regenerate"], before: str, after: str, facts: str, reasons: list[str],
                series_key: str) -> None:
    root = learning_root()
    root.mkdir(parents=True, exist_ok=True)
    row = dict(kind=kind, before=before, after=after, facts=facts, reasons=reasons, series_key=series_key)
    with (root / "pairs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _series_keys() -> list[str]:
    path = learning_root() / "pairs.jsonl"
    if not path.exists():
        return []
    keys = set()
    for s in path.read_text(encoding="utf-8").splitlines():
        try:
            keys.add(json.loads(s)["series_key"])
        except (ValueError, KeyError, TypeError):
            continue
    return sorted(k for k in keys if isinstance(k, str))


def _usable_pairs(series_key: str) -> list[dict]:
    path = learning_root() / "pairs.jsonl"
    if not path.exists():
        return []
    try:
        banned = [*DEFAULT_BANNED, *BibleStore().load(series_key).narrator_voice.banned_phrases]
    except ValueError:
        return []
    out, seen = [], set()
    for s in reversed(path.read_text(encoding="utf-8").splitlines()):  # newest first
        try:
            p = json.loads(s)
            if p["series_key"] != series_key:
                continue
            line, low = " ".join(p["after"].split()), p["after"].lower()
            ok = 5 <= len(line.split()) <= 10 and not any(re.search(rf"\b{re.escape(b.lower())}\b", low) for b in banned)
            if ok and line not in seen and p["facts"]:
                seen.add(line)
                out.append({"facts": p["facts"], "line": line})
        except (ValueError, KeyError, TypeError, AttributeError):  # one torn line must not stop the refresh
            continue
    return out


def refresh_fewshot(series_key: str, min_pairs: int = 5, max_rows: int = 10) -> Path | None:
    _check_key(series_key)
    rows = _usable_pairs(series_key)
    if len(rows) < min_pairs:
        return None
    path = learning_root() / series_key / "fewshot_user.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[:max_rows]), encoding="utf-8")
    os.replace(tmp, path)
    return path


def user_fewshot(series_key: str) -> list[dict]:
    try:
        _check_key(series_key)
        text = (learning_root() / series_key / "fewshot_user.jsonl").read_text(encoding="utf-8")
    except (ValueError, OSError):
        return []
    out = []
    for s in text.splitlines():
        try:
            r = json.loads(s)
            out.append({"facts": str(r["facts"]), "line": str(r["line"])})
        except (ValueError, KeyError, TypeError):
            continue
    return out
