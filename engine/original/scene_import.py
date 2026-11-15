"""Load pictures that already exist on disk into the Scene review queue (docs/SCENE_DIRECTOR.md): the 24 baseline pictures (raw and director), earlier runs,
each as a pending `scene_runs` row, then the two vision judges look at each one. Same store functions as a normal Draw it; nothing here draws or edits a picture.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from engine.database.models import SceneAnalysisRecord, SceneRunRecord
from engine.original import scene_store

RAW_RESULT = {"status": "raw", "unmet": [], "unverified": True, "seconds": 0.0, "iterations": []}  # the system never checked a raw picture


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def collect(scene_root: Path, briefs_file: Path) -> list[dict[str, Any]]:
    """Every picture under `scene_root` as {rel, source, brief, plan, result}: baseline raw, baseline director (with its stored plan and result), earlier runs."""
    briefs = {b["id"]: b for b in _read(briefs_file)}
    items: list[dict[str, Any]] = []
    base = scene_root / "_baseline"
    for bid, b in briefs.items():
        png = base / "raw" / f"{bid}.png"
        if png.is_file():
            items.append({"rel": f"baseline/raw/{bid}.png", "source": png, "brief": f"[raw] {b['text']}", "plan": {"scene_type": b["scene_type"], "brief": b["text"]}, "result": dict(RAW_RESULT)})
    results = base / "director" / "results.json"
    for row in _read(results) if results.is_file() else []:
        if not row.get("file"):
            continue  # the planner failed for this brief: there is no picture
        png, panel = base / "director" / row["file"], base / "director" / "panels" / f"{row['id']}.json"
        if png.is_file() and panel.is_file():
            result = _read(panel)
            items.append({"rel": f"baseline/director/{row['id']}.png", "source": png, "brief": f"[director] {result['plan']['brief']}", "plan": result["plan"], "result": result})
    for folder in sorted(p for p in scene_root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for js in sorted((folder / "panels").glob("*.json")):
            png = js.with_suffix(".png")
            if png.is_file():
                result = _read(js)
                items.append({"rel": f"earlier/{folder.name}/{js.stem}.png", "source": png, "brief": f"[earlier run] {result['plan']['brief']}", "plan": result["plan"], "result": result})
    return items


def import_runs(db, project_id: str, items: list[dict[str, Any]], dest_root: Path, judge: Callable[..., Any], progress: Callable[[str], None] = lambda m: None) -> dict[str, int]:
    """Create a pending run for every item that has none (the picture is copied to `<dest_root>/<project_id>/<rel>`, where the engine serves it from), then call
    `judge(db, run_id, scene_type, image_path)` for every run without a good analysis. A judge that fails is counted and retried on the next call; it never stops the import."""
    out = {"created": 0, "skipped": 0, "judged": 0, "judge_errors": 0}
    for n, it in enumerate(items, 1):
        dst = dest_root / project_id / it["rel"]
        run = db.query(SceneRunRecord).filter_by(project_id=project_id, image_path=it["rel"]).first()
        if run is not None:
            run_id, out["skipped"] = run.id, out["skipped"] + 1
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(it["source"], dst)
            run_id = scene_store.create_run(db, project_id=project_id, job_id=None, brief=it["brief"], plan=it["plan"], image_path=it["rel"], result=it["result"])["id"]
            out["created"] += 1
        if db.query(SceneAnalysisRecord).filter(SceneAnalysisRecord.run_id == run_id, SceneAnalysisRecord.error.is_(None)).first() is not None:
            continue
        progress(f"[{n}/{len(items)}] judging {it['rel']}")
        try:
            judge(db, run_id, str(it["plan"].get("scene_type", "")), dst)
        except Exception as exc:  # noqa: BLE001  (counted, reported by the caller, retried next time)
            out["judge_errors"] += 1
            progress(f"    judge failed: {type(exc).__name__}: {exc}")
            continue
        latest = db.query(SceneAnalysisRecord).filter_by(run_id=run_id).order_by(SceneAnalysisRecord.created_at.desc()).first()
        if latest is not None and latest.error:
            out["judge_errors"] += 1
            progress(f"    judges reported: {latest.error}")
        else:
            out["judged"] += 1
    return out
