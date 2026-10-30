"""Step 5 REPAIR: rewrite blocked lines (writer), re-judge only what changed, then fall back to plain facts."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from engine.narration.artifacts import (
    BeatSheet, CritiqueReport, LineCritique, LineCheck, PanelFacts, ScriptIR, SeriesBible,
)
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.client import ModelClient
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps._cached import cached_call
from engine.narration.steps.critique.judges import JUDGES, critique
from engine.narration.steps.factview import FACT_REF, char_names, display_name, normalize_facts, panel_line

REPAIR_PROMPT_VERSION = "v1"
REPAIR_STEP = "repair_line"
MAX_ROUNDS = 2
FALLBACK_LIMIT = 0.10
_UNKNOWN = re.compile(r"unknown_\d+")


class RepairDraft(BaseModel):
    text: str
    facts_used: list[str] = Field(default_factory=list)


@dataclass
class RepairResult:
    script: ScriptIR
    report: CritiqueReport
    gate: Literal["pass", "review"]
    reasons: list[str]
    revisions: list[ScriptIR]  # the input script first, then every revision written


def fallback_text(f: PanelFacts, names: dict[str, str]) -> str:
    ids = sorted({*f.characters_visible, *_UNKNOWN.findall(f.action)}, key=len, reverse=True)
    text = f.action
    if ids:
        text = re.sub(r"\b(?:" + "|".join(map(re.escape, ids)) + r")\b", lambda m: display_name(m.group(), names), text)
    text = " ".join(" ".join(text.split()[:12]).rstrip(".!?,;: ").split())
    if not text:
        raise ValueError("panel has no action to fall back to")
    return text[0].upper() + text[1:] + "."


def with_successors(script: ScriptIR, ids: list[str]) -> list[str]:
    """Changed lines plus the line after each: its clear and flow judges read the line before it."""
    want = set(ids)
    return [ln.line_id for i, ln in enumerate(script.lines)
            if ln.line_id in want or (i and script.lines[i - 1].line_id in want)]


def revise(script: ScriptIR, new: dict[str, dict]) -> ScriptIR:
    lines = [ln.model_copy(update=new[ln.line_id]) if ln.line_id in new else ln for ln in script.lines]
    return ScriptIR(project_id=script.project_id, revision=script.revision + 1, parent_revision=script.revision,
                    changed_line_ids=list(new), lines=lines)


async def repair_loop(
    script: ScriptIR, report: CritiqueReport, facts: dict[str, PanelFacts], story_ids: list[str], sheet: BeatSheet,
    bible: SeriesBible, client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache,
) -> RepairResult:
    names = char_names(bible, sheet)
    voice = bible.narrator_voice
    prompt = load_prompt(REPAIR_STEP, REPAIR_PROMPT_VERSION)
    common = dict(banned=", ".join(voice.banned_phrases) or "(none)",
                  style="; ".join(voice.style_notes) or "plain, vivid recap voice")
    revisions, cur, rep = [script], script, report

    async def one(text: str) -> RepairDraft:
        return await cached_call(client, cache, "writer", REPAIR_STEP, prompt.sha256, text, RepairDraft)

    for _ in range(MAX_ROUNDS):
        blocked = {lc.line_id: lc for lc in rep.lines if lc.blocked}
        if not blocked:
            break
        at = {ln.line_id: i for i, ln in enumerate(cur.lines)}
        texts = []
        for lid, lc in blocked.items():
            i = at[lid]
            failures = "\n".join(f"- {c.rule}: {c.reason}" for c in lc.checks if not c.passed and c.severity == "block")
            texts.append(prompt.render(
                failures=failures, line=cur.lines[i].text, panel=panel_line(1, facts[cur.lines[i].panel_id], names),
                previous=cur.lines[i - 1].text if i else "(none)",
                next=cur.lines[i + 1].text if i + 1 < len(cur.lines) else "(none)", **common))
        drafts = await scheduler.map("writer", texts, one)
        new = {}
        for lid, d in zip(blocked, drafts):
            used = [x for x in normalize_facts(d.facts_used) if FACT_REF.match(x)] or cur.lines[at[lid]].facts_used
            new[lid] = dict(text=" ".join(d.text.split()), facts_used=used, status="repaired")
        cur = revise(cur, new)
        revisions.append(cur)
        rep = await critique(cur, facts, story_ids, sheet, bible, client, scheduler, cache,
                             line_ids=with_successors(cur, list(new)), previous=rep)

    fallen = [lc.line_id for lc in rep.lines if lc.blocked]
    if fallen:
        by_panel = {ln.line_id: ln.panel_id for ln in cur.lines}
        new, stuck = {}, set()  # stuck: no action to fall back to; the line keeps its failing text and goes to review
        for lid in fallen:
            try:
                new[lid] = dict(text=fallback_text(facts[by_panel[lid]], names), facts_used=["action", "characters"],
                                status="fallback")
            except ValueError:
                new[lid] = dict(status="needs_review")
                stuck.add(lid)
        cur = revise(cur, new)
        revisions.append(cur)
        rep = await critique(cur, facts, story_ids, sheet, bible, client, scheduler, cache, line_ids=[], previous=rep)
        # fact-only text is not judged and may be short, but every other rule still applies to it
        rep = rep.model_copy(update={"lines": [
            LineCritique(line_id=lc.line_id, checks=[c for c in lc.checks if c.rule not in (*JUDGES, "word_budget")])
            if lc.line_id in fallen and lc.line_id not in stuck else lc for lc in rep.lines]})
        broken = sum(lc.blocked or lc.line_id in stuck for lc in rep.lines if lc.line_id in fallen)
    else:
        broken = 0
    final = cur.model_copy(update={"lines": [
        ln if ln.status != "draft" else ln.model_copy(update={"status": "passed"}) for ln in cur.lines]})
    revisions[-1] = final
    reasons = [f"{len(fallen)} of {len(final.lines)} lines fell back to facts"] if len(fallen) / len(final.lines) > FALLBACK_LIMIT else []
    if broken:
        reasons.append(f"{broken} fallback lines still break rules")
    review = bool(reasons)
    rep = rep.model_copy(update={"gate": "review" if review else "pass", "gate_reasons": reasons})
    return RepairResult(final, rep, "review" if review else "pass", reasons, revisions)
