"""Step 2 UNDERSTAND: windowed scene/beat planning stitched in code, then one merge call."""
from __future__ import annotations

from typing import Callable, Literal

from pydantic import BaseModel, Field

from engine.narration.artifacts import (
    ArtifactIdError, Beat, BeatSheet, BibleProposal, PanelFacts, Scene, SeriesBible, assert_known_ids,
)
from engine.narration.cache import ArtifactCache, cache_key
from engine.narration.runtime.client import ModelClient, guard_prompt
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler

UNDERSTAND_PROMPT_VERSION = "v1"
WINDOW_STEP = "understand_window"
MERGE_STEP = "understand_merge"


class NeedsReview(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class WindowBeatDraft(BaseModel):
    panels: list[int] = Field(min_length=1)
    what_happens: str
    function: Literal["setup", "escalate", "reveal", "payoff", "cliffhanger"]
    intensity: float = Field(ge=0, le=1)


class WindowSceneDraft(BaseModel):
    first: int
    last: int
    goal: str
    conflict: str
    turn: str
    beats: list[WindowBeatDraft] = Field(min_length=1)


class WindowDraft(BaseModel):
    scenes: list[WindowSceneDraft] = Field(min_length=1)


class NewCharacter(BaseModel):
    name: str
    description: str = ""
    unknown_ids: list[str] = Field(default_factory=list)  # unknown_<n> labels that are this person


class NewThread(BaseModel):
    text: str


class MergeDraft(BaseModel):
    hook: str
    chapter_summary: str
    character_resolutions: dict[str, str]  # unknown label -> EXISTING bible id only
    new_characters: list[NewCharacter] = Field(default_factory=list)
    new_threads: list[NewThread] = Field(default_factory=list)
    plot_update: str | None = None


def windows(n: int, size: int = 30, overlap: int = 5) -> list[tuple[int, int]]:
    out, start = [], 0
    while start < n:
        end = min(start + size, n)
        out.append((start, end))
        if end == n:
            break
        start += size - overlap
    return out


def stitch_windows(
    spans: list[tuple[int, int]], drafts: list[WindowDraft], overlap: int = 5,
) -> list[WindowSceneDraft]:
    out = []
    for k, draft in enumerate(drafts):
        # kept range in 1-based panel numbers; cut between windows at m + 1, m = next start + overlap // 2
        lo = spans[k][0] + 1 if k == 0 else spans[k][0] + overlap // 2 + 1
        hi = spans[k][1] if k == len(spans) - 1 else spans[k + 1][0] + overlap // 2
        for s in draft.scenes:
            first, last = max(s.first, lo), min(s.last, hi)
            beats = [b.model_copy(update={"panels": kept}) for b in s.beats
                     if (kept := [p for p in b.panels if first <= p <= last])]
            if first <= last and beats:
                out.append(normalize_beats(s.model_copy(update={"first": first, "last": last, "beats": beats})))
    return sorted(out, key=lambda s: s.first)


def normalize_beats(scene: WindowSceneDraft) -> WindowSceneDraft:
    """Small models interleave beat panels; make beats contiguous ranges in reading order."""
    starts = [min(max(min(b.panels), scene.first), scene.last) for b in scene.beats]
    order = sorted(range(len(scene.beats)), key=lambda i: starts[i])  # stable: ties keep model order
    beats = []
    for n, i in enumerate(order):
        lo = scene.first if n == 0 else starts[i]
        hi = scene.last if n == len(order) - 1 else starts[order[n + 1]] - 1
        if lo <= hi:
            beats.append(scene.beats[i].model_copy(update={"panels": list(range(lo, hi + 1))}))
    return scene.model_copy(update={"beats": beats})


def _problems(
    scenes: list[Scene], resolutions: dict[str, str], ids: list[str], bible: SeriesBible,
    label: Callable[[str], str],
) -> list[tuple[str, set[str]]]:
    """(message, panel ids it concerns); label renders a panel id for the message."""
    bible_ids = {c.id for c in bible.characters}
    out = [(f"character_resolutions {k} -> {v} is not a bible id", set())
           for k, v in resolutions.items() if v not in bible_ids]
    try:
        assert_known_ids([p for s in scenes for p in (s.first_panel_id, s.last_panel_id,
                                                      *(x for b in s.beats for x in b.panel_ids))],
                         set(ids), "beat sheet")
    except ArtifactIdError as exc:
        return out + [(str(exc), set())]
    pos = {p: i for i, p in enumerate(ids)}
    cover, prev = [0] * len(ids), None
    for s in scenes:
        a, b = pos[s.first_panel_id], pos[s.last_panel_id]
        rng = f"{label(s.first_panel_id)}-{label(s.last_panel_id)}"
        if a > b:
            out.append((f"scene {rng} ends before it starts", {s.first_panel_id, s.last_panel_id}))
            continue
        if prev is not None and a != prev + 1:
            out.append((f"scene {rng} does not directly follow the scene ending at {label(ids[prev])}",
                        {ids[prev], s.first_panel_id}))
        for i in range(a, b + 1):
            cover[i] += 1
        prev, beat_end = b, -1
        for beat in s.beats:
            ps = [pos[p] for p in beat.panel_ids]
            outside = [label(p) for p in beat.panel_ids if not a <= pos[p] <= b]
            if outside:
                out.append((f"beat cites {', '.join(outside)} outside its scene {rng}", set(beat.panel_ids)))
            if ps != sorted(ps) or ps[0] < beat_end:
                out.append((f"beat at {label(beat.panel_ids[0])} is out of order in scene {rng}",
                            set(beat.panel_ids)))
            beat_end = max(beat_end, *ps)
    for i, c in enumerate(cover):
        if c == 0:
            out.append((f"panel {label(ids[i])} is in no scene", {ids[i]}))
        elif c > 1:
            out.append((f"panel {label(ids[i])} is in {c} scenes", {ids[i]}))
    return out


def check_beat_sheet(sheet: BeatSheet, story_panel_ids: list[str], bible: SeriesBible) -> list[str]:
    return [m for m, _ in _problems(sheet.scenes, sheet.character_resolutions, story_panel_ids, bible, str)]


def _line(text: str) -> str:
    return " ".join(text.split())


def _proposals(
    merge: MergeDraft, bible: SeriesBible, unknowns: dict[str, str], facts: list[PanelFacts],
) -> tuple[list[BibleProposal], dict[str, str]]:
    """Typed draft -> BibleProposals with code-made ids; also unknowns the draft re-found in the bible."""
    by_name = {_line(n).casefold(): c.id for c in bible.characters for n in (c.name, *c.aliases)}
    taken, claimed, proposed, found, out = {c.id for c in bible.characters}, set(), {}, {}, []
    n = 0
    page = {_line(x).casefold() for f in facts for x in f.names_mentioned}
    text = ' '.join(f'{f.action} {f.setting} ' + ' '.join(f.names_mentioned) + ' ' + ' '.join(d.text for d in f.dialogue) for f in facts).casefold()
    for nc in merge.new_characters:
        name = _line(nc.name)
        if not name:
            continue
        ids = [u for u in dict.fromkeys(nc.unknown_ids) if u in unknowns and u not in claimed]
        if name.casefold() in by_name:  # already known: its unknowns resolve to that existing id
            found.update({u: by_name[name.casefold()] for u in ids})
            claimed.update(ids)
            continue
        # a new person must be named on the page; descriptive inventions are dropped
        if name.casefold() not in page or not all(w in text for w in name.casefold().split()):
            continue
        claimed.update(ids)
        if name.casefold() in proposed:  # same person listed twice: keep one proposal, merge its unknowns
            proposed[name.casefold()]["unknown_ids"] += ids
            continue
        n += 1
        while f"c_{n}" in taken:
            n += 1
        payload = proposed[name.casefold()] = {"id": f"c_{n}", "name": name, "unknown_ids": ids}
        if nc.description.strip():
            payload["appearance_cues"] = [_line(nc.description)]
    out = [BibleProposal(kind="add_character", payload=p) for p in proposed.values()]
    seen = set(bible.open_threads)
    for t in merge.new_threads:
        text = _line(t.text)
        if text and text not in seen:
            seen.add(text)
            out.append(BibleProposal(kind="add_thread", payload={"text": text}))
    if merge.plot_update and merge.plot_update.strip():
        out.append(BibleProposal(kind="update_plot", payload={"plot_so_far": _line(merge.plot_update)}))
    return out, found


def _scenes(stitched: list[WindowSceneDraft], ids: list[str]) -> list[Scene]:
    return [
        Scene(scene_id=f"s{i}", first_panel_id=ids[s.first - 1], last_panel_id=ids[s.last - 1],
              goal=s.goal, conflict=s.conflict, turn=s.turn,
              beats=[Beat(beat_id=f"s{i}b{j}", panel_ids=[ids[p - 1] for p in sorted(set(b.panels))],
                          what_happens=b.what_happens, function=b.function, intensity=b.intensity)
                     for j, b in enumerate(s.beats)])
        for i, s in enumerate(stitched)
    ]


async def understand_chapter(
    project_id: str, facts: list[PanelFacts], bible: SeriesBible, client: ModelClient,
    scheduler: ModelScheduler, cache: ArtifactCache,
) -> BeatSheet:
    story = [f for f in facts if f.is_story]
    if not story:
        raise NeedsReview(["no story panels"])
    ids = [f.panel_id for f in story]
    pos = {p: i for i, p in enumerate(ids)}
    names = {c.id: c.name for c in bible.characters}
    model, params = client.model_for("planner"), client.params_for("planner")

    async def cached(step: str, sha: str, text: str, schema: type[BaseModel]):
        key = cache_key(step, {"prompt": text}, sha, model, params)
        hit = cache.get(step, key, schema)
        if hit is not None:
            return hit
        guard_prompt(client, "planner", text)
        out = await client.structured("planner", text, schema)
        cache.put(step, key, out)
        return out

    wprompt = load_prompt(WINDOW_STEP, UNDERSTAND_PROMPT_VERSION)
    lines = [
        f"P{k} | {', '.join(names.get(c, c) for c in f.characters_visible) or '-'} | {_line(f.action)}"
        f" | {' / '.join(_line(d.text) for d in f.dialogue) or '-'}"
        for k, f in enumerate(story, start=1)
    ]
    characters = "\n".join(f"{c.id}: {c.name}" for c in bible.characters) or "(none)"

    def render(span: tuple[int, int]) -> str:
        return wprompt.render(plot_so_far=bible.plot_so_far or "(none)", characters=characters,
                              panels="\n".join(lines[span[0]:span[1]]), first=str(span[0] + 1), last=str(span[1]))

    spans = windows(len(story))
    drafts = await scheduler.map("planner", [render(s) for s in spans],
                                 lambda t: cached(WINDOW_STEP, wprompt.sha256, t, WindowDraft))
    scenes = _scenes(stitch_windows(spans, drafts), ids)
    problems = _problems(scenes, {}, ids, bible, lambda p: f"P{pos[p] + 1}")
    if problems:
        bad = set().union(*(p for _, p in problems))
        redo = [k for k, (a, b) in enumerate(spans) if not bad or any(a <= pos[p] < b for p in bad)]
        fix = "\n\nFix these problems: " + "; ".join(m for m, _ in problems)
        # the re-ask prompt embeds the feedback, so its cache key never collides with the first call
        fixed = await scheduler.map("planner", [render(spans[k]) + fix for k in redo],
                                    lambda t: cached(WINDOW_STEP, wprompt.sha256, t, WindowDraft))
        for k, d in zip(redo, fixed):
            drafts[k] = d
        scenes = _scenes(stitch_windows(spans, drafts), ids)
        errors = [m for m, _ in _problems(scenes, {}, ids, bible, str)]
        if errors:
            raise NeedsReview(errors)

    unknowns: dict[str, str] = {}
    where: dict[str, list[str]] = {}  # unknown label -> its story panels, and the names written on them
    named: dict[str, list[str]] = {}
    for k, f in enumerate(story, start=1):
        for label in {*f.characters_visible, *(d.speaker_id for d in f.dialogue)}:
            if label and label.startswith('unknown_'):
                where.setdefault(label, []).append(f'P{k}')
                named.setdefault(label, []).extend(f.names_mentioned)
    for f in facts:
        for label, cue in f.unknown_cues.items():
            unknowns.setdefault(label, cue)
    mprompt = load_prompt(MERGE_STEP, UNDERSTAND_PROMPT_VERSION)
    scene_lines = []
    for s in scenes:
        scene_lines.append(f"P{pos[s.first_panel_id] + 1}-P{pos[s.last_panel_id] + 1}: {_line(s.goal)}")
        scene_lines.extend(f"  - {_line(b.what_happens)}" for b in s.beats)
    mtext = mprompt.render(
        scenes="\n".join(scene_lines),
        characters="\n".join(
            f"{c.id}: {c.name} - {', '.join(c.aliases) or '-'} - {'; '.join(c.appearance_cues) or '-'}"
            for c in bible.characters) or "(none)",
        unknowns="\n".join(
            f"{k}: {_line(v)} | panels {', '.join(where.get(k, [])) or '-'} | names on those panels: "
            f"{', '.join(dict.fromkeys(named.get(k, []))) or '-'}" for k, v in unknowns.items()) or "(none)",
    )
    merge = (await scheduler.map("planner", [mtext], lambda t: cached(MERGE_STEP, mprompt.sha256, t, MergeDraft)))[0]
    proposals, found = _proposals(merge, bible, unknowns, facts)
    resolutions = {k: v for k, v in merge.character_resolutions.items() if k in unknowns and v in names}
    return BeatSheet(
        project_id=project_id, scenes=scenes, hook=merge.hook, chapter_summary=merge.chapter_summary,
        character_resolutions={**found, **resolutions}, bible_proposals=proposals,
    )
