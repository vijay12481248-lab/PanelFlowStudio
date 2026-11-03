"""Story engine: premise -> bible -> scene outline -> panel script, one small validated LLM call per step.

Lesson from the anime review work: a 9B local model cannot produce a long structured document in one shot, but it writes a
short section reliably, and code can enforce structure, ids, content limits and continuity between sections.
"""
from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field

from engine.original.genres import ANGLES, GENRES, SHOTS, Genre
from engine.original.models import (Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene)

NL = chr(10)
SYSTEM = "You are a professional story writer for illustrated manga and picture books. You follow the requested format exactly."
AGE_GROUPS = {"child", "teen", "adult", "elder"}
ROLES = {"protagonist", "companion", "antagonist", "mentor", "other"}
MAX_LINE_WORDS = 18
SLUG = re.compile(r"^[a-z][a-z0-9_]{0,24}$")
NOT_NAMES = {"they", "them", "it", "he", "she", "him", "her", "the", "someone", "something", "unknown", "nobody", "thing",
             "creature", "keeper", "protagonist", "supporting", "companion", "antagonist", "mentor", "hero", "other", "man", "woman", "boy", "girl", "child", "figure", "stranger", "narrator"}
STOP_NAMES = {"I", "Mr", "Mrs", "Ms", "Dr", "Oh", "Hey", "Yes", "No", "Okay", "Mom", "Dad", "Grandma", "Grandpa"}


class _Premise(BaseModel):
    title: str
    logline: str = Field(description="two sentences: who wants what and what stands in the way")
    setting: str


class _Char(BaseModel):
    id: str = Field(description="lowercase slug, letters/digits/underscore, e.g. mira")
    name: str
    role: str = Field(description="protagonist, companion, antagonist, mentor or other")
    age_group: str = Field(description="child, teen, adult or elder")
    species: str = Field(description="'human', or exactly what it is: fox cub, robot, spirit")
    gender: str = Field(description="male or female for humans (decide it); neutral only for creatures, robots and spirits")
    look: str = Field(description="6-10 comma-separated visual tags: hair, eyes, build, outfit, one distinctive item")
    personality: str


class _Loc(BaseModel):
    id: str
    name: str
    look: str = Field(description="5-8 comma-separated visual tags")


class _Bible(BaseModel):
    characters: list[_Char]
    locations: list[_Loc]
    rules: list[str] = Field(description="2-4 facts about this world that must never be contradicted")


class _SceneOut(BaseModel):
    location_id: str
    character_ids: list[str]
    summary: str = Field(description="2-3 sentences: what happens in this scene")
    mood: str


class _Outline(BaseModel):
    scenes: list[_SceneOut]


class _LineOut(BaseModel):
    speaker_id: str
    text: str


class _PanelOut(BaseModel):
    shot: str = Field(description="wide, medium, close, extreme_close or over_shoulder")
    angle: str = Field(description="eye_level, low, high or dutch")
    character_ids: list[str]
    action: str = Field(description="one concrete visual sentence: who is where, doing what, with what expression")
    dialogue: list[_LineOut] = Field(default_factory=list)
    caption: str = ""
    sfx: list[str] = Field(default_factory=list)


class _Panels(BaseModel):
    panels: list[_PanelOut]


def forbidden_hits(text: str, genre: Genre) -> list[str]:
    words = set(re.findall(r"[a-z]+", text.lower()))
    return sorted(words & genre.forbidden)


def known_names(bible: Bible) -> set[str]:
    names = set(STOP_NAMES)
    for n in [c.name for c in bible.characters] + [loc.name for loc in bible.locations] + [bible.premise.title]:
        names |= set(re.findall(r"[A-Za-z]+", n))
    return names


def unknown_names(text: str, allowed: set[str]) -> list[str]:
    """Capitalised words inside a sentence that are not in the bible: invented characters or places."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        for w in re.findall(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]{2,}\b", sent):
            if w not in allowed and w.rstrip("s") not in allowed:
                out.append(w)
    return sorted(set(out))


AGE_SYNONYMS = {"kid": "child", "young": "child", "toddler": "child", "baby": "child", "teenager": "teen", "youth": "teen",
                "old": "elder", "elderly": "elder", "ancient": "elder", "grown": "adult", "grownup": "adult"}


def to_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:24] or "x"


GENDERS = {"man": "male", "boy": "male", "he": "male", "woman": "female", "girl": "female", "she": "female"}


def normalize_bible(o: _Bible) -> _Bible:
    """Fix what the model gets cosmetically wrong (hyphenated ids, 'kid' for child) instead of failing the whole step."""
    for x in o.characters + o.locations:
        x.id = to_slug(x.name or x.id)  # the id follows the name: a model that calls "Mist-Walker" by its id "fenrir" in prose is a real failure
    for c in o.characters:
        g = c.gender.strip().lower()
        c.gender = GENDERS.get(g, g if g in ("male", "female") else "neutral")
        c.species = c.species.strip().lower() or "human"
        c.age_group = AGE_SYNONYMS.get(c.age_group.strip().lower(), c.age_group.strip().lower())
        if c.age_group not in AGE_GROUPS and c.role != "protagonist":
            c.age_group = "adult"  # creatures and spirits: the field only matters for the hero and for child-safety
        c.role = c.role.strip().lower() if c.role.strip().lower() in ROLES else "other"
    seen: set[str] = set()
    for x in o.characters + o.locations:  # colliding ids get a numeric suffix
        base, n = x.id, 2
        while x.id in seen:
            x.id, n = f"{base[:20]}_{n}", n + 1
        seen.add(x.id)
    heroes = [c for c in o.characters if c.role == "protagonist"]
    if o.characters and not heroes:
        o.characters[0].role = "protagonist"  # the first character listed is the lead
    for extra in heroes[1:]:
        extra.role = "companion"
    return o


def _resolver(bible: Bible):
    table = {}
    for x in list(bible.characters) + list(bible.locations):
        table[to_slug(x.id)] = x.id
        table[to_slug(x.name)] = x.id
    return lambda ref: table.get(to_slug(ref), ref)


def normalize_outline(o: _Outline, bible: Bible) -> _Outline:
    r = _resolver(bible)
    for sc in o.scenes:
        sc.location_id = r(sc.location_id)
        sc.character_ids = [r(c) for c in sc.character_ids]
    return o


def normalize_panels(o: _Panels, bible: Bible) -> _Panels:
    r = _resolver(bible)
    for x in o.panels:
        x.character_ids = list(dict.fromkeys(r(c) for c in x.character_ids))
        x.shot, x.angle = x.shot.strip().lower().replace(" ", "_"), x.angle.strip().lower().replace(" ", "_").replace("-", "_")
        for ln in x.dialogue:
            ln.speaker_id = r(ln.speaker_id)
    return o


def check_bible(o: _Bible, genre: Genre) -> list[str]:
    p: list[str] = []
    normalize_bible(o)
    if not 2 <= len(o.characters) <= 5:
        p.append("need 2-5 characters")
    if not 2 <= len(o.locations) <= 4:
        p.append("need 2-4 locations")
    ids = [c.id for c in o.characters] + [loc.id for loc in o.locations]
    if len(set(ids)) != len(ids):
        p.append("ids must be unique across characters and locations")
    for x in o.characters + o.locations:
        if not SLUG.match(x.id):
            p.append(f"id {x.id!r} must be a lowercase slug")
        if len([t for t in x.look.split(",") if t.strip()]) < 4 and len(x.look.split()) < 8:
            p.append(f"{x.name}: look needs at least 4 comma-separated visual tags")
    for c in o.characters:
        if c.age_group not in AGE_GROUPS:
            p.append(f"{c.name}: age_group must be one of {sorted(AGE_GROUPS)}")
        if c.role not in ROLES:
            p.append(f"{c.name}: role must be one of {sorted(ROLES)}")
    for c in o.characters:
        if re.sub(r"[^a-z]", "", c.name.lower()) in NOT_NAMES or len(c.name.strip()) < 3:
            p.append(f"character name {c.name!r} is a pronoun or generic word; give every character a proper name")
    for c in o.characters:
        if c.species == "human" and c.gender == "neutral":
            p.append(f"{c.name}: a human character needs gender male or female (it decides how they are drawn)")
    if sum(c.role == "protagonist" for c in o.characters) != 1:
        p.append("exactly one protagonist is required")
    hero = next((c for c in o.characters if c.role == "protagonist"), None)
    if genre.child_safe and hero and hero.age_group != "child":
        p.append("the protagonist of a bedtime story must be a child (age_group child)")
    if genre.child_safe and any(c.role == "antagonist" for c in o.characters):
        p.append("a bedtime story has no antagonist; use a gentle worry or a misunderstanding instead")
    for c in o.characters:
        others = [x.name for x in o.characters if x is not c and x.name.split()[0].lower() in c.look.lower()]
        if others:
            p.append(f"{c.name}: look must describe only this character, not {others}")
    blob = " ".join(x.look for x in o.characters + o.locations) + " " + " ".join(o.rules)
    if forbidden_hits(blob, genre):
        p.append(f"remove forbidden words: {forbidden_hits(blob, genre)}")
    return p


def check_outline(o: _Outline, bible: Bible, genre: Genre) -> list[str]:
    p: list[str] = []
    normalize_outline(o, bible)
    if abs(len(o.scenes) - genre.scenes) > 1:
        p.append(f"need {genre.scenes} scenes (+-1), got {len(o.scenes)}")
    cids, lids = {c.id for c in bible.characters}, {loc.id for loc in bible.locations}
    for i, s in enumerate(o.scenes, 1):
        if s.location_id not in lids:
            p.append(f"scene {i}: location_id {s.location_id!r} must be one of {sorted(lids)}")
        if not s.character_ids or any(c not in cids for c in s.character_ids):
            p.append(f"scene {i}: character_ids must be a non-empty subset of {sorted(cids)}")
        if len(s.summary.split()) < 10:
            p.append(f"scene {i}: summary too short")
        if forbidden_hits(s.summary, genre):
            p.append(f"scene {i}: forbidden words {forbidden_hits(s.summary, genre)}")
        extra = unknown_names(s.summary, known_names(bible))
        if extra:
            p.append(f"scene {i}: unknown names {extra}; use only characters and places from the bible")
    return p


ABSTRACT_WORDS = {"realizes", "realises", "realized", "realised", "understands", "understood", "represents", "symbol", "symbolizes", "metaphor",
                  "essence", "embodiment", "testament", "tapestry", "sanctuary", "legacy", "destiny", "significance", "profound", "transcend"}


def caption_visual_problem(caption: str, shown: list[Character]) -> str:
    """The picture is drawn from the caption, so a caption must say who is on screen and describe something that can be seen."""
    if shown and not any(c.name.split()[0].lower() in caption.lower() for c in shown):
        return f"the caption must name who is on screen ({', '.join(c.name for c in shown)}) and what they visibly do"
    hits = sorted({w.strip(".,;:!?").lower() for w in caption.split()} & ABSTRACT_WORDS)
    return f"the caption is abstract ({hits}): describe what we SEE - body, face, objects, place" if hits else ""


def check_panels(o: _Panels, scene: Scene, bible: Bible, genre: Genre) -> list[str]:
    p: list[str] = []
    normalize_panels(o, bible)
    lo, hi = genre.panels_per_scene
    if not lo <= len(o.panels) <= hi:
        p.append(f"need {lo}-{hi} panels, got {len(o.panels)}")
    if o.panels and o.panels[0].shot != "wide":
        p.append("the first panel of a scene must be a wide establishing shot")
    if len({x.shot for x in o.panels}) < min(3, len(o.panels)):
        p.append("vary the shots: use at least 3 different shot types")
    allowed = known_names(bible)
    for i, x in enumerate(o.panels, 1):
        if x.shot not in SHOTS or x.angle not in ANGLES:
            p.append(f"panel {i}: shot must be in {sorted(SHOTS)} and angle in {sorted(ANGLES)}")
        if not x.character_ids and x.shot not in {"wide", "close", "extreme_close"}:
            p.append(f"panel {i}: only wide shots and close-ups of objects may show no character")
        if any(c not in {ch.id for ch in bible.characters} for c in x.character_ids):
            p.append(f"panel {i}: character_ids must be bible characters {[ch.id for ch in bible.characters]}")
        if len(x.action.split()) < 6 or '"' in x.action:
            p.append(f"panel {i}: action must be a visual sentence of 6+ words without quotes")
        if len(x.dialogue) > 2:
            p.append(f"panel {i}: at most 2 dialogue lines")
        for ln in x.dialogue:
            if ln.speaker_id not in x.character_ids:
                p.append(f"panel {i}: speaker {ln.speaker_id!r} is not shown in the panel")
            if not 1 <= len(ln.text.split()) <= MAX_LINE_WORDS:
                p.append(f"panel {i}: dialogue lines must be 1-{MAX_LINE_WORDS} words")
        cw = len(x.caption.split())
        if not genre.caption_words[0] <= cw <= genre.caption_words[1] + 10:  # ten words of slack over the requested range
            p.append(f"panel {i}: caption must be {genre.caption_words[0]}-{genre.caption_words[1]} words, got {cw}")
        problem = caption_visual_problem(x.caption, [c for c in bible.characters if c.id in x.character_ids])
        if problem:
            p.append(f"panel {i}: {problem}")
        text = " ".join([x.action, x.caption] + [ln.text for ln in x.dialogue])
        if forbidden_hits(text, genre):
            p.append(f"panel {i}: forbidden words {forbidden_hits(text, genre)}")
        extra = sorted({n for part in [x.action, x.caption] + [ln.text for ln in x.dialogue] for n in unknown_names(part, allowed)})
        if extra:
            p.append(f"panel {i}: unknown names {extra}; use only bible characters and places")
    return p


async def _ask(provider, prompt: str, model, check, temperature: float = 0.7, attempts: int = 4, max_tokens: int = 3500,
               notes: list[str] | None = None):
    """Retries with the concrete problems. 'unknown names' alone is soft after two tries (a real term like
    'Fresnel lens' looks like an invented name): the answer is accepted and the finding goes to `notes`."""
    feedback: list[str] = []
    for attempt in range(attempts):
        text = prompt + ("\n\nYour last answer had these problems, fix them all:\n- " + "\n- ".join(feedback[:8]) if feedback else "")
        out = await provider.generate_structured(text, model, system_prompt=SYSTEM, temperature=temperature,
                                                 max_tokens=max_tokens, num_ctx=16384)
        feedback = check(out)
        if not feedback:
            return out
        if attempt >= 1 and all("unknown names" in f for f in feedback):
            if notes is not None:
                notes.extend(feedback)
            return out
    raise ValueError("story step failed validation after retries: " + "; ".join(feedback[:6]))


def _bible_text(b: Bible) -> str:
    chars = "\n".join(f"- {c.id} ({c.name}, {c.role}, {c.age_group}): {c.personality}" for c in b.characters)
    locs = "\n".join(f"- {loc.id} ({loc.name})" for loc in b.locations)
    return (f"Title: {b.premise.title}\nLogline: {b.premise.logline}\nSetting: {b.premise.setting}\nCharacters:\n{chars}\n"
            f"Locations:\n{locs}\nWorld rules: {'; '.join(b.rules)}")


def _episode_ask(sb: Bible, genre: Genre, previous: str, idea: str) -> str:
    return (f"Write the next episode of the {genre.key} series '{sb.premise.title}' ({sb.premise.logline}). Cast: "
            f"{', '.join(c.name for c in sb.characters)}. Places: {', '.join(x.name for x in sb.locations)}. "
            f"Earlier episodes: {previous or 'none yet'}. Give a NEW episode title, a two-sentence logline and the setting "
            "(one of the places). It is a self-contained adventure that continues naturally, uses only the existing cast, "
            f"and keeps the tone: {genre.tone}." + (f" Author's idea: {idea}." if idea else ""))


async def generate_story(genre_key: str, provider, idea: str = "", scenes: int | None = None,
                         progress=lambda pct, msg: None, series_bible: Bible | None = None, previous: str = "") -> OriginalStory:
    """A standalone story, or - with `series_bible` - the next episode: same cast, places and rules, a new premise that
    continues from `previous` (summaries of the earlier episodes)."""
    genre = GENRES[genre_key]
    notes: list[str] = []
    if scenes:
        genre = Genre(**{**genre.__dict__, "scenes": scenes})
    progress(0.05, "Premise")
    pr = await _ask(provider, _episode_ask(series_bible, genre, previous, idea) if series_bible is not None else
                    f"Invent an original {genre.key} story for an illustrated video. Tone: {genre.tone}. "
                    f"Structure: {genre.structure}. " + (f"Seed idea from the author: {idea}. " if idea else "") +
                    "Give a title, a two-sentence logline and the setting. Nothing copied from existing franchises.",
                    _Premise, lambda o: [] if len(o.logline.split()) >= 12 and not forbidden_hits(o.logline + o.title, genre)
                    else ["logline too short or contains forbidden words"], temperature=0.9, max_tokens=600)
    premise = Premise(title=pr.title.strip(), genre=genre.key, logline=pr.logline.strip(), tone=genre.tone, setting=pr.setting.strip())

    progress(0.15, "Characters and places")
    bible = series_bible.model_copy(update={"premise": premise}) if series_bible is not None else await _make_bible(
        provider, genre, premise)

    progress(0.3, "Scene outline")
    ou = await _ask(provider, _bible_text(bible) + (f"{NL}{NL}Earlier episodes: {previous}" if previous else "") +
                    f"{NL}{NL}Write the scene outline: {genre.scenes} scenes in story order following "
                    f"this structure: {genre.structure}. Each scene has a location_id, the character_ids present, a 2-3 "
                    "sentence summary and a mood. Use only the characters and places above; do not invent names.",
                    _Outline, lambda o: check_outline(o, bible, genre), temperature=0.7, max_tokens=2500, notes=notes)
    return await _script(bible, genre, ou, provider, progress, notes)


async def _make_bible(provider, genre: Genre, premise: Premise) -> Bible:
    bo = await _ask(provider, f"Story: {premise.title}. {premise.logline} Setting: {premise.setting}. Genre: {genre.key}, "
                    f"tone {genre.tone}. Create the cast (2-4 characters, exactly one protagonist; give each a distinctive, "
                    "reusable visual 'look' of comma-separated tags for an image model, ordered hair/fur, eyes, body, outfit, one "
                    "carried item; use concrete colour-and-shape tags an illustrator can draw, like 'long white hair' or 'black "
                    "wool coat', never textures or story words like 'salt-crusted' or 'weary'; describe ONLY that character and never mention another character in a look), 2-3 locations "
                    "and 2-4 world rules."
                    + (" This is a children's bedtime story: no antagonist, nothing frightening." if genre.child_safe else ""),
                    _Bible, lambda o: check_bible(o, genre), temperature=0.8, max_tokens=2500)
    return Bible(premise=premise, rules=[r.strip() for r in bo.rules],
                  characters=[Character(**c.model_dump()) for c in bo.characters],
                  locations=[Location(**loc.model_dump()) for loc in bo.locations])


async def _script(bible: Bible, genre: Genre, ou: _Outline, provider, progress, notes: list[str]) -> OriginalStory:
    scene_list = [Scene(id=f"sc{i:02d}", location_id=s.location_id, character_ids=list(dict.fromkeys(s.character_ids)),
                        summary=s.summary.strip(), mood=s.mood.strip()) for i, s in enumerate(ou.scenes, 1)]

    panels: list[Panel] = []
    lo, hi = genre.panels_per_scene
    for n, sc in enumerate(scene_list, 1):
        progress(0.35 + 0.6 * (n - 1) / len(scene_list), f"Panels for scene {n}/{len(scene_list)}")
        before = " ".join(s.summary for s in scene_list[max(0, n - 3):n - 1])
        out = await _ask(provider, _bible_text(bible) + f"\n\nEarlier in the story: {before or 'nothing yet'}\n"
                         f"Scene {n} of {len(scene_list)} ({sc.mood}) at {sc.location_id}, characters {sc.character_ids}: "
                         f"{sc.summary}\n\nBreak this scene into {lo}-{hi} manga panels. The first panel is a wide "
                         "establishing shot; vary shots and angles. 'action' is a concrete visual description for an "
                         "illustrator (no dialogue in it; 'shot' and 'angle' are camera terms - never describe a person or room as 'high' or 'low' because of them). Dialogue speakers must appear in the panel; keep lines short and "
                         "natural. Keep every panel different from the last - move the story forward. EVERY panel needs a narrator 'caption' of "
                         f"{genre.caption_words[0]}-{genre.caption_words[1]} words in the voice of a storyteller; it is read aloud over the picture and "
                         "the picture is DRAWN FROM IT, so every caption must name the characters on screen and describe what can be SEEN: "
                         "their body, face and eyes, what they hold or do, the place and light. Feelings are shown through faces and "
                         "gestures; no internal thoughts and no abstract statements. Use only the bible's characters and places.",
                         _Panels, lambda o, sc=sc: check_panels(o, sc, bible, genre), temperature=0.8, notes=notes)
        for x in out.panels:
            panels.append(Panel(id=f"p{len(panels) + 1:03d}", scene_id=sc.id, shot=x.shot, angle=x.angle,
                                location_id=sc.location_id, character_ids=x.character_ids, action=x.action.strip(),
                                dialogue=[Line(**ln.model_dump()) for ln in x.dialogue], caption=x.caption.strip(), sfx=x.sfx))
    story = OriginalStory(bible=bible, scenes=scene_list, panels=panels)
    story.warnings = continuity_warnings(story) + notes
    progress(1.0, "Story ready")
    return story


def continuity_warnings(s: OriginalStory) -> list[str]:
    """Soft checks over the whole story: unused cast, absent protagonist, silent or caption-less stretches."""
    w: list[str] = []
    shown = {c for p in s.panels for c in p.character_ids}
    for c in s.bible.characters:
        if c.id not in shown:
            w.append(f"{c.name} never appears in a panel")
    hero = next((c.id for c in s.bible.characters if c.role == "protagonist"), None)
    if hero and sum(hero in p.character_ids for p in s.panels) < 0.4 * len(s.panels):
        w.append("the protagonist is in fewer than 40% of the panels")
    words = sum(len(ln.text.split()) for p in s.panels for ln in p.dialogue) + sum(len(p.caption.split()) for p in s.panels)
    if words < 8 * len(s.panels):
        w.append(f"only {words} words of dialogue/captions for {len(s.panels)} panels: narration will be thin")
    for sc in s.scenes:
        if not any(p.scene_id == sc.id for p in s.panels):
            w.append(f"scene {sc.id} has no panels")
    return w


def estimated_minutes(s: OriginalStory) -> float:
    words = sum(len(ln.text.split()) for p in s.panels for ln in p.dialogue) + sum(len(p.caption.split()) for p in s.panels)
    return round(math.ceil(words / 2.4) / 60, 1)


async def generate_series_bible(genre_key: str, provider, idea: str = "") -> Bible:
    """The long-lived part of a series: premise of the world, cast with drawable looks, places and rules."""
    genre = GENRES[genre_key]
    pr = await _ask(provider, f"Invent an original {genre.key} story SERIES for an illustrated video channel. Tone: {genre.tone}. "
                    + (f"Seed idea from the author: {idea}. " if idea else "") +
                    "Give the series title, a two-sentence logline that can sustain many episodes, and the main setting. "
                    "Nothing copied from existing franchises.", _Premise,
                    lambda o: [] if len(o.logline.split()) >= 12 and not forbidden_hits(o.logline + o.title, genre)
                    else ["logline too short or contains forbidden words"], temperature=0.9, max_tokens=600)
    premise = Premise(title=pr.title.strip(), genre=genre.key, logline=pr.logline.strip(), tone=genre.tone, setting=pr.setting.strip())
    return await _make_bible(provider, genre, premise)
