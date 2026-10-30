"""Review queue: chapters parked at gate `review`, line actions that write new script revisions, approval."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from engine.narration.artifacts import (
    BeatSheet, CritiqueReport, PanelFacts, ScriptIR, SeriesBible, _Strict,
)
from engine.narration.bible.store import BibleStore, apply_proposals
from engine.narration.cache import ArtifactCache
from engine.narration.compiler import _write_json
from engine.narration.runtime.client import ModelClient
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps._cached import cached_call
from engine.narration.steps.critique.rules import rule_checks
from engine.narration.steps.factview import char_names, panel_line
from engine.narration.steps.repair import (
    _FACT_REF, REPAIR_PROMPT_VERSION, REPAIR_STEP, RepairDraft, fallback_text, revise,
)

_OK = {"passed", "repaired", "fallback"}


class ReviewItem(_Strict):
    run_id: str
    project_id: str
    series_key: str = ""
    run_dir: str
    reasons: list[str]
    line_ids: list[str]
    status: Literal["pending", "approved"] = "pending"


def _item(run_dir: Path) -> ReviewItem:
    return ReviewItem.model_validate_json((run_dir / "review.json").read_text(encoding="utf-8"))


def list_pending(projects_root: Path) -> list[ReviewItem]:
    paths = sorted(Path(projects_root).glob("*/narration/*/review.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = [ReviewItem.model_validate_json(p.read_text(encoding="utf-8")) for p in paths]
    return [i for i in items if i.status == "pending"]


def _latest(run_dir: Path) -> ScriptIR:
    revs = [(int(m.group(1)), p) for p in run_dir.glob("script_r*.json") if (m := re.fullmatch(r"script_r(\d+)\.json", p.name))]
    return ScriptIR.model_validate_json(max(revs)[1].read_text(encoding="utf-8"))


def _save(run_dir: Path, script: ScriptIR) -> ScriptIR:
    payload = script.model_dump(mode="json")
    _write_json(run_dir / f"script_r{script.revision}.json", payload)
    _write_json(run_dir / "script.json", payload)
    return script


def _facts(run_dir: Path) -> dict[str, PanelFacts]:
    import json
    raw = json.loads((run_dir / "panel_facts.json").read_text(encoding="utf-8"))
    return {f["panel_id"]: PanelFacts.model_validate(f) for f in raw}


def _sheet(run_dir: Path) -> BeatSheet:
    return BeatSheet.model_validate_json((run_dir / "beat_sheet.json").read_text(encoding="utf-8"))


def _line(script: ScriptIR, line_id: str):
    for ln in script.lines:
        if ln.line_id == line_id:
            return ln
    raise ValueError(f"unknown line: {line_id}")


def edit_line(run_dir: Path, line_id: str, text: str, bibles: BibleStore | None = None) -> ScriptIR:
    run_dir, bibles = Path(run_dir), bibles or BibleStore()
    script = _latest(run_dir)
    _line(script, line_id)
    facts = _facts(run_dir)
    new = revise(script, {line_id: dict(text=" ".join(text.split()), status="passed")})
    story = [ln.panel_id for ln in new.lines]
    checks = rule_checks(new, facts, story, bibles.load(_item(run_dir).series_key))[line_id]
    failed = [f"{c.rule}: {c.reason}" for c in checks if not c.passed and c.severity == "block"]
    if failed:
        raise ValueError("; ".join(failed))
    return _save(run_dir, new)


def accept_line(run_dir: Path, line_id: str) -> ScriptIR:
    script = _latest(Path(run_dir))
    _line(script, line_id)
    return _save(Path(run_dir), revise(script, {line_id: dict(status="passed")}))


def fallback_line(run_dir: Path, line_id: str, bibles: BibleStore | None = None) -> ScriptIR:
    run_dir, bibles = Path(run_dir), bibles or BibleStore()
    script = _latest(run_dir)
    ln = _line(script, line_id)
    names = char_names(bibles.load(_item(run_dir).series_key), _sheet(run_dir))
    return _save(run_dir, revise(script, {line_id: dict(
        text=fallback_text(_facts(run_dir)[ln.panel_id], names), facts_used=["action", "characters"], status="fallback")}))


async def regenerate_line(run_dir: Path, line_id: str, hint: str, client: ModelClient, scheduler: ModelScheduler,
                          cache: ArtifactCache, bibles: BibleStore | None = None) -> ScriptIR:
    run_dir, bibles = Path(run_dir), bibles or BibleStore()
    script, facts, sheet = _latest(run_dir), _facts(run_dir), _sheet(run_dir)
    bible = bibles.load(_item(run_dir).series_key)
    at = {ln.line_id: i for i, ln in enumerate(script.lines)}
    if line_id not in at:
        raise ValueError(f"unknown line: {line_id}")
    i, ln = at[line_id], script.lines[at[line_id]]
    report = CritiqueReport.model_validate_json((run_dir / "critique.json").read_text(encoding="utf-8"))
    failures = [f"- {c.rule}: {c.reason}" for lc in report.lines if lc.line_id == line_id
                for c in lc.checks if not c.passed and c.severity == "block"]
    voice, prompt = bible.narrator_voice, load_prompt(REPAIR_STEP, REPAIR_PROMPT_VERSION)
    text = prompt.render(
        failures="\n".join([*failures, f"- reviewer hint: {hint}"]), line=ln.text,
        panel=panel_line(1, facts[ln.panel_id], char_names(bible, sheet)),
        previous=script.lines[i - 1].text if i else "(none)",
        next=script.lines[i + 1].text if i + 1 < len(script.lines) else "(none)",
        banned=", ".join(voice.banned_phrases) or "(none)", style="; ".join(voice.style_notes) or "plain, vivid recap voice")

    async def one(t: str) -> RepairDraft:
        return await cached_call(client, cache, "writer", REPAIR_STEP, prompt.sha256, t, RepairDraft)

    try:
        (draft,) = await scheduler.map("writer", [text], one)
    finally:
        await scheduler.release()
    used = [x for x in dict.fromkeys(draft.facts_used) if _FACT_REF.match(x)] or ln.facts_used
    return _save(run_dir, revise(script, {line_id: dict(text=" ".join(draft.text.split()), facts_used=used, status="repaired")}))


def approve(run_dir: Path, bibles: BibleStore) -> SeriesBible:
    run_dir = Path(run_dir)
    item = _item(run_dir)
    if item.status == "approved":
        raise ValueError("already approved")
    script = _latest(run_dir)
    open_ = [ln.line_id for ln in script.lines if ln.status not in _OK]
    if open_:
        raise ValueError(f"lines still need review: {', '.join(open_)}")
    bible = bibles.load(item.series_key)
    new, applied = apply_proposals(bible, _sheet(run_dir).bible_proposals)
    if applied:
        bible = bibles.save(new, item.project_id, applied)
    _write_json(run_dir / "script.json", script.model_dump(mode="json"))
    _write_json(run_dir / "review.json", item.model_copy(update={"status": "approved"}).model_dump(mode="json"))
    return bible
