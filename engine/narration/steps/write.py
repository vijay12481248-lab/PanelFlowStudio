"""Step 3 WRITE: one narration line per story panel, written per scene (chunks of at most 30 panels)."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from engine.narration.artifacts import (
    BeatSheet, PanelFacts, ScriptIR, ScriptLine, SeriesBible, check_script_ids,
)
from engine.narration.cache import ArtifactCache, cache_key
from engine.narration.runtime.client import ModelClient, guard_prompt
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.factview import load_fewshot, panel_line
from engine.narration.steps.understand import NeedsReview

WRITE_PROMPT_VERSION = "v1"
SCENE_STEP = "write_scene"
CANDIDATE_STEP = "write_candidates"
CHUNK = 30
_FACT_REF = re.compile(r"^(action|emotion|dialogue|characters|setting|sfx|beat:[A-Za-z0-9_-]+)$")


class LineDraft(BaseModel):
    panel: int
    text: str
    facts_used: list[str] = Field(default_factory=list)
    kind: Literal["narration", "paraphrase", "transition"] = "narration"


class SceneLinesDraft(BaseModel):
    lines: list[LineDraft]


class CandidatesDraft(BaseModel):
    candidates: list[str] = Field(min_length=3, max_length=3)


def _problems(draft: SceneLinesDraft, n: int) -> list[str]:
    """Check a chunk answer against P1..Pn; panel ids here are the chunk-local labels."""
    if not draft.lines:
        return ["no lines returned"]
    try:
        script = ScriptIR(project_id="chunk", lines=[
            ScriptLine(line_id=f"T{i}", panel_id=f"P{d.panel}", text=d.text, facts_used=[], kind=d.kind)
            for i, d in enumerate(draft.lines)])
    except ValueError:
        return ["every line needs non-empty text"]
    out = check_script_ids(script, [f"P{k}" for k in range(1, n + 1)])
    if out:
        got = {d.panel for d in draft.lines}
        out += [f"P{k} has no line" for k in range(1, n + 1) if k not in got]
    return out


async def write_chapter(
    project_id: str, facts: list[PanelFacts], sheet: BeatSheet, bible: SeriesBible,
    client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache,
) -> tuple[ScriptIR, dict[str, list[str]]]:
    story = [f for f in facts if f.is_story]
    if not story:
        raise NeedsReview(["no story panels"])
    pos = {f.panel_id: i for i, f in enumerate(story)}
    names = {c.id: c.name for c in bible.characters}
    names.update({u: names[c] for u, c in sheet.character_resolutions.items() if c in names})
    model, params = client.model_for("writer"), client.params_for("writer")
    voice = bible.narrator_voice
    common = dict(
        style="; ".join(voice.style_notes) or "plain, vivid recap voice",
        banned=", ".join(voice.banned_phrases) or "(none)",
        examples="\n".join(f"facts: {r['facts']}\nline: {r['line']}" for r in load_fewshot()[:6]),
    )

    async def cached(step: str, sha: str, text: str, schema: type[BaseModel]):
        key = cache_key(step, {"prompt": text}, sha, model, params)
        hit = cache.get(step, key, schema)
        if hit is not None:
            return hit
        guard_prompt(client, "writer", text)
        out = await client.structured("writer", text, schema)
        cache.put(step, key, out)
        return out

    sprompt = load_prompt(SCENE_STEP, WRITE_PROMPT_VERSION)

    async def write_chunk(item: tuple[str, int]) -> SceneLinesDraft:
        text, n = item
        draft = await cached(SCENE_STEP, sprompt.sha256, text, SceneLinesDraft)
        problems = _problems(draft, n)
        if problems:  # the re-ask embeds its feedback, so it has its own cache key
            draft = await cached(SCENE_STEP, sprompt.sha256,
                                 text + "\n\nFix these problems: " + "; ".join(problems), SceneLinesDraft)
            problems = _problems(draft, n)
            if problems:
                raise NeedsReview(problems)
        return draft

    chunks = []  # (scene, story positions in the chunk)
    for s in sheet.scenes:
        idx = list(range(pos[s.first_panel_id], pos[s.last_panel_id] + 1))
        chunks.append([(s, idx[i:i + CHUNK]) for i in range(0, len(idx), CHUNK)])
    text_of: dict[int, str] = {}  # story position -> written line
    kinds: dict[int, str] = {}
    used: dict[int, list[str]] = {}
    for rnd in range(max(len(c) for c in chunks)):  # round r writes chunk r of every scene; it needs chunk r-1
        todo = [c[rnd] for c in chunks if rnd < len(c)]
        prompts = []
        for s, idx in todo:
            lo = {p: i for i, p in enumerate(idx)}
            beats = []
            for b in s.beats:
                local = [lo[pos[p]] + 1 for p in b.panel_ids if pos[p] in lo]
                if local:
                    beats.append(f"beat:{b.beat_id} P{min(local)}-P{max(local)}: {b.what_happens}")
            prev = [text_of[i] for i in range(idx[0] - 3, idx[0]) if i in text_of] if rnd else []
            prompts.append((sprompt.render(
                n=str(len(idx)), goal=s.goal, turn=s.turn, beats="\n".join(beats) or "(none)",
                previous="\n".join(prev) or "(none)",
                panels="\n".join(panel_line(k, story[i], names) for k, i in enumerate(idx, start=1)),
                **common), len(idx)))
        for (s, idx), draft in zip(todo, await scheduler.map("writer", prompts, write_chunk)):
            for d in draft.lines:
                i = idx[d.panel - 1]
                text_of[i], kinds[i] = " ".join(d.text.split()), d.kind
                used[i] = list(dict.fromkeys(f for f in d.facts_used if _FACT_REF.match(f)))

    lines = [ScriptLine(line_id=f"L{i + 1:03d}", panel_id=f.panel_id, text=text_of[i], facts_used=used[i],
                        kind="hook" if i == 0 else "cliffhanger" if i == len(story) - 1 else kinds[i])
             for i, f in enumerate(story) if i in text_of]
    script = ScriptIR(project_id=project_id, lines=lines)
    if problems := check_script_ids(script, [f.panel_id for f in story]):
        raise NeedsReview(problems)

    cprompt = load_prompt(CANDIDATE_STEP, WRITE_PROMPT_VERSION)
    moments = [("hook", "opening hook", story[0], sheet.hook),
               ("cliffhanger", "closing cliffhanger", story[-1], sheet.scenes[-1].turn)]
    texts = [cprompt.render(kind=label, seed=seed, panel=panel_line(1, f, names), **common)
             for _, label, f, seed in moments]
    drafts = await scheduler.map("writer", texts, lambda t: cached(CANDIDATE_STEP, cprompt.sha256, t, CandidatesDraft))
    return script, {name: d.candidates for (name, *_), d in zip(moments, drafts)}
