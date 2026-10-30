"""Autopilot's narration stage: run the compiler to the locked timeline and project it into the project."""
from __future__ import annotations

from pathlib import Path

from engine.database.models import ProjectRecord
from engine.database.session import SessionLocal
from engine.narration.__main__ import _local_provider, _make_compiler
from engine.narration.bible.store import BibleStore
from engine.narration.inputs import load_chapter_inputs
from engine.narration.project import apply_to_project


class NarrationNeedsReview(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__("Narration needs review: " + "; ".join(reasons))
        self.reasons = reasons


async def run_compiler_stage(project_id: str) -> None:
    with SessionLocal() as db:
        inputs = load_chapter_inputs(db, project_id)
        workspace = Path(db.get(ProjectRecord, project_id).workspace_path)
    provider = await _local_provider()
    if provider is None:
        raise RuntimeError("Ollama is not reachable")
    compiler = _make_compiler(provider, workspace / "narration" / "cache", BibleStore())
    res = await compiler.run(inputs, workspace, stop_after="timeline")
    if res.gate == "review":
        raise NarrationNeedsReview(res.reasons)
    if res.gate == "failed":
        raise RuntimeError("; ".join(res.reasons))
    with SessionLocal() as db:
        apply_to_project(db, project_id, res.timeline, res.script, res.beat_sheet, res.takes, workspace, res.plan)
