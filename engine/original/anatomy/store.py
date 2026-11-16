"""The anatomy knowledge records: one JSON line per checked picture and per owner flag, and statistics over them.

A plain append-only file under the app-data config folder (the same place as the Scene Director's lessons) instead of a SQL table: the Reels tools run outside the
engine and have no database session, and nothing here needs joins. A half-written last line (a crash mid-append) is skipped, never fatal.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from engine.config.settings import settings


def checks_path() -> Path:
    return settings.app_data_dir / "config" / "anatomy_checks.jsonl"


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def append_check(path: Path, *, model: str, picture: str, prompt: str, rules_used: bool, report: dict, attempt: int) -> None:
    _append(path, {"kind": "check", "ts": time.time(), "model": model, "picture": picture, "prompt": prompt[:500], "rules_used": bool(rules_used),
                   "attempt": int(attempt), "status": report.get("status"),
                   "confirmed": [d.get("kind") for d in report.get("confirmed", [])], "suspected": [d.get("kind") for d in report.get("suspected", [])]})


def flag_missed(path: Path, *, picture: str, model: str, note: str) -> None:
    """The owner says a picture had a mistake the system missed; the picture joins the labelled set and counts against the reviewer."""
    if not note.strip():
        raise ValueError("say what the mistake was")
    _append(path, {"kind": "owner_flag", "ts": time.time(), "picture": picture, "model": model, "note": note.strip()[:2000]})


def _read(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    out: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _rate(rows: list[dict]) -> float | None:
    return round(sum(1 for r in rows if r.get("confirmed")) / len(rows), 3) if rows else None


def stats(path: Path) -> dict:
    records = _read(path)
    checks = [r for r in records if r.get("kind") == "check"]
    flagged = [{k: r.get(k) for k in ("picture", "model", "note")} for r in records if r.get("kind") == "owner_flag"]
    by_model: dict[str, dict] = {}
    for model in sorted({r.get("model", "") for r in checks}):
        rows = [r for r in checks if r.get("model") == model]
        by_model[model] = {
            "checked": len(rows), "defect_rate": _rate(rows), "by_kind": dict(Counter(k for r in rows for k in r.get("confirmed", []))),
            "rate_rules_off": _rate([r for r in rows if not r.get("rules_used")]), "rate_rules_on": _rate([r for r in rows if r.get("rules_used")]),
            "redraws": sum(1 for r in rows if r.get("attempt", 0) > 0)}
    return {"checked": len(checks), "by_model": by_model, "owner_flags": len(flagged), "flagged": flagged}
