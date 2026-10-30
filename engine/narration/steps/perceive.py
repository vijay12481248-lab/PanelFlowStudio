"""Step 1 PERCEIVE: grounded per-panel facts from a local vision model."""
from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

from engine.narration.artifacts import OcrDialogue, PanelFacts, SeriesBible
from engine.narration.cache import ArtifactCache, cache_key
from engine.narration.inputs import ChapterInputs, PanelInput
from engine.imaging.panel_quality_reviewer import AD_KEYWORDS
from engine.narration.runtime.client import ModelClient, guard_prompt
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler

PERCEIVE_PROMPT_VERSION = "v1"
STEP = "perceive"
_START = "(chapter start)"


class SpeakerGuess(BaseModel):
    region_id: str
    speaker: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class PanelFactsDraft(BaseModel):
    is_story: bool
    shot: Literal["wide", "medium", "close", "insert"]
    characters_visible: list[str]
    names_mentioned: list[str] = Field(default_factory=list)
    action: str
    emotion: str
    speakers: list[SpeakerGuess]
    sfx: list[str]
    setting: str
    importance: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)


def _context(draft: PanelFactsDraft) -> str:
    who = ", ".join(draft.characters_visible) or "none"
    return f"{draft.action} (visible: {who})"


class _Namer:
    """Maps model-written names to bible ids, then to chapter-stable unknown_<n> labels."""

    def __init__(self, bible: SeriesBible):
        self.by_name = {}
        for c in bible.characters:
            for n in [c.id, c.name, *c.aliases]:  # models often echo the id shown in the prompt
                self.by_name[n.casefold()] = c.id
        self.unknowns: dict[str, str] = {}  # model string (casefold) -> unknown_<n>

    def map(self, name: str, cues: dict[str, str]) -> str:
        key = name.strip().casefold()
        if key in self.by_name:
            return self.by_name[key]
        if key.startswith("unknown_") and key in self.unknowns.values():
            return key
        label = self.unknowns.setdefault(key, f"unknown_{len(self.unknowns) + 1}")
        cues.setdefault(label, name)
        return label


_NAME_RUN = re.compile(r"\b[A-Z][a-z]+(?:[ -][A-Z][a-z]+)*\b")
_NOT_NAMES = {"A", "An", "The", "He", "She", "They", "His", "Her", "Their", "It", "Man", "Woman", "Young", "Red",
              "Two", "One", "Another", "Someone", "Figure", "Demon", "Master"}


def names_in(text: str) -> list[str]:
    """Capitalised runs in a sentence, minus the sentence-initial word unless it starts a multi-word run."""
    out = []
    for m in _NAME_RUN.finditer(text):
        run = m.group().split()
        while run and run[0] in _NOT_NAMES:
            run = run[1:]
        if not run or (m.start() == 0 and len(run) == 1 and run == m.group().split()):
            continue  # a lone capitalised first word is just the sentence start
        out.append(" ".join(run))
    return out


def _facts(panel: PanelInput, d: PanelFactsDraft, namer: _Namer) -> PanelFacts:
    cues: dict[str, str] = {}
    visible = list(dict.fromkeys(namer.map(n, cues) for n in d.characters_visible if n.strip()))
    region_ids = {r.region_id for r in panel.ocr}
    guesses = {g.region_id: g for g in d.speakers if g.region_id in region_ids and g.speaker.strip()}
    speaker = {rid: namer.map(g.speaker, cues) for rid, g in guesses.items()}
    credits = any(k in r.text.casefold() for r in panel.ocr for k in AD_KEYWORDS)
    dialogue = [
        OcrDialogue(
            region_id=r.region_id, text=r.text,
            speaker_id=speaker.get(r.region_id),
            speaker_confidence=guesses[r.region_id].confidence if r.region_id in guesses else None,
        )
        for r in panel.ocr
    ]
    # small models often leave names_mentioned empty but still write read-off names into the action
    names = list(dict.fromkeys([*(n.strip() for n in d.names_mentioned if n.strip()), *names_in(d.action)]))[:6]
    # Only allowed coercion: over-long action is cut to its first 20 words.
    action = " ".join(d.action.split()[:20]) if len(d.action.split()) > 20 else d.action
    return PanelFacts(
        panel_id=panel.panel_id, order=panel.order, is_story=d.is_story or (bool(guesses) and not credits), shot=d.shot,
        characters_visible=visible, unknown_cues=cues, names_mentioned=names, action=action, emotion=d.emotion,
        dialogue=dialogue, sfx=list(dict.fromkeys([*d.sfx, *panel.sfx])), setting=d.setting, importance=d.importance,
        confidence=d.confidence, needs_review=d.confidence < 0.5,
    )


async def perceive_chapter(
    inputs: ChapterInputs, bible: SeriesBible, client: ModelClient,
    scheduler: ModelScheduler, cache: ArtifactCache,
) -> list[PanelFacts]:
    prompt = load_prompt(STEP, PERCEIVE_PROMPT_VERSION)
    model, params = client.model_for("vision"), client.params_for("vision")
    characters = "\n".join(
        f"{c.id}: {c.name} - {'; '.join(c.appearance_cues)}" for c in bible.characters
    ) or "(none)"

    async def one(panel: PanelInput, previous: str) -> PanelFactsDraft:
        ocr = [(r.region_id, r.text) for r in panel.ocr]
        key = cache_key(
            STEP,
            {"panel_id": panel.panel_id, "image": hashlib.sha256(panel.image_path.read_bytes()).hexdigest(),
             "ocr": ocr, "previous": previous, "bible_version": bible.version},
            prompt.sha256, model, params,
        )
        hit = cache.get(STEP, key, PanelFactsDraft)
        if hit is not None:
            return hit
        text = prompt.render(
            previous=previous, characters=characters,
            ocr_lines="\n".join(f"[{i}] {t}" for i, t in ocr) or "(no text)",
        )
        guard_prompt(client, "vision", text, images=1)
        draft = await client.structured("vision", text, PanelFactsDraft, image=panel.image_path)
        cache.put(STEP, key, draft)
        return draft

    drafts: list[PanelFactsDraft] = []
    previous, size = _START, scheduler.concurrency("vision")
    for i in range(0, len(inputs.panels), size):
        chunk = inputs.panels[i:i + size]
        ctx = previous
        got = await scheduler.map("vision", chunk, lambda p, ctx=ctx: one(p, ctx))
        drafts.extend(got)
        previous = _context(got[-1])

    namer = _Namer(bible)
    return [_facts(p, d, namer) for p, d in zip(inputs.panels, drafts)]
