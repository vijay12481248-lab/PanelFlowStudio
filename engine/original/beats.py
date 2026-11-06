"""Beats and the shot director: every narrated moment gets its own, fully specified picture.

History: on the first real episode one image stayed up for 13-19 s while 2-3 sentences played over it, and its prompt came from a
separately written `action`, not from the narration. Now:

1. The narration of each panel is split into beats of at most ~24 words (1-2 sentences).
2. A *shot director* (LLM) reads the beat's spoken text and writes a structured ShotSpec: who is on screen and where, each
   character's pose, expression and action, the setting specifics, lighting, mood and the things that MUST be visible
   (see shotspec.py, which composes the final image prompt from it - no prompt is typed by hand, for any story).
3. Pattern rules that do not depend on the model keep hard requirements from being lost: "closes his eyes", "asleep", "yawns",
   "smiles", "cries" always become required visuals; a moment about one named character's face/eyes/sleep must show only that
   character, close; every named character must be on screen; at most two characters are drawn per picture.

The expanded story is an ordinary OriginalStory whose panels are the beats, so art, video and pages run unchanged on it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from engine.original.genres import GENRES, SHOTS
from engine.original.models import Bible, OriginalStory, Panel
from engine.original.shotspec import CharPose, ShotSpec
from engine.original.story import _ask, forbidden_hits, known_names, unknown_names

MAX_BEAT_WORDS = 24
MIN_TAIL_WORDS = 8
MAX_CHARACTERS = 2  # the art workflow draws at most two faces per picture
FOCUS_WORDS = ("eyes", "asleep", "sleep", "yawn", "smile", "tear", "whisper", "face", "blink", "breath")
BEATS_FILE = "beats.json"
SIDES = {"left", "center", "right"}
CAMERAS = {"eye_level", "low", "high", "dutch"}


def split_caption(text: str, max_words: int = MAX_BEAT_WORDS) -> list[str]:
    """Greedy sentence groups of at most `max_words` words (a single longer sentence stays whole)."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    groups: list[list[str]] = []
    for s in sentences:
        if groups and sum(len(x.split()) for x in groups[-1]) + len(s.split()) <= max_words:
            groups[-1].append(s)
        else:
            groups.append([s])
    if len(groups) > 1 and sum(len(x.split()) for x in groups[-1]) < MIN_TAIL_WORDS:
        tail = groups.pop()
        groups[-1] += tail  # a 2-6 word fragment ("Cat juggling.") gets no picture of its own: the model invents one from nothing
    return [" ".join(g) for g in groups]


POSE_PATTERNS = [  # what the words say about the body, whatever the director model writes
    (r"clos\w*\s+(?:his|her|their|its|my)?\s*eyes|eyes\s+(?:clos|shut)|shut\w*\s+(?:his|her|their|its)?\s*eyes", "eyes closed"),
    (r"\basleep\b|\bsleeping\b|falls?\s+asleep|drift\w*(?:\s+\w+ly)?\s+(?:off\s+)?(?:to|into)\s+(?:sleep|dreams?)|\bdreaming\b|\bslumber"
     r"|\bdoz(?:e|es|ed|ing)\b|nods?\s+off|rests?\s+(?:his|her|their)\s+head", "sleeping"),
    (r"\byawn", "yawning"),
    (r"\bsmil", "smiling"),
    (r"\btears?\b|\bcry|\bcried", "tears"),
]


def pose_keys(text: str) -> list[str]:
    """Things the words require to be visible on the character: found by pattern, so they are never lost to a model."""
    return [key for pat, key in POSE_PATTERNS if re.search(pat, text, re.I)]


class _CharOut(BaseModel):
    id: str = Field(description="character id from the cast list")
    side: str = Field(description="left, center or right: where they stand in the frame")
    pose: str = Field(description="body position, e.g. 'lying curled on his side', 'standing with arms raised', 'sitting cross-legged'")
    expression: str = Field(description="face and eyes, e.g. 'eyes closed, peaceful smile', 'wide eyes, open mouth, startled'")
    action: str = Field(description="what they are doing with hands/body/objects, e.g. 'holding the glowing basket to his chest'")


class _Shot(BaseModel):
    shot: str = Field(description="wide, medium, close, extreme_close or over_shoulder")
    camera: str = Field(description="eye_level, low, high or dutch")
    characters: list[_CharOut] = Field(description="the characters visible, at most two")
    setting: str = Field(description="specific visible details of the place: objects, plants, weather, time of day")
    lighting: str = Field(description="light source and colour, e.g. 'warm golden glow from the lantern'")
    mood: str = Field(description="the emotion of the picture in a few words")
    key_visuals: list[str] = Field(description="2-4 phrases of AT MOST 5 words each that must be clearly visible; include every physical claim of the narration")


def named_characters(text: str, bible: Bible) -> list[str]:
    return [c.id for c in bible.characters if re.search(rf"\b{re.escape(c.name.split()[0])}\b", text)]


def focus_character(text: str, bible: Bible) -> str | None:
    """The one named character a moment is about when it describes their eyes/sleep/expression, else None."""
    named = named_characters(text, bible)
    return named[0] if len(named) == 1 and any(w in text.lower() for w in FOCUS_WORDS) else None


PRONOUN = re.compile(r"\b(he|she|they|his|her|their|him|them)\b", re.I)


def _check(o: _Shot, bible: Bible, genre, text: str = "") -> list[str]:
    p: list[str] = []
    ids = {c.id for c in bible.characters}
    names = {c.name.lower(): c.id for c in bible.characters}
    o.shot = o.shot.strip().lower().replace(" ", "_")
    o.camera = o.camera.strip().lower().replace(" ", "_").replace("-", "_")
    if o.shot not in SHOTS:
        p.append(f"shot must be one of {sorted(SHOTS)}")
    if o.camera not in CAMERAS:
        o.camera = "eye_level"
    for c in o.characters:
        c.id = names.get(c.id.strip().lower(), c.id.strip())
        c.side = c.side.strip().lower() if c.side.strip().lower() in SIDES else "center"
    if any(c.id not in ids for c in o.characters):
        p.append(f"characters must come from {sorted(ids)}")
    if len(o.characters) > MAX_CHARACTERS:
        p.append(f"show at most {MAX_CHARACTERS} characters: pick the ones the narration is about")
    if len({c.id for c in o.characters}) != len(o.characters):
        p.append("each character appears once")
    for c in o.characters:
        if len(c.pose.split()) < 1 or len(c.expression.split()) < 1:
            p.append(f"{c.id}: give a pose and an expression")
    if len(o.setting.split()) < 3:
        p.append("setting: describe the place with at least 3 words of specifics")
    o.key_visuals = [k.strip() for k in o.key_visuals if 0 < len(k.split()) <= 5][:4]  # a cut-off phrase is worse than none
    if not o.key_visuals:
        p.append("key_visuals: give 1-4 short phrases of what must be visible")
    blob = " ".join([o.setting, o.lighting, o.mood] + o.key_visuals + [f"{c.pose} {c.expression} {c.action}" for c in o.characters])
    if forbidden_hits(blob, genre):
        p.append(f"forbidden words {forbidden_hits(blob, genre)}")
    extra = unknown_names(blob, known_names(bible))
    if extra:
        p.append(f"unknown names {extra}; use only the story's characters")
    shown = {c.id for c in o.characters}
    named = named_characters(text, bible)
    missing = [n for n in named if n not in shown]
    if missing and len(named) <= MAX_CHARACTERS:
        p.append(f"the narration names {missing}: they must be in the picture")
    if named and len(named) <= MAX_CHARACTERS and shown - set(named):
        p.append(f"the narration is only about {named}: do not draw {sorted(shown - set(named))}")
    if not named and not PRONOUN.search(text) and shown:
        p.append("the narration names nobody: draw the place (a wide shot with no characters)")
    who = focus_character(text, bible)
    if who and (o.shot == "wide" or shown != {who}):
        p.append(f"this moment is about {who} alone (eyes, sleep or expression): use a close or medium shot showing only {who}")
    return p


def _summary(spec: ShotSpec, bible: Bible) -> str:
    names = {c.id: c.name for c in bible.characters}
    return "; ".join(f"{names.get(c.id, c.id)} {c.pose}, {c.expression}" for c in spec.characters) + f" ({spec.setting}; {spec.lighting})"


async def direct_shot(provider, story: OriginalStory, panel: Panel, text: str, previous: ShotSpec | None, notes: list[str]) -> ShotSpec | None:
    bible, genre = story.bible, GENRES[story.bible.premise.genre]
    cast = "\n".join(f"- {c.id} ({c.name}): {c.look}" for c in bible.characters)
    loc = next((x for x in bible.locations if x.id == panel.location_id), None)
    prompt = (
        "You are the storyboard artist of a narrated picture story. The narrator reads this aloud while the picture is on screen:\n"
        f"\"{text}\"\n\nCast (use these ids):\n{cast}\nPlace: {(loc.name + ' - ' + loc.look) if loc else 'unspecified'}\n"
        f"Previous picture: {_summary(previous, bible) if previous else 'none yet'}.\n"
        # the author's note disambiguates nouns ("glass" of water vs a glass door); the narration still decides what is shown
        f"{('Author note on this panel (only to resolve ambiguous words): ' + panel.action + chr(10)) if panel.action.strip() else ''}\n"
        "Design the ONE picture that shows exactly what the narration says. For each visible character give their pose (body), "
        "expression (eyes and mouth) and action (hands, objects), and where they stand. Add the specific visible details of the place, "
        "the light and the mood. List the 2-4 things that must be clearly visible, including every physical claim in the narration. "
        "Every character the narration names must be visible. If the narration is about a feeling or an idea, show the most fitting "
        "visible moment (a face, a gesture, the place) without inventing plot. Draw only the characters the narration names (a narration "
        "about the weather or the place has no characters: a wide shot of the place). Use a close-up only for a face, eyes or an "
        "expression; if an object matters, use a medium or wide shot showing the character AND the object. Use camera eye_level unless "
        "the narration says someone looks up or down. Keep clothes, place and time of day consistent with the "
        "previous picture unless the narration changes them. Do not repeat the previous picture. Use only the cast above.")
    try:
        o = await _ask(provider, prompt, _Shot, lambda o: _check(o, bible, genre, text), temperature=0.5, attempts=4, max_tokens=900, notes=notes)
    except ValueError as e:
        notes.append(f"{panel.id}: shot rejected - {str(e)[-160:]}")
        return None
    return ShotSpec(shot=o.shot, camera=o.camera, setting=o.setting.strip(), lighting=o.lighting.strip(), mood=o.mood.strip(),
                    key_visuals=o.key_visuals, characters=[CharPose(**c.model_dump()) for c in o.characters])


def fallback_spec(story: OriginalStory, panel: Panel, text: str) -> ShotSpec:
    """When the director fails: still a complete spec, built from the words (named characters, pose rules, the panel's place)."""
    named = named_characters(text, story.bible)[:MAX_CHARACTERS]
    who = focus_character(text, story.bible)
    ids = [who] if who else (named or panel.character_ids[:MAX_CHARACTERS])
    keys = pose_keys(text)
    loc = next((x for x in story.bible.locations if x.id == panel.location_id), None)
    return ShotSpec(shot="close" if who else panel.shot if panel.shot in SHOTS else "medium", camera="eye_level",
                    characters=[CharPose(id=i, side="center" if len(ids) == 1 else ("left" if k == 0 else "right"),
                                         pose="", expression=", ".join(keys), action=text[:120]) for k, i in enumerate(ids)],
                    setting=loc.name if loc else "", key_visuals=keys)


async def expand_story(story: OriginalStory, provider, progress: Callable[[float, str], None] = lambda p, m: None,
                       limit: int | None = None) -> OriginalStory:
    """Panels -> beats with a ShotSpec each. A shot that cannot be directed falls back to a spec built from the words, with a warning."""
    notes: list[str] = []
    out: list[Panel] = []
    previous: ShotSpec | None = None
    src = story.panels[:limit] if limit else story.panels
    for n, p in enumerate(src, 1):
        progress(n / len(src), f"Beats for panel {n}/{len(src)}")
        parts = split_caption(p.caption) or [""]
        for k, text in enumerate(parts, 1):
            last = k == len(parts)
            spec = await direct_shot(provider, story, p, text, previous, notes) if text else None
            if spec is None:
                if text:
                    notes.append(f"{p.id}: no shot could be directed, built it from the words")
                spec = fallback_spec(story, p, text or p.action)
            spec.key_visuals = list(dict.fromkeys(pose_keys(text) + spec.key_visuals))[:4]
            dialogue = list(p.dialogue) if last else []
            for ln in dialogue:  # whoever speaks must be in the picture
                if ln.speaker_id not in [c.id for c in spec.characters] and len(spec.characters) < MAX_CHARACTERS:
                    spec.characters.append(CharPose(id=ln.speaker_id, side="right", pose="standing", expression="speaking, mouth open"))
            out.append(p.model_copy(update={
                "id": f"{p.id}_{k}", "shot": spec.shot, "angle": spec.camera, "character_ids": [c.id for c in spec.characters],
                "action": "; ".join(f"{c.pose} {c.action}".strip() for c in spec.characters) or p.action, "caption": text,
                "dialogue": dialogue, "sfx": p.sfx if last else [], "key_visuals": spec.key_visuals, "director": spec.model_dump()}))
            previous = spec
    return story.model_copy(update={"panels": out, "warnings": list(story.warnings) + notes})


def media_story(ws: Path) -> OriginalStory:
    """The story the media steps use: the beat-expanded one when it exists, else the plain story."""
    f = ws / BEATS_FILE
    return OriginalStory.model_validate_json((f if f.exists() else ws / "story.json").read_text(encoding="utf-8"))
