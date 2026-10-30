"""Gold chapters live outside the repo (third-party images): <app_data_dir>/narration_gold/<slug>/."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from engine.config.settings import settings
from engine.database.models import ProjectRecord, ScriptSegmentRecord, VideoScriptRecord
from engine.database.session import SessionLocal
from engine.narration.artifacts import SeriesBible
from engine.narration.bible.store import BibleStore, _check_key
from engine.narration.inputs import dump_chapter_inputs, load_chapter_inputs


def gold_root() -> Path:
    return settings.app_data_dir / "narration_gold"


def _write(path: Path, payload) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _bible_before(store: BibleStore, series_key: str, project_id: str) -> SeriesBible:
    """The series bible as it was before this project's revision."""
    cur = store.load(series_key)
    mine = [h.version for h in cur.history if h.project_id == project_id]
    if not mine:
        return cur
    prev = min(mine) - 1
    if prev < 1:
        return SeriesBible(series_key=series_key)
    snap = store.root / series_key / f"bible.v{prev}.json"
    if snap.exists():
        return SeriesBible.model_validate(json.loads(snap.read_text(encoding="utf-8")))
    # no snapshot kept: the current bible minus this project's history entry (its changes stay in)
    return cur.model_copy(update={"history": [h for h in cur.history if h.project_id != project_id]})


def add_gold(project_id: str, slug: str, kind: str = "manhwa") -> Path:
    _check_key(slug)  # also rejects _work and _reports
    dest = gold_root() / slug
    if dest.exists():
        raise FileExistsError(f"gold chapter already exists: {slug}")
    with SessionLocal() as db:
        inputs = load_chapter_inputs(db, project_id)
        workspace = Path(db.get(ProjectRecord, project_id).workspace_path)
        script = (db.query(VideoScriptRecord).filter(VideoScriptRecord.project_id == project_id)
                  .order_by(VideoScriptRecord.created_at.desc()).first())
        segments = (db.query(ScriptSegmentRecord).filter(ScriptSegmentRecord.script_id == script.id)
                    .order_by(ScriptSegmentRecord.sequence).all()) if script else []
        lines = []
        for s in segments:
            ids = (s.source_evidence or {}).get("panel_ids") or []
            if s.type == "NARRATOR" and ids and s.text.strip():  # a segment citing several panels maps to the first
                lines.append({"panel_id": ids[0], "text": s.text})
    runs = sorted(p.parent for p in (workspace / "narration").glob("*/panel_facts.json"))
    if not runs:
        raise ValueError(f"project {project_id} has no narration run with panel facts")
    if not lines:
        print(f"warning: project {project_id} has no narration segments; the reference is empty")
    try:
        dump_chapter_inputs(inputs, dest)
        shutil.copyfile(runs[-1] / "panel_facts.json", dest / "facts.json")
        _write(dest / "reference.json", {"lines": lines})
        _write(dest / "bible.json", _bible_before(BibleStore(), inputs.series_key, project_id).model_dump(mode="json"))
        _write(dest / "meta.json", {"slug": slug, "project_id": project_id, "kind": kind, "frozen": False})
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest
