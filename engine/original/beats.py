"""Beats: make every picture show exactly what is being said while it is on screen.

Problem found on the first real episode: one image stayed up for 13-19 seconds while 2-3 narrated sentences played over it, and
its prompt came from a separately written `action`, not from the narration. "Pip closes his eyes, drifting peacefully into
dreams" played over a wide shot of three characters in a glowing hollow.

Fix: the narration of each panel is split into beats of at most ~24 words (1-2 sentences). Each beat gets its own picture, whose
brief (shot, who is visible, what they do, a few things that MUST be visible) is written FROM the spoken text. The expanded story
is an ordinary OriginalStory whose panels are the beats, so art, video and pages run unchanged on it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from engine.original.genres import GENRES, SHOTS
from engine.original.models import Bible, Line, OriginalStory, Panel
from engine.original.story import SYSTEM, _ask, forbidden_hits, known_names, unknown_names

MAX_BEAT_WORDS = 24
FOCUS_WORDS = ("eyes", "asleep", "sleep", "yawn", "smile", "tear", "whisper", "face", "blink", "breath")
BEATS_FILE = "beats.json"


def split_caption(text: str, max_words: int = MAX_BEAT_WORDS) -> list[str]:
    """Greedy sentence groups of at most `max_words` words (a single longer sentence stays whole)."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    groups: list[list[str]] = []
    for s in sentences:
        if groups and sum(len(x.split()) for x in groups[-1]) + len(s.split()) <= max_words:
            groups[-1].append(s)
        else:
            groups.append([s])
    return [" ".join(g) for g in groups]


POSE_PATTERNS = [  # what the words say about the body, whatever the illustrator model writes
    (r"clos\w*\s+(?:his|her|their|its|my)?\s*eyes|eyes\s+(?:clos|shut)|shut\w*\s+(?:his|her|their|its)?\s*eyes", "eyes closed"),
    (r"\basleep\b|\bsleeping\b|falls?\s+asleep|drift\w*(?:\s+\w+ly)?\s+(?:off\s+)?(?:to|into)\s+(?:sleep|dreams?)|\bdreaming\b|\bslumber|\bdoz(?:e|es|ed|ing)\b|nods?\s+off|rests?\s+(?:his|her|their)\s+head", "sleeping"),
    (r"\byawn", "yawning"),
    (r"\bsmil", "smiling"),
    (r"\btears?\b|\bcry|\bcried", "tears"),
]


def pose_keys(text: str) -> list[str]:
    """Things the words require to be visible on the character: found by pattern, so they are never lost to a model."""
    return [key for pat, key in POSE_PATTERNS if re.search(pat, text, re.I)]


class _Brief(BaseModel):
    shot: str = Field(description="wide, medium, close, extreme_close or over_shoulder")
    character_ids: list[str] = Field(description="only the characters visible in this picture")
    action: str = Field(description="one concrete visual sentence: exactly what the narration shows, with pose and expression")
    key_visuals: list[str] = Field(description="2-4 short things that must be clearly visible, e.g. 'eyes closed', 'asleep'")


def focus_character(text: str, bible: Bible) -> str | None:
    """The one named character a moment is about when it describes their eyes/sleep/expression, else None."""
    named = [c for c in bible.characters if re.search(rf"\b{re.escape(c.name.split()[0])}\b", text)]
    return named[0].id if len(named) == 1 and any(w in text.lower() for w in FOCUS_WORDS) else None


def _check(o: _Brief, bible: Bible, genre, text: str = "") -> list[str]:
    p: list[str] = []
    ids = {c.id for c in bible.characters}
    if o.shot.strip().lower().replace(" ", "_") not in SHOTS:
        p.append(f"shot must be one of {sorted(SHOTS)}")
    o.shot = o.shot.strip().lower().replace(" ", "_")
    names = {c.name.lower(): c.id for c in bible.characters}
    o.character_ids = list(dict.fromkeys(names.get(c.lower(), c) for c in o.character_ids))
    if any(c not in ids for c in o.character_ids):
        p.append(f"character_ids must come from {sorted(ids)}")
    if len(o.action.split()) < 6 or '"' in o.action:
        p.append("action must be one visual sentence of 6+ words without quotes")
    o.key_visuals = [" ".join(k.split()[:6]) for k in o.key_visuals if k.strip()][:4]  # trim instead of failing the whole brief
    if not o.key_visuals:
        p.append("key_visuals: give 1-4 short phrases of what must be visible")
    if forbidden_hits(o.action + " " + " ".join(o.key_visuals), genre):
        p.append(f"forbidden words {forbidden_hits(o.action, genre)}")
    extra = unknown_names(o.action, known_names(bible))
    if extra:
        p.append(f"unknown names {extra}; use only the story's characters")
    who = focus_character(text, bible)
    if who and (o.shot == "wide" or o.character_ids != [who]):
        p.append(f"this moment is about {who} alone (eyes, sleep or expression): use a close or medium shot showing only {who}")
    return p


async def brief_for(provider, story: OriginalStory, panel: Panel, text: str, previous: str, notes: list[str]) -> _Brief | None:
    bible, genre = story.bible, GENRES[story.bible.premise.genre]
    cast = "\n".join(f"- {c.id} ({c.name}): {c.look}" for c in bible.characters)
    loc = next((x for x in bible.locations if x.id == panel.location_id), None)
    prompt = (f"You are the illustrator of a picture story. The narrator is saying this right now:\n\"{text}\"\n\n"
              f"Characters:\n{cast}\nPlace: {loc.name + ' - ' + loc.look if loc else 'unspecified'}\n"
              f"The previous picture showed: {previous or 'nothing yet'}.\n\n"
              "Design the ONE picture that shows what the narration says at this moment: choose the shot and the characters "
              "who are visible, describe their pose and expression, and list the key things that must be visible. If the "
              "narration says someone closes their eyes or falls asleep, use a close-up of that character with closed eyes; "
              "if it is about a place or mood, use a wide shot. Do not repeat the previous picture. Use only these characters.")
    try:
        return await _ask(provider, prompt, _Brief, lambda o: _check(o, bible, genre, text), temperature=0.5, attempts=4,
                          max_tokens=500, notes=notes)
    except ValueError as e:
        notes.append(f"{panel.id}: brief rejected - {str(e)[-160:]}")
        return None


async def expand_story(story: OriginalStory, provider, progress: Callable[[float, str], None] = lambda p, m: None,
                       limit: int | None = None) -> OriginalStory:
    """Panels -> beats. A brief that cannot be written falls back to the panel's own action and is reported in warnings."""
    notes: list[str] = []
    out: list[Panel] = []
    previous = ""
    src = story.panels[:limit] if limit else story.panels
    for n, p in enumerate(src, 1):
        progress(n / len(src), f"Beats for panel {n}/{len(src)}")
        parts = split_caption(p.caption) or [""]
        for k, text in enumerate(parts, 1):
            last = k == len(parts)
            b = await brief_for(provider, story, p, text, previous, notes) if text else None
            if b is None:
                if text:
                    notes.append(f"{p.id}: no brief could be written, drew the narration itself")
                who = focus_character(text, story.bible) if text else None
                shot, chars = ("close", [who]) if who else (p.shot, p.character_ids)
                action, keys = (text or p.action), []  # the spoken words are a better brief than the panel's separate action
            else:
                shot, chars, action, keys = b.shot, b.character_ids, b.action.strip(), [x.strip() for x in b.key_visuals]
            keys = list(dict.fromkeys(pose_keys(text) + keys))[:4]
            dialogue = list(p.dialogue) if last else []
            for ln in dialogue:  # whoever speaks must be in the picture
                if ln.speaker_id not in chars:
                    chars = chars + [ln.speaker_id]
            out.append(p.model_copy(update={"id": f"{p.id}_{k}", "shot": shot, "character_ids": chars, "action": action,
                                            "caption": text, "dialogue": dialogue, "sfx": p.sfx if last else [],
                                            "key_visuals": keys}))
            previous = action
    s = story.model_copy(update={"panels": out, "warnings": list(story.warnings) + notes})
    return s


def media_story(ws: Path) -> OriginalStory:
    """The story the media steps use: the beat-expanded one when it exists, else the plain story."""
    f = ws / BEATS_FILE
    return OriginalStory.model_validate_json((f if f.exists() else ws / "story.json").read_text(encoding="utf-8"))
