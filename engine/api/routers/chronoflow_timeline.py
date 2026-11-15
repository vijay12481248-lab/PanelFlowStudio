"""The studio timeline on the server: the UI mirrors its edits here, agents (MCP) read and change it, the UI adopts their versions."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.chronoflow import timeline_ops as ops

router = APIRouter(prefix="/api/chronoflow/timeline", tags=["chronoflow-timeline"])


class SaveRequest(BaseModel):
    timeline: dict[str, Any]
    source: str = "ui"


class OpRequest(BaseModel):
    op: str
    args: dict[str, Any] = {}


def _bad(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


@router.get("/describe")
def describe() -> dict[str, Any]:
    return ops.describe()


@router.get("/{job_id}")
def get_timeline(job_id: str) -> dict[str, Any]:
    try:
        rec = ops.load(job_id)
    except ops.TimelineError as e:
        raise _bad(e)
    if not rec:
        return {"version": 0, "timeline": None, "clips": []}
    return {**rec, "clips": ops.summary(rec["timeline"])}


@router.put("/{job_id}")
def save_timeline(job_id: str, req: SaveRequest) -> dict[str, Any]:
    try:
        rec = ops.save(job_id, req.timeline, req.source[:16] or "ui")
    except ops.TimelineError as e:
        raise _bad(e)
    return {"version": rec["version"]}


@router.post("/{job_id}/op")
def run_op(job_id: str, req: OpRequest) -> dict[str, Any]:
    try:
        rec = ops.load(job_id)
        if not rec:
            raise ops.TimelineError("no timeline for this job yet: open the job once in the ChronoFlow Video Studio (Edit page)")
        tl = rec["timeline"]
        result = ops.apply_op(tl, req.op, req.args or {})
        saved = ops.save(job_id, tl, "agent")
    except (ops.TimelineError, KeyError, TypeError) as e:
        raise _bad(e)
    return {"ok": True, "version": saved["version"], "result": result, "clips": ops.summary(tl)}
