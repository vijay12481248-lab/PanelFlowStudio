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
from engine.narration.artifacts import (
    CritiqueReport, NARRATOR_ID, PerformancePlan, ScriptIR, SeriesBible, VoiceTake,
)
from engine.narration.bible.store import BibleStore, series_key_for
from engine.narration.casting import apply_recommendations, load_cast, resolve_cast, save_cast
from engine.narration.ledger import TakeLedger, outdated_lines
from engine.narration.qa import QaReport, repairs
from engine.narration.runtime.roles import load_voice_catalog
from engine.narration.stoppoints import load_stop_points, open_stop_points, resolve_stop_point
from engine.narration.steps.critique.judges import JUDGES
from engine.narration.steps.critique.rules import rule_checks
from engine.narration.steps.factview import char_names, cues_of, panel_line
from engine.security.paths import contained_file_response, resolve_contained_path

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


def _context(run_dir: Path, item) -> dict:
    """Everything a line view needs. Checks are recomputed from the current text; critique.json is the fallback."""
    ctx = {"sheet": None, "facts": None, "names": None, "takes": {}, "checks": {}, "qa": {}}
    report = None
    try:
        report = CritiqueReport.model_validate_json((run_dir / "critique.json").read_text(encoding="utf-8"))
        ctx["checks"] = {lc.line_id: [c.model_dump(mode="json") for c in lc.checks] for lc in report.lines}
    except (ValueError, OSError):
        pass
    try:
        ctx["takes"] = {t["line_id"]: {"wer": t["wer"], "flagged": t["flagged"], "stt_text": t["stt_text"],
                                       "voice_profile_id": t.get("voice_profile_id", ""),
                                       "script_revision": t.get("script_revision", 0),
                                       "direction_revision": t.get("direction_revision", 0),
                                       "provider": t.get("provider", "")}
                        for t in _json(run_dir / "takes.json")}
    except (ValueError, KeyError, TypeError, OSError):
        pass
    try:
        ctx["qa"] = {lid: {"passed": r["passed"], "checks": r["checks"], "repairs": repairs(QaReport(**r))}
                     for lid, r in _json(run_dir / "qa.json").items()}
    except (ValueError, KeyError, TypeError, OSError):
        pass
    try:
        sheet, facts = review._sheet(run_dir), review._facts(run_dir)
        try:
            bible = _bibles().load(item.series_key if item else "")
        except ValueError:  # a passed run has no review.json, so no series key: names fall back to ids and descriptions
            bible = SeriesBible(series_key="unknown")
        ctx.update(sheet=sheet, facts=facts, names=char_names(bible, sheet, cues_of(facts.values())))
    except (ValueError, KeyError, OSError):
        return ctx
    try:
        script = review._latest(run_dir)
        fresh = rule_checks(script, facts, [ln.panel_id for ln in script.lines], bible)
        checks = {k: [c.model_dump(mode="json") for c in v] for k, v in fresh.items()}
        # judge verdicts cannot be recomputed: keep them for lines whose text is unchanged since that critique
        if report is not None:
            old = {lc.line_id: lc for lc in report.lines}
            was = {ln.line_id: ln.text for ln in ScriptIR.model_validate_json(
                (run_dir / f"script_r{report.revision}.json").read_text(encoding="utf-8")).lines}
            for ln in script.lines:
                if ln.line_id in old and was.get(ln.line_id) == ln.text:
                    checks.setdefault(ln.line_id, []).extend(
                        c.model_dump(mode="json") for c in old[ln.line_id].checks if c.rule in JUDGES)
        ctx["checks"] = checks
        ctx["outdated"] = _outdated_takes(run_dir, script)
    except (ValueError, KeyError, OSError):
        pass
    return ctx


def _outdated_takes(run_dir: Path, script: ScriptIR) -> list[str]:
    """The lines whose take no longer matches the line: the text, the direction or the voice moved on."""
    try:
        takes = [VoiceTake.model_validate(t) for t in _json(run_dir / "takes.json")]
    except (ValueError, KeyError, TypeError, OSError):
        return []
    if not takes:
        return []
    plan = None
    try:
        plan = PerformancePlan.model_validate_json((run_dir / "performance.json").read_text(encoding="utf-8"))
    except (ValueError, OSError):
        pass
    profiles = {}
    try:
        profiles = {a["character_id"]: a["profile_id"] for a in (_json(run_dir / "casting.json") or {}).get("assignments", [])}
    except (ValueError, KeyError, TypeError, OSError):
        profiles = {}
    ledger = TakeLedger(script, direction_revision=plan.revision if plan else script.revision,
                        voice_profile_ids=profiles)
    return outdated_lines(takes, ledger)


def _line_view(ln, ctx: dict) -> dict:
    """The NarrationLine shape, shared by the inspector and the line-action responses."""
    try:
        facts = panel_line(1, ctx["facts"][ln.panel_id], ctx["names"])
    except (KeyError, TypeError):
        facts = ""  # panel missing from panel_facts.json
    speaker_id = getattr(ln, "speaker_id", NARRATOR_ID)
    take = ctx["takes"].get(ln.line_id)
    qa = ctx["qa"].get(ln.line_id)
    return {"line_id": ln.line_id, "panel_id": ln.panel_id, "text": ln.text, "status": ln.status, "kind": ln.kind,
            "speaker_id": speaker_id,
            "speaker_name": "Narrator" if speaker_id == NARRATOR_ID else ctx["names"].get(speaker_id, speaker_id),
            "checks": ctx["checks"].get(ln.line_id, []), "facts": facts, "take": take,
            "outdated": ln.line_id in ctx.get("outdated", []),
            "qa": qa}

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
    ctx = _context(run_dir, item)
    try:
        script_lines = review._latest(run_dir).lines
    except ValueError:
        script_lines = []  # the run stopped before write
    sheet = ctx["sheet"]
    lines = [_line_view(ln, ctx) for ln in script_lines]
    beat_sheet = None
    if sheet is not None:
        beat_sheet = {"hook": sheet.hook, "chapter_summary": sheet.chapter_summary,
                      "scenes": [{"scene_id": s.scene_id, "goal": s.goal, "first_panel_id": s.first_panel_id,
                                  "last_panel_id": s.last_panel_id} for s in sheet.scenes]}
    try:
        cast = _json(run_dir / "casting.json")
    except (ValueError, OSError):
        cast = None  # the run stopped before the voice step
    try:
        readiness_report = _json(run_dir / "readiness.json")
    except (ValueError, OSError):
        readiness_report = None  # the run stopped before the timeline
    return {"run": run, "lines": lines, "beat_sheet": beat_sheet, "casting": cast,
            "readiness": readiness_report,
            "stop_points": [p.model_dump(mode="json") for p in open_stop_points(run_dir)],
            "review": item.model_dump(mode="json") if item else None}


class StopPointRequest(BaseModel):
    kind: str
    choice: str


@router.get("/runs/{project_id}/{run_id}/stop-points")
def list_stop_points(project_id: str, run_id: str, db: Session = Depends(get_db)):
    """The decisions this run is waiting for."""
    run_dir = _run_dir(db, project_id, run_id)
    return {"stop_points": [p.model_dump(mode="json") for p in load_stop_points(run_dir)]}


@router.post("/runs/{project_id}/{run_id}/stop-points")
def answer_stop_point(project_id: str, run_id: str, req: StopPointRequest, db: Session = Depends(get_db)):
    """Answer a stop point: the owner chose, and the run carries on."""
    run_dir = _run_dir(db, project_id, run_id)
    try:
        remaining = resolve_stop_point(run_dir, req.kind, req.choice)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"stop_points": [p.model_dump(mode="json") for p in remaining]}


@router.get("/runs/{project_id}/{run_id}/takes/{line_id}/audio")
def take_audio(project_id: str, run_id: str, line_id: str, db: Session = Depends(get_db)):
    run_dir = _run_dir(db, project_id, run_id)
    workspace = Path(db.get(ProjectRecord, project_id).workspace_path)
    try:  # the path comes from takes.json, never from the client
        audio = next(t["audio_path"] for t in _json(run_dir / "takes.json") if t["line_id"] == line_id)
        p = resolve_contained_path(workspace, audio, must_be_file=True)
        return contained_file_response(workspace, p, media_type="audio/wav", filename=p.name)
    except (StopIteration, KeyError, TypeError, ValueError, OSError):
        raise HTTPException(404, "Take audio not found")


@router.get("/projects/{project_id}/cast")
def get_cast(project_id: str, db: Session = Depends(get_db)):
    """The cast of a project: the voices it uses, the ones it recommends, and the ones it lacks."""
    project = db.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    key = series_key_for(project.title or "", project.source_metadata)
    if not key:
        raise HTTPException(404, "Project has no series")
    bible = _bibles().load(key)
    catalog = load_voice_catalog()
    assigned = load_cast(key)
    characters = [c.id for c in bible.characters]
    plan = resolve_cast(key, bible, characters, catalog, assigned)
    return {
        "series_key": key,
        "catalog": [p.model_dump(mode="json") for p in catalog],
        "assigned": assigned,
        "cast": [a.model_dump(mode="json") for a in plan.assignments],
        "recommendations": [r.model_dump(mode="json") for r in plan.recommendations],
        "uncast": plan.uncast,
    }


class CastRequest(BaseModel):
    character_id: str
    profile_id: str


@router.post("/projects/{project_id}/cast")
def set_cast(project_id: str, req: CastRequest, db: Session = Depends(get_db)):
    """Cast a character to a voice, or clear the casting by sending an empty profile id."""
    project = db.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    key = series_key_for(project.title or "", project.source_metadata)
    if not key:
        raise HTTPException(404, "Project has no series")
    if req.profile_id:
        known = {p.id for p in load_voice_catalog()}
        if req.profile_id not in known:
            raise HTTPException(400, "That voice is not an approved profile")
    current = load_cast(key)
    if req.profile_id:
        current[req.character_id] = req.profile_id
    else:
        current.pop(req.character_id, None)
    save_cast(key, current)
    return {"series_key": key, "assigned": current}


@router.post("/projects/{project_id}/cast/accept")
def accept_cast_recommendations(project_id: str, db: Session = Depends(get_db)):
    """Accept every proposed voice, keeping the assignments already made."""
    project = db.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    key = series_key_for(project.title or "", project.source_metadata)
    if not key:
        raise HTTPException(404, "Project has no series")
    bible = _bibles().load(key)
    catalog = load_voice_catalog()
    plan = resolve_cast(key, bible, [c.id for c in bible.characters], catalog, load_cast(key))
    assigned = apply_recommendations(plan, key, catalog)
    return {"series_key": key, "assigned": assigned}


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
            review._line(review._latest(run_dir), line_id)
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
    return _line_view(next(ln for ln in script.lines if ln.line_id == line_id), _context(run_dir, review._item(run_dir)))


@router.post("/runs/{project_id}/{run_id}/approve")
def approve_run(project_id: str, run_id: str, db: Session = Depends(get_db)) -> dict:
    run_dir = _run_dir(db, project_id, run_id)
    try:
        item = review._item(run_dir)
        if item.status == "approved":
            # a stranded approve: the proposals are already applied, so only the continue job is missing
            if (run_dir / "continued.json").exists():
                raise ValueError("run is already finished")
            approval = review.Approval(_bibles().load(item.series_key), True)
        else:
            approval = review.approve(run_dir, _bibles())
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    job_id = None
    if approval.needs_continue:
        payload = {"run_id": run_id}
        job_id = enqueue_project_operation(
            project_id, "NARRATION_CONTINUE", _continue_operation(project_id, payload), job_input=payload)
    return {"bible_version": approval.bible.version, "job_id": job_id}
