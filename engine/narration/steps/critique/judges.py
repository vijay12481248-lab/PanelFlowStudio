"""Step 4 CRITIQUE, model judges (yes/no, role `judge`), pairwise picking and the gate."""
from __future__ import annotations

from itertools import permutations
from typing import Literal

from pydantic import BaseModel

from engine.narration.artifacts import (
    BeatSheet, CritiqueReport, LineCheck, LineCritique, PanelFacts, ScriptIR, SeriesBible,
)
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.client import ModelClient, StepModelError
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps._cached import cached_call
from engine.narration.steps.critique.rules import chapter_stats, rule_checks
from engine.narration.steps.factview import char_names, cues_of, panel_line

CRITIQUE_PROMPT_VERSION = "v1"
PAIR_STEP = "critique_pair"
JUDGES = ("grounded", "clear", "voice", "flow")
# Only grounding blocks: a 9B judge's style verdicts are too noisy to gate on (real Ch927 run: clear 38 %, flow 34 %).
BLOCKING_JUDGES = {"grounded"}


class Verdict(BaseModel):
    yes: bool
    reason: str


class PairVerdict(BaseModel):
    winner: Literal["A", "B"]
    reason: str


async def judge_lines(
    script: ScriptIR, line_ids: list[str] | None, facts: dict[str, PanelFacts], sheet: BeatSheet,
    bible: SeriesBible, client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache,
) -> dict[str, list[LineCheck]]:
    names = char_names(bible, sheet, cues_of(facts.values()))
    style = "; ".join(bible.narrator_voice.style_notes) or "plain, vivid recap voice"
    prompts = {n: load_prompt(f"critique_{n}", CRITIQUE_PROMPT_VERSION) for n in JUDGES}
    want = set(line_ids) if line_ids is not None else None
    scene_starts = {s.first_panel_id for s in sheet.scenes}
    items = []  # (line_id, judge name, rendered prompt)
    for i, ln in enumerate(script.lines):
        if want is not None and ln.line_id not in want:
            continue
        prev = script.lines[i - 1].text if i else "(none)"
        values = {
            "grounded": dict(line=ln.text, panel=panel_line(1, facts[ln.panel_id], names)),
            "clear": dict(previous=prev, line=ln.text),
            "voice": dict(style=style, line=ln.text),
            "flow": dict(previous=prev, line=ln.text),
        }
        # a scene's first line is meant to jump; judging its flow against the last scene only adds noise
        names_here = [n for n in JUDGES if not (n == "flow" and ln.panel_id in scene_starts)]
        items += [(ln.line_id, n, prompts[n].render(**values[n])) for n in names_here]

    async def one(item: tuple[str, str, str]) -> Verdict:
        _, name, text = item
        try:
            return await cached_call(client, cache, "judge", f"critique_{name}", prompts[name].sha256, text, Verdict)
        except StepModelError as exc:
            if "length limit" not in str(exc.cause):
                raise
            # A 9B judge sometimes loops on one line until its token cap; one stuck verdict must not fail the
            # chapter. Unjudged style checks pass; an unjudged grounding check sends the line to repair.
            return Verdict(yes=name not in BLOCKING_JUDGES, reason="judge gave no usable answer")

    out: dict[str, list[LineCheck]] = {}
    for (line_id, name, _), v in zip(items, await scheduler.map("judge", items, one)):
        out.setdefault(line_id, []).append(LineCheck(rule=name, passed=v.yes, reason=v.reason,
                                                  severity="block" if name in BLOCKING_JUDGES else "warn"))
    return out


async def pick_best(kind: str, candidates: list[str], context: str, client: ModelClient,
                    scheduler: ModelScheduler, cache: ArtifactCache) -> str:
    """Round robin over all ordered pairs; ties go to the earlier candidate."""
    prompt = load_prompt(PAIR_STEP, CRITIQUE_PROMPT_VERSION)
    items = [(a, b, prompt.render(kind=kind, context=context, a=candidates[a], b=candidates[b]))
             for a, b in permutations(range(len(candidates)), 2)]

    async def one(item: tuple[int, int, str]) -> PairVerdict | None:
        try:
            return await cached_call(client, cache, "judge", PAIR_STEP, prompt.sha256, item[2], PairVerdict)
        except StepModelError as exc:
            if "length limit" not in str(exc.cause):
                raise
            return None  # the judge looped on this pair: it scores for neither side

    score = [0] * len(candidates)
    for (a, b, _), v in zip(items, await scheduler.map("judge", items, one)):
        if v is not None:
            score[a if v.winner == "A" else b] += 1
    return candidates[score.index(max(score))]


async def critique(
    script: ScriptIR, facts: dict[str, PanelFacts], story_ids: list[str], sheet: BeatSheet, bible: SeriesBible,
    client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache, line_ids: list[str] | None = None,
    previous: CritiqueReport | None = None,
) -> CritiqueReport:
    old = {lc.line_id: lc for lc in previous.lines} if previous else {}
    judged = await judge_lines(script, line_ids, facts, sheet, bible, client, scheduler, cache)
    rules = rule_checks(script, facts, story_ids, bible)  # always recomputed: cheap, depends on neighbours
    lines = []
    for ln in script.lines:
        j = judged.get(ln.line_id) or [c for c in (old[ln.line_id].checks if ln.line_id in old else []) if c.rule in JUDGES]
        lines.append(LineCritique(line_id=ln.line_id, checks=rules[ln.line_id] + j, scores={c.rule: c.passed for c in j}))
    covered = {ln.panel_id for ln in script.lines if ln.status not in ("fallback", "needs_review")}
    pace, repetition = chapter_stats(script)
    return CritiqueReport(
        revision=script.revision, lines=lines, coverage=len(covered & set(story_ids)) / max(len(story_ids), 1),
        pace_estimate=pace, repetition=repetition,
        gate="repair" if any(lc.blocked for lc in lines) else "pass")