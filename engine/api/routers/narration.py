"""Narration compiler review queue, run inspector and line actions. Runs are addressed as project_id + run_id only."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.database.models import ProjectRecord
from engine.database.session import get_db
from engine.jobs.workflow import enqueue_project_operation, register_operation_factory
from engine.narration import review
from engine.narration.artifacts import CritiqueReport
from engine.narration.bible.store import BibleStore
from engine.narration.steps.factview import char_names, cues_of, panel_line

router = APIRouter(prefix="/api/narration", tags=["narration"])


def _bibles() -> BibleStore:
    return BibleStore()


def _run_dir(db: Session, project_id: str, run_id: str) -> Path:
    try:
        return review.resolve_run_dir(db, project_id, run_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "Project or run not found")


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run_dirs(project: ProjectRecord):
    return (p.parent for p in Path(project.workspace_path).glob("narration/*/review.json"))


@router.get("/review")
def review_queue(db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for project in db.query(ProjectRecord).all():
        for run_dir in _run_dirs(project):
            try:
                item = review._item(run_dir)  # also rejects a review.json that belongs to another run directory
            except (ValueError, OSError):
                continue  # one corrupt file must not hide the rest
            if item.status != "pending" or item.project_id != project.id:
                continue
            mtime = (run_dir / "review.json").stat().st_mtime
            out.append({"project_id": project.id, "project_title": project.title, "run_id": item.run_id,
                        "reasons": item.reasons, "line_ids": item.line_ids,
                        "created": datetime.fromtimestamp(mtime, timezone.utc).isoformat()})
    return sorted(out, key=lambda i: i["created"], reverse=True)


@router.get("/runs/{project_id}")
def list_runs(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    project = db.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    out = []
    for p in Path(project.workspace_path).glob("narration/*/run.json"):
        try:
            run = _json(p)
            out.append({"run_id": run["run_id"], "gate": run.get("gate"), "created": run["started_at"],
                        "steps": [{k: s.get(k) for k in ("step", "status", "seconds", "model_calls")}
                                  for s in run.get("steps", [])]})
        except (ValueError, KeyError, TypeError, OSError):
            continue
    return sorted(out, key=lambda r: r["created"], reverse=True)


@router.get("/runs/{project_id}/{run_id}")
def inspect_run(project_id: str, run_id: str, db: Session = Depends(get_db)) -> dict:
    run_dir = _run_dir(db, project_id, run_id)
    try:
        run = _json(run_dir / "run.json")
    except (ValueError, OSError):
        raise HTTPException(404, "Run has no readable run.json")
    try:
        item = review._item(run_dir)
    except (ValueError, OSError):
        item = None
    checks: dict = {}
    try:
        report = CritiqueReport.model_validate_json((run_dir / "critique.json").read_text(encoding="utf-8"))
        checks = {lc.line_id: [c.model_dump(mode="json") for c in lc.checks] for lc in report.lines}
    except (ValueError, OSError):
        pass
    takes = {}
    try:
        takes = {t["line_id"]: {"wer": t["wer"], "flagged": t["flagged"], "stt_text": t["stt_text"]}
                 for t in _json(run_dir / "takes.json")}
    except (ValueError, KeyError, TypeError, OSError):
        pass
    sheet = facts = names = None
    try:
        sheet, facts = review._sheet(run_dir), review._facts(run_dir)
        names = char_names(_bibles().load(item.series_key if item else ""), sheet, cues_of(facts.values()))
    except (ValueError, OSError):
        pass
    try:
        script_lines = review._latest(run_dir).lines
    except ValueError:
        script_lines = []  # the run stopped before write
    lines = [{"line_id": ln.line_id, "panel_id": ln.panel_id, "text": ln.text, "status": ln.status, "kind": ln.kind,
              "checks": checks.get(ln.line_id, []),
              "facts": panel_line(1, facts[ln.panel_id], names) if facts and ln.panel_id in facts else "",
              "take": takes.get(ln.line_id)} for ln in script_lines]
    beat_sheet = None
    if sheet is not None:
        beat_sheet = {"hook": sheet.hook, "chapter_summary": sheet.chapter_summary,
                      "scenes": [{"scene_id": s.scene_id, "goal": s.goal, "first_panel_id": s.first_panel_id,
                                  "last_panel_id": s.last_panel_id} for s in sheet.scenes]}
    return {"run": run, "lines": lines, "beat_sheet": beat_sheet,
            "review": item.model_dump(mode="json") if item else None}


# ---- background jobs: the same durable job manager autopilot uses; handlers never wait on models ----

def _regenerate_operation(project_id: str, payload: dict):
    def operation(db, progress, is_cancelled):
        run_dir = review.resolve_run_dir(db, project_id, payload["run_id"])
        workspace = Path(db.get(ProjectRecord, project_id).workspace_path)

        async def go():
            comp = await review._build_compiler(workspace)
            script = await review.regenerate_line(run_dir, payload["line_id"], payload.get("hint", ""),
                                                  comp.client, comp.scheduler, comp.cache, comp.bibles)
            return next(ln.status for ln in script.lines if ln.line_id == payload["line_id"])

        progress(0.1, "Regenerating line")
        return {"line_id": payload["line_id"], "status": asyncio.run(go())}

    return operation


def _continue_operation(project_id: str, payload: dict):
    def operation(db, progress, is_cancelled):
        progress(0.1, "Voicing and projecting approved narration")
        return {"script_id": asyncio.run(review.continue_after_approval(project_id, payload["run_id"]))}

    return operation


register_operation_factory("NARRATION_REGENERATE", _regenerate_operation)
register_operation_factory("NARRATION_CONTINUE", _continue_operation)


class LineAction(BaseModel):
    action: Literal["accept", "edit", "fallback", "regenerate"]
    text: Optional[str] = None
    hint: Optional[str] = None


@router.post("/runs/{project_id}/{run_id}/lines/{line_id}")
def line_action(project_id: str, run_id: str, line_id: str, body: LineAction, db: Session = Depends(get_db)) -> dict:
    run_dir = _run_dir(db, project_id, run_id)
    try:
        if body.action == "regenerate":
            review._open(run_dir)  # fail fast (400) instead of inside the job
            payload = {"run_id": run_id, "line_id": line_id, "hint": body.hint or ""}
            return {"job_id": enqueue_project_operation(
                project_id, "NARRATION_REGENERATE", _regenerate_operation(project_id, payload), job_input=payload)}
        if body.action == "edit":
            if not (body.text or "").strip():
                raise ValueError("edit needs text")
            script = review.edit_line(run_dir, line_id, body.text, _bibles())
        elif body.action == "accept":
            script = review.accept_line(run_dir, line_id)
        else:
            script = review.fallback_line(run_dir, line_id, _bibles())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return next(ln for ln in script.lines if ln.line_id == line_id).model_dump(mode="json")


@router.post("/runs/{project_id}/{run_id}/approve")
def approve_run(project_id: str, run_id: str, db: Session = Depends(get_db)) -> dict:
    run_dir = _run_dir(db, project_id, run_id)
    try:
        approval = review.approve(run_dir, _bibles())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    job_id = None
    if approval.needs_continue:
        payload = {"run_id": run_id}
        job_id = enqueue_project_operation(
            project_id, "NARRATION_CONTINUE", _continue_operation(project_id, payload), job_input=payload)
    return {"bible_version": approval.bible.version, "job_id": job_id}
