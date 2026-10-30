"""NarrationCompiler: runs PERCEIVE then UNDERSTAND, writing artifacts and an atomic run log."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from engine.narration.artifacts import BeatSheet, PanelFacts
from engine.narration.bible.store import BibleStore
from engine.narration.cache import ArtifactCache
from engine.narration.inputs import ChapterInputs
from engine.narration.runtime.client import ModelClient, StepModelError
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps import perceive, understand
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
               model_calls: int, seconds: float) -> None:
        self._data["steps"].append({"step": step, "model": model, "prompt_version": prompt_version,
                                    "cache_hits": cache_hits, "model_calls": model_calls,
                                    "seconds": round(seconds, 3)})
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


class NarrationCompiler:
    def __init__(self, client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache,
                 bibles: BibleStore):
        self.client, self.scheduler, self.cache, self.bibles = client, scheduler, cache, bibles

    async def run(self, inputs: ChapterInputs, workspace: Path,
                  stop_after: Literal["perceive", "understand"] = "understand") -> CompileResult:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        run_id = f"{now}-{hashlib.sha256((inputs.project_id + now).encode()).hexdigest()[:6]}"
        run_dir = Path(workspace) / "narration" / run_id
        log = RunLog(run_dir / "run.json", run_id)
        facts: list[PanelFacts] | None = None
        sheet: BeatSheet | None = None

        def result(gate: Gate, reasons: list[str]) -> CompileResult:
            log.finish(gate, reasons)
            return CompileResult(run_id, gate, reasons, run_dir, facts, sheet)

        try:
            bible = self.bibles.load(inputs.series_key)

            counter, t0 = _CountingCache(self.cache), time.monotonic()
            facts = await perceive.perceive_chapter(inputs, bible, self.client, self.scheduler, counter)
            log.record("perceive", model=self.client.model_for("vision"),
                       prompt_version=perceive.PERCEIVE_PROMPT_VERSION, cache_hits=counter.hits,
                       model_calls=counter.calls, seconds=time.monotonic() - t0)
            _write_json(run_dir / "panel_facts.json", [f.model_dump(mode="json") for f in facts])
            if stop_after == "perceive":
                return result("pass", [])

            counter, t0 = _CountingCache(self.cache), time.monotonic()
            sheet = await understand.understand_chapter(
                inputs.project_id, facts, bible, self.client, self.scheduler, counter)
            log.record("understand", model=self.client.model_for("planner"),
                       prompt_version=understand.UNDERSTAND_PROMPT_VERSION, cache_hits=counter.hits,
                       model_calls=counter.calls, seconds=time.monotonic() - t0)
            _write_json(run_dir / "beat_sheet.json", sheet.model_dump(mode="json"))
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
