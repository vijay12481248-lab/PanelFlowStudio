"""Versioned per-series story bible: root/<series_key>/bible.json plus bible.v<N>.json snapshots."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import ValidationError

from engine.config.settings import settings
from engine.narration.artifacts import (
    BibleCharacter,
    BibleLocation,
    BibleProposal,
    BibleRevision,
    SeriesBible,
)


def series_key_for(title: str, source_metadata: dict | None) -> str:
    name = ((source_metadata or {}).get("series_title") or "").strip()
    if not name:
        i = title.lower().find(" - chapter")
        name = title if i < 0 else title[:i]
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _write_atomic(path: Path, bible: SeriesBible) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(bible.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def apply_proposals(bible: SeriesBible, proposals: list[BibleProposal]) -> tuple[SeriesBible, list[str]]:
    out = bible.model_copy(deep=True)
    applied: list[str] = []
    for p in proposals:
        try:
            if p.kind in ("add_character", "add_location"):
                is_char = p.kind == "add_character"
                item = (BibleCharacter if is_char else BibleLocation).model_validate(p.payload)
                existing = out.characters if is_char else out.locations
                if any(e.id == item.id or e.name.lower() == item.name.lower() for e in existing):
                    continue
                existing.append(item)
                applied.append(f"{p.kind}: {item.name}")
            elif p.kind == "update_plot":
                out = SeriesBible.model_validate({**out.model_dump(), "plot_so_far": p.payload["plot_so_far"]})
                applied.append("update_plot")
            elif p.kind == "add_thread":
                text = p.payload["text"]
                if text not in out.open_threads:
                    out.open_threads.append(text)
                    applied.append(f"add_thread: {text}")
            elif p.kind == "close_thread":
                text = p.payload["text"]
                if text in out.open_threads:
                    out.open_threads.remove(text)
                    applied.append(f"close_thread: {text}")
        except (ValidationError, KeyError, TypeError):
            continue  # malformed proposal payload: skipped, never raised
    return out, applied


class BibleStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else Path(settings.app_data_dir) / "series"

    apply_proposals = staticmethod(apply_proposals)

    def load(self, series_key: str) -> SeriesBible:
        path = self.root / series_key / "bible.json"
        if not path.exists():
            return SeriesBible(series_key=series_key)
        return SeriesBible.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save(self, bible: SeriesBible, project_id: str, applied: list[str]) -> SeriesBible:
        version = bible.version + 1
        new = bible.model_copy(deep=True, update={
            "version": version,
            "history": [*bible.history, BibleRevision(version=version, project_id=project_id, applied=applied)],
        })
        folder = self.root / bible.series_key
        folder.mkdir(parents=True, exist_ok=True)
        _write_atomic(folder / f"bible.v{version}.json", new)
        _write_atomic(folder / "bible.json", new)
        return new