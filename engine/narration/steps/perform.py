"""Step 6 PERFORM: delivery marks per narration line, mapped in code to a TTS rate and pauses."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from engine.narration.artifacts import BeatSheet, LineMarks, PanelFacts, PerformancePlan, ScriptIR, SeriesBible
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.client import ModelClient
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps._cached import cached_call
from engine.narration.steps.factview import char_names, cues_of, panel_line
from engine.narration.steps.understand import NeedsReview

PERFORM_PROMPT_VERSION = "v1"
STEP = "perform_scene"


class MarksDraft(BaseModel):
    line: int
    emotion: str
    energy: Literal["low", "med", "high"]
    emphasis_words: list[str] = []


class SceneMarksDraft(BaseModel):
    lines: list[MarksDraft]


def marks_to_tts(draft: MarksDraft, beat_function: str, is_scene_last: bool, is_last: bool,
                 next_is_reveal: bool = False) -> tuple[float, int]:
    """(rate, pause_after_ms). The pause is 0 for the chapter's last line, otherwise within 150-800."""
    rate = 1.0
    if draft.energy == "high" or beat_function in ("escalate", "payoff"):
        rate = 1.05
    if draft.energy == "low" or beat_function == "reveal":  # shortcut: slow wins when both apply
        rate = 0.95
    rate = min(1.1, max(0.9, rate))
    if is_last:
        return rate, 0
    return rate, min(800, max(150, 650 if is_scene_last or next_is_reveal else 250))


def _problems(draft: SceneMarksDraft, n: int) -> list[str]:
    got = [d.line for d in draft.lines]
    return [] if got == list(range(1, n + 1)) else [f"need exactly one mark for each of P1..P{n}, in order; got {got}"]


async def perform(script: ScriptIR, sheet: BeatSheet, facts: list[PanelFacts], bible: SeriesBible,
                  client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache) -> PerformancePlan:
    by_panel = {f.panel_id: f for f in facts}
    names = char_names(bible, sheet, cues_of(facts))
    pos = {ln.panel_id: i for i, ln in enumerate(script.lines)}
    func = {p: b.function for s in sheet.scenes for b in s.beats for p in b.panel_ids}  # a panel in no beat is "setup"
    groups: list[list[int]] = [[] for _ in sheet.scenes]  # scene -> line indices
    for i in range(len(script.lines)):  # a line outside every scene range joins the scene before it
        k = next((k for k, s in enumerate(sheet.scenes)
                  if pos.get(s.first_panel_id, len(pos)) <= i <= pos.get(s.last_panel_id, -1)), None)
        if k is None:
            k = max((k for k, g in enumerate(groups) if g), default=0)
        groups[k].append(i)
    todo = [(s, g) for s, g in zip(sheet.scenes, groups) if g]
    prompt = load_prompt(STEP, PERFORM_PROMPT_VERSION)

    async def one(item: tuple[str, int]) -> SceneMarksDraft:
        text, n = item
        draft = await cached_call(client, cache, "writer", STEP, prompt.sha256, text, SceneMarksDraft)
        if problems := _problems(draft, n):  # the re-ask embeds its feedback, so it has its own cache key
            draft = await cached_call(client, cache, "writer", STEP, prompt.sha256,
                                      text + "\n\nFix these problems: " + "; ".join(problems), SceneMarksDraft)
            if problems := _problems(draft, n):
                raise NeedsReview(problems)
        return draft

    items = []
    for s, g in todo:
        rows = [f"P{k} | {script.lines[i].text} | {panel_line(k, by_panel[script.lines[i].panel_id], names)}"
                if script.lines[i].panel_id in by_panel else f"P{k} | {script.lines[i].text}"
                for k, i in enumerate(g, start=1)]
        items.append((prompt.render(n=str(len(g)), goal=s.goal, turn=s.turn, lines="\n".join(rows)), len(g)))
    drafts = await scheduler.map("writer", items, one)

    marks: dict[int, LineMarks] = {}
    last = len(script.lines) - 1
    for (s, g), draft in zip(todo, drafts):
        for d, i in zip(draft.lines, g):
            ln = script.lines[i]
            nxt = script.lines[i + 1].panel_id if i < last else None
            rate, pause = marks_to_tts(d, func.get(ln.panel_id, "setup"), i == g[-1], i == last,
                                       nxt is not None and func.get(nxt, "setup") == "reveal")
            stripped = (w.strip(" \t.,;:!?\"'()") for w in d.emphasis_words)
            words = [w for w in dict.fromkeys(stripped) if w and re.search(rf"\b{re.escape(w)}\b", ln.text, re.I)]
            # the last line's 0 ms pause is stored as the 150 ms floor the artifact allows
            marks[i] = LineMarks(line_id=ln.line_id, emotion=d.emotion, energy=d.energy, rate=rate,
                                 pause_after_ms=max(150, pause), emphasis_words=words)
    return PerformancePlan(project_id=script.project_id, script_revision=script.revision,
                           lines=[marks[i] for i in range(len(script.lines))])
