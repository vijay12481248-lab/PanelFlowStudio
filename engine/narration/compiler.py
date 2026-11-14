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

from engine.narration.artifacts import (
    BeatSheet, CritiqueReport, LockedTimeline, PanelFacts, PerformancePlan, ReviewItem, ScriptIR, StopPoint,
    VoiceTake,
)
from engine.narration.bible.store import BibleStore, apply_once
from engine.narration.cache import ArtifactCache
from engine.narration.casting import cast_for_script
from engine.narration.inputs import ChapterInputs
from engine.narration.ledger import TakeLedger, outdated_lines
from engine.narration.qa import QaReport, qa_report
from engine.narration.readiness import ReadinessReport, readiness
from engine.narration.stoppoints import add_stop_point
from engine.narration.runtime.audio import KokoroTts, Stt, Tts, WhisperStt, get_default_tts, release_audio_models
from engine.narration.runtime.client import ModelClient, StepModelError
from engine.narration.runtime.roles import load_stt_config, load_tts_config
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps import perceive, perform, repair, timeline, understand, voice, write
from engine.narration.steps.critique import judges
from engine.narration.steps.factview import char_names, cues_of, panel_line
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

    @classmethod
    def resume(cls, path: Path) -> "RunLog":
        """Re-open a finished run's log so later steps append to it."""
        log = cls.__new__(cls)
        log.path = Path(path)
        log._data = json.loads(log.path.read_text(encoding="utf-8"))
        return log

    def finish(self, gate: Gate, reasons: list[str]) -> None:
        self._data["gate"], self._data["reasons"] = gate, list(reasons)
        _write_json(self.path, self._data)


def _brief_stop_points(run_dir: Path, sheet: BeatSheet) -> None:
    """The beats the analyst is unsure about: the workflow pauses for the owner on them."""
    for beat in understand.uncertain_beats(sheet):
        add_stop_point(run_dir, StopPoint(
            kind="brief",
            detail=beat.uncertain or f"{beat.beat_id} is read with low confidence",
            line_ids=list(beat.panel_ids),
            options=["accept as read", "edit the beat", "leave for later"],
        ))


def _casting_stop_points(run_dir: Path, cast_plan) -> None:
    """The casting decisions the workflow pauses for."""
    # a proposed voice that would replace an assignment the owner made pauses for them
    for change in cast_plan.changes:
        add_stop_point(run_dir, StopPoint(
            kind="casting",
            detail=f"{change.character_id} is cast to {change.profile_id}, not the voice already chosen",
            character_ids=[change.character_id],
            options=["keep the current voice", "use the proposed voice"],
        ))
    # a character with no voice yet needs one approved before it can be read
    for rec in cast_plan.recommendations:
        add_stop_point(run_dir, StopPoint(
            kind="voice",
            detail=f"{rec.character_id} has no voice yet; {rec.profile_id} is proposed",
            character_ids=[rec.character_id],
            options=["use the proposed voice", "choose another"],
        ))


def _readiness(run_dir: Path, script: ScriptIR, takes: list[VoiceTake] | None, cast_plan) -> ReadinessReport:
    """What is still open before the project renders."""
    qa: dict[str, QaReport] = {}
    try:
        raw = json.loads((run_dir / "qa.json").read_text(encoding="utf-8"))
        qa = {lid: QaReport.model_validate(r) for lid, r in raw.items()}
    except (ValueError, KeyError, TypeError, OSError):
        qa = {}
    outdated: list[str] = []
    try:
        plan = PerformancePlan.model_validate_json((run_dir / "performance.json").read_text(encoding="utf-8"))
    except (ValueError, OSError):
        plan = None
    try:
        raw = json.loads((run_dir / "casting.json").read_text(encoding="utf-8"))
        profiles = {a["character_id"]: a["profile_id"] for a in raw.get("assignments", [])}
    except (ValueError, KeyError, TypeError, OSError):
        profiles = {}
    if takes:
        ledger = TakeLedger(script, direction_revision=plan.revision if plan else script.revision,
                            voice_profile_ids=profiles)
        outdated = outdated_lines(takes, ledger)
    return readiness(script, takes, qa, cast_plan, outdated)


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
    timeline: LockedTimeline | None = None
    sync: dict | None = None
    plan: PerformancePlan | None = None
    takes: list[VoiceTake] | None = None
    readiness: ReadinessReport | None = None


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
                 bibles: BibleStore, tts: Tts | None = None, stt: Stt | None = None):
        self.client, self.scheduler, self.cache, self.bibles = client, scheduler, cache, bibles
        self.tts, self.stt = tts, stt

    async def continue_run(self, run_dir: Path, inputs: ChapterInputs, workspace: Path) -> CompileResult:
        """Finish an approved review run: perform, voice, timeline. The bible was already applied by approve."""
        run_dir = Path(run_dir)
        log = RunLog.resume(run_dir / "run.json")
        script = ScriptIR.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
        sheet = BeatSheet.model_validate_json((run_dir / "beat_sheet.json").read_text(encoding="utf-8"))
        facts = [PanelFacts.model_validate(f) for f in json.loads((run_dir / "panel_facts.json").read_text(encoding="utf-8"))]
        story_ids = [f.panel_id for f in facts if f.is_story]
        plan = takes = tl = sync = None
        ready: ReadinessReport | None = None
        _brief_stop_points(run_dir, sheet)

        def result(gate: Gate, reasons: list[str]) -> CompileResult:
            log.finish(gate, reasons)
            return CompileResult(run_dir.name, gate, reasons, run_dir, facts, sheet, script, None, tl, sync, plan, takes, ready)

        try:
            bible = self.bibles.load(inputs.series_key)
            if (run_dir / "performance.json").exists():  # a voice review already has its plan
                plan = PerformancePlan.model_validate_json((run_dir / "performance.json").read_text(encoding="utf-8"))
            else:
                counter = _CountingCache(self.cache)
                with _recorded(log, "perform", self.client.model_for("writer"), perform.PERFORM_PROMPT_VERSION, counter):
                    plan = await perform.perform(script, sheet, facts, bible, self.client, self.scheduler, counter)
                _write_json(run_dir / "performance.json", plan.model_dump(mode="json"))

            await self.scheduler.release()  # the LLM leaves the GPU before Kokoro arrives
            tts_cfg = load_tts_config()
            audio_model = f"{tts_cfg.model} + {load_stt_config().model}"
            heard = {}  # voice review: takes the owner listened to; audio_path is keyed on the line text, so an edited line differs
            if (run_dir / "takes.json").exists():
                heard = {t["line_id"]: t["audio_path"] for t in json.loads((run_dir / "takes.json").read_text(encoding="utf-8"))}
            cast_plan, cast_voices = cast_for_script(inputs.series_key, bible, script)
            _write_json(run_dir / "casting.json", cast_plan.model_dump(mode="json"))
            _casting_stop_points(run_dir, cast_plan)
            ledger = TakeLedger(script, direction_revision=plan.revision,
                                voice_profile_ids={a.character_id: a.profile_id for a in cast_plan.assignments},
                                provider=tts_cfg.model)
            with _recorded(log, "voice", audio_model, "-", _CountingCache(self.cache)):
                takes, reasons = await voice.voice_lines(  # cached takes cost no synthesis; an edited line is voiced fresh
                    script, plan, bible, self.tts or get_default_tts(), self.stt or WhisperStt(),
                    Path(workspace) / "narration" / "voice", tts_cfg.voice, facts, cast_voices, ledger)
                takes = [t.model_copy(update={"flagged": False}) if heard.get(t.line_id) == t.audio_path else t for t in takes]
                if heard:
                    n = sum(t.flagged for t in takes)
                    reasons = [f"{n} of {len(takes)} takes failed the speech check"] if n > voice.FLAG_LIMIT * len(takes) else []
                _write_json(run_dir / "takes.json", [t.model_dump(mode="json") for t in takes])
                _write_json(run_dir / "qa.json", {lid: r.model_dump(mode="json") for lid, r in
                                                  qa_report(takes, {ln.line_id: ln.text for ln in script.lines}).items()})
                if reasons:
                    raise NeedsReview(reasons)

            with _recorded(log, "timeline", audio_model, "-", _CountingCache(self.cache)):
                tl = timeline.lock_timeline(script, plan, takes, sheet, story_ids)
                sync = timeline.sync_metrics(tl, takes, script)
            _write_json(run_dir / "timeline.json", tl.model_dump(mode="json"))
            _write_json(run_dir / "sync.json", sync)
            ready = _readiness(run_dir, script, takes, cast_plan)
            _write_json(run_dir / "readiness.json", ready.model_dump(mode="json"))
            return result("pass", [])
        except NeedsReview as exc:  # voiced now and still bad: park it again for another look
            flagged = {t.line_id for t in takes or [] if t.flagged}
            _write_json(run_dir / "review.json", ReviewItem(
                run_id=run_dir.name, project_id=inputs.project_id, series_key=inputs.series_key, run_dir=str(run_dir),
                reasons=list(exc.reasons), line_ids=[ln.line_id for ln in script.lines if ln.line_id in flagged],
            ).model_dump(mode="json"))
            return result("review", exc.reasons)
        except StepModelError as exc:
            return result("failed", [f"{exc.role}: {exc.cause}"])
        except Exception as exc:
            log.finish("failed", [str(exc)])
            raise
        finally:
            await self.scheduler.release()
            release_audio_models()

    async def run(self, inputs: ChapterInputs, workspace: Path,
                  stop_after: Literal["perceive", "understand", "write", "perform", "voice", "timeline"] = "timeline",
                  facts_override: list[PanelFacts] | None = None) -> CompileResult:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        run_id = f"{now}-{hashlib.sha256((inputs.project_id + now).encode()).hexdigest()[:6]}"
        run_dir = Path(workspace) / "narration" / run_id
        log = RunLog(run_dir / "run.json", run_id)
        facts: list[PanelFacts] | None = None
        sheet: BeatSheet | None = None
        script: ScriptIR | None = None
        report: CritiqueReport | None = None
        plan: PerformancePlan | None = None
        takes: list[VoiceTake] | None = None
        tl: LockedTimeline | None = None
        sync: dict | None = None
        ready: ReadinessReport | None = None

        def result(gate: Gate, reasons: list[str]) -> CompileResult:
            log.finish(gate, reasons)
            if gate == "review":
                blocked = {lc.line_id for lc in report.lines if lc.blocked} if report else set()
                blocked |= {t.line_id for t in takes or [] if t.flagged}
                ids = [ln.line_id for ln in script.lines if ln.line_id in blocked or ln.status in ("fallback", "needs_review")] if script else []
                _write_json(run_dir / "review.json", ReviewItem(
                    run_id=run_id, project_id=inputs.project_id, series_key=inputs.series_key, run_dir=str(run_dir),
                    reasons=list(reasons), line_ids=ids).model_dump(mode="json"))
            return CompileResult(run_id, gate, reasons, run_dir, facts, sheet, script, report, tl, sync, plan, takes, ready)

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
            _brief_stop_points(run_dir, sheet)
            if stop_after == "understand":
                return result("pass", [])

            by_id = {f.panel_id: f for f in facts}
            story_ids = [f.panel_id for f in facts if f.is_story]
            if not story_ids:
                return result("review", ["no story panels to narrate"])
            names = char_names(bible, sheet, cues_of(facts))
            args = (by_id, story_ids, sheet, bible, self.client, self.scheduler)

            counter = _CountingCache(self.cache)
            with _recorded(log, "write", self.client.model_for("writer"), write.WRITE_PROMPT_VERSION, counter):
                script, candidates = await write.write_chapter(
                    inputs.project_id, facts, sheet, bible, self.client, self.scheduler, counter)
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

            def passed() -> CompileResult:  # the chapter is approved only now, so only now does the bible learn from it
                bible2, applied = apply_once(bible, sheet.bible_proposals, inputs.project_id)
                if applied:
                    self.bibles.save(bible2, inputs.project_id, applied)
                return result("pass", [])

            if stop_after == "write":
                return passed()

            counter = _CountingCache(self.cache)
            with _recorded(log, "perform", self.client.model_for("writer"), perform.PERFORM_PROMPT_VERSION, counter):
                plan = await perform.perform(script, sheet, facts, bible, self.client, self.scheduler, counter)
            _write_json(run_dir / "performance.json", plan.model_dump(mode="json"))
            if stop_after == "perform":
                return passed()

            await self.scheduler.release()  # the LLM leaves the GPU before Kokoro arrives
            tts_cfg = load_tts_config()
            audio_model = f"{tts_cfg.model} + {load_stt_config().model}"
            cast_plan, cast_voices = cast_for_script(inputs.series_key, bible, script)
            _write_json(run_dir / "casting.json", cast_plan.model_dump(mode="json"))
            _casting_stop_points(run_dir, cast_plan)
            ledger = TakeLedger(script, direction_revision=plan.revision,
                                voice_profile_ids={a.character_id: a.profile_id for a in cast_plan.assignments},
                                provider=tts_cfg.model)
            with _recorded(log, "voice", audio_model, "-", _CountingCache(self.cache)):
                takes, reasons = await voice.voice_lines(
                    script, plan, bible, self.tts or get_default_tts(), self.stt or WhisperStt(),
                    Path(workspace) / "narration" / "voice", tts_cfg.voice, facts, cast_voices, ledger)
                _write_json(run_dir / "takes.json", [t.model_dump(mode="json") for t in takes])
                _write_json(run_dir / "qa.json", {lid: r.model_dump(mode="json") for lid, r in
                                                  qa_report(takes, {ln.line_id: ln.text for ln in script.lines}).items()})
                if reasons:
                    raise NeedsReview(reasons)
            if stop_after == "voice":
                return passed()

            with _recorded(log, "timeline", audio_model, "-", _CountingCache(self.cache)):
                tl = timeline.lock_timeline(script, plan, takes, sheet, story_ids)
                sync = timeline.sync_metrics(tl, takes, script)
            _write_json(run_dir / "timeline.json", tl.model_dump(mode="json"))
            _write_json(run_dir / "sync.json", sync)
            ready = _readiness(run_dir, script, takes, cast_plan)
            _write_json(run_dir / "readiness.json", ready.model_dump(mode="json"))
            return passed()
        except NeedsReview as exc:
            return result("review", exc.reasons)
        except StepModelError as exc:
            return result("failed", [f"{exc.role}: {exc.cause}"])
        except Exception as exc:
            log.finish("failed", [str(exc)])
            raise
        finally:
            await self.scheduler.release()
            release_audio_models()
