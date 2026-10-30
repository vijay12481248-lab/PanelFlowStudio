"""NarrationCompiler: runs PERCEIVE then UNDERSTAND, writing artifacts and an atomic run log."""
from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from engine.narration.artifacts import BeatSheet, CritiqueReport, PanelFacts, ReviewItem, ScriptIR
from engine.narration.bible.store import BibleStore, apply_proposals
from engine.narration.cache import ArtifactCache
from engine.narration.inputs import ChapterInputs
from engine.narration.runtime.client import ModelClient, StepModelError
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps import perceive, repair, understand, write
from engine.narration.steps.critique import judges
from engine.narration.steps.factview import char_names, panel_line
from engine.narration.steps.understand import NeedsReview

Gate = Literal["pass", "review", "failed"]


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class RunLog:
    def __init__(self, path: Path, run_id: str = ""):
        self.path = Path(path)
        self._data = {"run_id": run_id or self.path.parent.name,
                      "started_at": datetime.now(timezone.utc).isoformat(),
                      "steps": [], "gate": None, "reasons": []}
        _write_json(self.path, self._data)

    def record(self, step: str, *, model: str, prompt_version: str, cache_hits: int,
               model_calls: int, seconds: float, status: str = "ok") -> None:
        self._data["steps"].append({"step": step, "model": model, "prompt_version": prompt_version,
                                    "cache_hits": cache_hits, "model_calls": model_calls,
                                    "seconds": round(seconds, 3), "status": status})
        _write_json(self.path, self._data)

    def finish(self, gate: Gate, reasons: list[str]) -> None:
        self._data["gate"], self._data["reasons"] = gate, list(reasons)
        _write_json(self.path, self._data)


@dataclass
class CompileResult:
    run_id: str
    gate: Gate
    reasons: list[str]
    run_dir: Path
    facts: list[PanelFacts] | None
    beat_sheet: BeatSheet | None
    script: ScriptIR | None = None
    critique: CritiqueReport | None = None


class _CountingCache:
    """Wraps a cache: a get that returns an artifact is a hit, a put is one model call."""

    def __init__(self, inner: ArtifactCache):
        self._inner = inner
        self.hits = 0
        self.calls = 0

    def get(self, step, key, model_cls):
        out = self._inner.get(step, key, model_cls)
        self.hits += out is not None
        return out

    def put(self, step, key, artifact):
        self.calls += 1
        return self._inner.put(step, key, artifact)


@contextmanager
def _recorded(log: RunLog, step: str, model: str, version: str, counter: "_CountingCache"):
    """Record the step in run.json whether it passes, needs review or fails."""
    t0, status = time.monotonic(), "failed"
    try:
        yield
        status = "ok"
    except NeedsReview:
        status = "review"
        raise
    finally:
        log.record(step, model=model, prompt_version=version, cache_hits=counter.hits,
                   model_calls=counter.calls, seconds=time.monotonic() - t0, status=status)


class NarrationCompiler:
    def __init__(self, client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache,
                 bibles: BibleStore):
        self.client, self.scheduler, self.cache, self.bibles = client, scheduler, cache, bibles

    async def run(self, inputs: ChapterInputs, workspace: Path,
                  stop_after: Literal["perceive", "understand", "write"] = "write",
                  facts_override: list[PanelFacts] | None = None) -> CompileResult:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        run_id = f"{now}-{hashlib.sha256((inputs.project_id + now).encode()).hexdigest()[:6]}"
        run_dir = Path(workspace) / "narration" / run_id
        log = RunLog(run_dir / "run.json", run_id)
        facts: list[PanelFacts] | None = None
        sheet: BeatSheet | None = None
        script: ScriptIR | None = None
        report: CritiqueReport | None = None

        def result(gate: Gate, reasons: list[str]) -> CompileResult:
            log.finish(gate, reasons)
            if gate == "review":
                blocked = {lc.line_id for lc in report.lines if lc.blocked} if report else set()
                ids = [ln.line_id for ln in script.lines if ln.line_id in blocked or ln.status in ("fallback", "needs_review")] if script else []
                _write_json(run_dir / "review.json", ReviewItem(
                    run_id=run_id, project_id=inputs.project_id, series_key=inputs.series_key, run_dir=str(run_dir),
                    reasons=list(reasons), line_ids=ids).model_dump(mode="json"))
            return CompileResult(run_id, gate, reasons, run_dir, facts, sheet, script, report)

        try:
            bible = self.bibles.load(inputs.series_key)

            if facts_override is not None:  # gold eval: hand-corrected facts replace step 1
                facts = list(facts_override)
            else:
                counter = _CountingCache(self.cache)
                with _recorded(log, "perceive", self.client.model_for("vision"),
                               perceive.PERCEIVE_PROMPT_VERSION, counter):
                    facts = await perceive.perceive_chapter(inputs, bible, self.client, self.scheduler, counter)
            _write_json(run_dir / "panel_facts.json", [f.model_dump(mode="json") for f in facts])
            if stop_after == "perceive":
                return result("pass", [])

            counter = _CountingCache(self.cache)
            with _recorded(log, "understand", self.client.model_for("planner"),
                           understand.UNDERSTAND_PROMPT_VERSION, counter):
                sheet = await understand.understand_chapter(
                    inputs.project_id, facts, bible, self.client, self.scheduler, counter)
            _write_json(run_dir / "beat_sheet.json", sheet.model_dump(mode="json"))
            if stop_after == "understand":
                return result("pass", [])

            by_id = {f.panel_id: f for f in facts}
            story_ids = [f.panel_id for f in facts if f.is_story]
            if not story_ids:
                return result("review", ["no story panels to narrate"])
            names = char_names(bible, sheet)
            args = (by_id, story_ids, sheet, bible, self.client, self.scheduler)

            counter = _CountingCache(self.cache)
            with _recorded(log, "write", self.client.model_for("writer"), write.WRITE_PROMPT_VERSION, counter):
                script, candidates = await write.write_chapter(
                    inputs.project_id, facts, sheet, bible, self.client, self.scheduler, counter)
            if not script.lines:
                return result("review", ["no story panels to narrate"])
            _write_json(run_dir / "script_r0.json", script.model_dump(mode="json"))

            counter = _CountingCache(self.cache)
            with _recorded(log, "critique", self.client.model_for("judge"), judges.CRITIQUE_PROMPT_VERSION, counter):
                report = await judges.critique(script, *args, counter)
                picks = {script.lines[0].line_id: ("hook", candidates.get("hook"))}
                if len(script.lines) > 1:
                    picks[script.lines[-1].line_id] = ("cliffhanger", candidates.get("cliffhanger"))
                swaps = {}
                for ln in script.lines:
                    if picks.get(ln.line_id, (0, None))[1]:  # no candidates: keep the written line
                        kind, cands = picks[ln.line_id]
                        swaps[ln.line_id] = dict(text=await judges.pick_best(
                            kind, cands, panel_line(1, by_id[ln.panel_id], names), self.client, self.scheduler, counter))
                script = repair.revise(script, swaps)
                report = await judges.critique(script, *args, counter, line_ids=repair.with_successors(script, list(swaps)),
                                               previous=report)

            counter = _CountingCache(self.cache)
            with _recorded(log, "repair", self.client.model_for("writer"), repair.REPAIR_PROMPT_VERSION, counter):
                fixed = await repair.repair_loop(script, report, *args, counter)
            script, report = fixed.script, fixed.report
            for rev in fixed.revisions:
                _write_json(run_dir / f"script_r{rev.revision}.json", rev.model_dump(mode="json"))
            _write_json(run_dir / "script.json", script.model_dump(mode="json"))
            _write_json(run_dir / "critique.json", report.model_dump(mode="json"))
            if fixed.gate == "review":
                return result("review", fixed.reasons)
            bible2, applied = apply_proposals(bible, sheet.bible_proposals)
            if applied:
                self.bibles.save(bible2, inputs.project_id, applied)
            return result("pass", [])
        except NeedsReview as exc:
            return result("review", exc.reasons)
        except StepModelError as exc:
            return result("failed", [f"{exc.role}: {exc.cause}"])
        except Exception as exc:
            log.finish("failed", [str(exc)])
            raise
        finally:
            await self.scheduler.release()
