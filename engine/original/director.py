"""The Director: ONE abstract brief -> a complete production plan, as an `OriginalStory` of LONG TAKES the film pipeline can render.

The owner gives a sentence ("a one-minute video that explains how a thunderstorm forms, a young woman guide and her cat"); this module plays the film roles and writes down
every decision, so nothing is left to chance inside H3:

  writer              title, logline, the teaching points in order (`facts`)                              -> `_Writer`
  production designer cast and places with reusable look tags (the existing bible step)                    -> `story._make_bible`
  director            per take: the narration (voice-over), where it happens, and 2-3 shots inside the take -> `_TakeOut`
  cinematographer     framing per shot, a FIXED camera unless a shot names a move (measured: a push-in sentence in every shot zoomed clips 38% on average)
  sound / editor      the narration is a faceless `narrator` line mixed at the master; the takes are cut in order by `film_master`

The local 9B model is a noisy writer, so every stage is validated and retried with the concrete problems (`story._ask`), and everything H3 needs to be told is composed by RULES from the
plan, not by the model: the cast of each shot is closed ("exactly one woman (Mira) and exactly one cat (Pip), no other people or animals"), a moving subject must say which way it goes
relative to the camera, and only characters that are in the first frame may appear in the take (the first frame carries the look; a character that first appears in a later shot has none).
A take is as long as H3 allows (`MAX_TAKE`, measured on this GPU in docs/H3_CLIP_EVAL.md) so a minute needs few clips and few boundaries.
"""
from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field

from engine.original import story as sm
from engine.original.genres import GENRES, Genre
from engine.original.models import Line, OriginalStory, Panel, Scene

MAX_TAKE = 15.0  # seconds: the official H3 limit; the measured feasible length on this machine goes in docs/H3_CLIP_EVAL.md
WORDS_PER_SECOND = 2.4  # narration pace budget (Kokoro speaks ~2.6 words/s; the margin keeps the last word inside the take)
FRAMINGS = {"wide", "medium", "close"}
FIXED_WORDS = {"static", "fixed", "locked", "none", "still", "tripod", "no movement", "no camera movement", "stationary", "locked off"}  # a model's many ways of saying "the camera does not move"
CAMERA_MOVES = {"", "slow push-in", "slow pan left", "slow pan right"}
MOVE_VERB = re.compile(r"\b(walk|walks|walking|run|runs|running|jog|stride|strides|march|marches|travel|travels|enter|enters|leave|leaves|approach|approaches|head|heads|fly|flies|flying|float|floats|drift|drifts|rise|rises|climb|climbs|fall|falls|rush|rushes)\b", re.I)
DIRECTION = re.compile(r"\b(toward|towards|away from|to the left|to the right|from left to right|from right to left|left to right|right to left|upward|downward|across|past|forward|straight ahead)\b", re.I)  # "right behind her" is not a direction
SPEECH = re.compile(r"\b(says|said|speaks|speaking|talks|talking|asks|replies|whispers|shouts|explains aloud)\b", re.I)

EXPLAINER = Genre("explainer", "clear, friendly, curious and accurate; it respects the viewer's intelligence",
                  "a hook that asks the question, the explanation step by step in cause-and-effect order, one memorable summary",
                  4, (1, 1), "clean modern 2D animated explainer illustration, soft shading, bright natural colours, detailed scenery, consistent character design, no text, no captions, no labels",
                  GENRES["fantasy"].forbidden, caption_words=(0, 0))
GENRES.setdefault("explainer", EXPLAINER)


class _Writer(BaseModel):
    title: str
    logline: str = Field(description="two sentences: what the video explains, for whom, and who guides the viewer (name the guide and any companion from the brief)")
    setting: str
    facts: list[str] = Field(description="the teaching points in the order they are explained, each ONE short sentence of 8-22 words, accurate and concrete")


class _ShotOut(BaseModel):
    framing: str = Field(description="wide, medium or close")
    camera: str = Field(default="", description="leave empty for a fixed camera; only if the shot needs it: slow push-in, slow pan left or slow pan right")
    characters: list[str] = Field(description="ids of EVERY character visible in this shot (may be empty)")
    action: str = Field(description="what the viewer SEES in this shot, one or two concrete sentences: who is where, doing what, which way anything moves relative to the camera; the fact shown as a picture")


class _TakeOut(BaseModel):
    location_id: str
    narration: str = Field(description="the voice-over for this take: friendly spoken sentences that explain the take's facts, no stage directions")
    shots: list[_ShotOut]


def take_count(total_seconds: float, max_take: float = MAX_TAKE) -> int:
    return max(1, math.ceil(total_seconds / max_take))


def narration_budget(seconds: float) -> int:
    return int(seconds * WORDS_PER_SECOND)


def split_facts(facts: list[str], takes: int) -> list[list[str]]:
    """The teaching points dealt to the takes in order, as evenly as possible."""
    size, extra = divmod(len(facts), takes)
    out, i = [], 0
    for k in range(takes):
        n = size + (1 if k < extra else 0)
        out.append(facts[i:i + n])
        i += n
    return out


def check_writer(o: _Writer, takes: int, genre: Genre) -> list[str]:
    p: list[str] = []
    if len(o.logline.split()) < 12:
        p.append("logline needs two real sentences")
    if not takes <= len(o.facts) <= takes * 3:
        p.append(f"give {takes * 2} facts ({takes}-{takes * 3} allowed), at least one per take")
    for f in o.facts:
        if not 6 <= len(f.split()) <= 26:
            p.append(f"fact {f[:40]!r}... must be 8-22 words")
    if sm.forbidden_hits(" ".join(o.facts) + o.logline + o.title, genre):
        p.append("remove forbidden words")
    return p


def check_take(o: _TakeOut, bible, seconds: float, facts: list[str], genre: Genre) -> list[str]:
    p: list[str] = []
    chars = {c.id: c for c in bible.characters}
    locs = {x.id for x in bible.locations}
    for s in o.shots:  # tolerate wording, not substance
        if s.camera.strip().lower() in FIXED_WORDS or s.camera.strip().lower().startswith(("static", "fixed", "locked")):
            s.camera = ""
        s.framing = s.framing.strip().lower().replace(" shot", "").replace("close-up", "close").replace("closeup", "close").replace("long", "wide").replace("full", "wide")
        s.characters = [c.strip().lower() for c in s.characters]
    by_name = {x.name.lower(): x.id for x in bible.locations}
    o.location_id = by_name.get(o.location_id.strip().lower(), o.location_id.strip().lower())
    if o.location_id not in locs:
        p.append(f"location_id must be one of {sorted(locs)}")
    words = len(o.narration.split())
    budget = narration_budget(seconds)
    if not budget * 0.45 <= words <= budget:
        p.append(f"narration has {words} words; write {int(budget * 0.7)} words (allowed {int(budget * 0.45)}-{budget}) so it fills about {seconds:.0f} s of speech")
    if SPEECH.search(" ".join(s.action for s in o.shots)):
        p.append("nobody speaks on screen: the narration is a voice-over; describe what the viewer sees, not speech")
    if not 2 <= len(o.shots) <= 3:
        p.append("2 or 3 shots per take")
    first = {c for c in (o.shots[0].characters if o.shots else [])}
    for k, s in enumerate(o.shots, 1):
        if s.framing not in FRAMINGS:
            p.append(f"shot {k}: framing must be one of {sorted(FRAMINGS)}")
        if s.camera.strip() not in CAMERA_MOVES:
            p.append(f"shot {k}: camera must be empty or one of {sorted(CAMERA_MOVES - {''})}")
        for c in s.characters:
            if c not in chars:
                p.append(f"shot {k}: unknown character id {c!r}; use {sorted(chars)}")
        if set(s.characters) - first:
            p.append(f"shot {k}: {sorted(set(s.characters) - first)} are not in shot 1; every character of the take must already be in the FIRST shot (the first picture carries the look)")
        if len(s.action.split()) < 8:
            p.append(f"shot {k}: describe what is seen in at least 8 words")
        if MOVE_VERB.search(s.action) and not DIRECTION.search(s.action):
            p.append(f"shot {k}: something moves; say which way relative to the camera (toward the camera, away from the camera, to the left, to the right, up, down)")
        named = [c.name for c in chars.values() if c.name.lower() in s.action.lower()]
        absent = [n for n in named if next(c.id for c in chars.values() if c.name == n) not in s.characters]
        if absent:
            p.append(f"shot {k}: {absent} appear in the action but are not listed in 'characters'")
        if re.search(r"\b(text|caption|label|sign reading|words|subtitle|title card)\b", s.action, re.I):
            p.append(f"shot {k}: the picture cannot hold readable text; show the idea as a picture instead")
    if sm.forbidden_hits(o.narration + " ".join(s.action for s in o.shots), genre):
        p.append("remove forbidden words")
    return p


async def direct(brief: str, provider, total_seconds: float = 60.0, max_take: float = MAX_TAKE, progress=lambda pct, msg: None) -> OriginalStory:
    """The whole plan from one sentence. Raises ValueError if a stage cannot be made to pass its checks (the message lists the problems)."""
    genre = GENRES["explainer"]
    n = take_count(total_seconds, max_take)
    seconds = round(total_seconds / n, 2)
    progress(0.05, "Writer: premise and teaching points")
    w = await sm._ask(provider, f"Brief from the owner: {brief}\nPlan an informative video of {total_seconds:.0f} seconds in {n} parts. Give a title, a two-sentence logline (name the guide "
                      f"and any companion the brief asks for), the setting, and {n * 2} teaching facts in the order they are explained. Facts must be accurate and concrete.",
                      _Writer, lambda o: check_writer(o, n, genre), temperature=0.7, max_tokens=900)
    premise = sm.Premise(title=w.title.strip(), genre="explainer", logline=w.logline.strip(), tone=genre.tone, setting=w.setting.strip())
    progress(0.2, "Production designer: cast and places")
    bible = await sm._make_bible(provider, genre, premise)
    dealt = split_facts([f.strip() for f in w.facts], n)
    scenes: list[Scene] = []
    panels: list[Panel] = []
    for i in range(n):
        progress(0.3 + 0.6 * i / n, f"Director: take {i + 1} of {n}")
        prev = " ".join(p.dialogue[0].text for p in panels)[-400:]
        facts = " | ".join(dealt[i])
        cast = "; ".join(f"{c.id} = {c.name} ({c.species}, {c.age_group})" for c in bible.characters)
        places = "; ".join(f"{x.id} = {x.name}" for x in bible.locations)
        t = await sm._ask(provider, f"Video: {premise.title}. {premise.logline}\nCast: {cast}\nPlaces: {places}\n"
                          f"Take {i + 1} of {n}, {seconds:.0f} seconds long. It must explain: {facts}\nEarlier narration (do not repeat it): {prev or 'none'}\n"
                          f"Write the narration (about {int(narration_budget(seconds) * 0.75)} words, never more than {narration_budget(seconds)}) and 2-3 shots inside this take that SHOW the facts as pictures "
                          "(a story-world visual metaphor or a real scene, no text on screen). Only characters who are in the first shot may appear later in the take. The camera is fixed "
                          "unless a shot truly needs a slow move. Nobody speaks on screen; the narration is a voice-over.",
                          _TakeOut, lambda o: check_take(o, bible, seconds, dealt[i], genre), temperature=0.7, max_tokens=1800, attempts=7)
        loc = t.location_id
        shots = []
        for k, s in enumerate(t.shots):
            shots.append({"at": round(seconds * k / len(t.shots) * 2) / 2, "framing": s.framing, "camera": s.camera.strip(), "action": s.action.strip(), "characters": s.characters})
        first = t.shots[0]
        scenes.append(Scene(id=f"s{i + 1}", location_id=loc, character_ids=first.characters, summary=" ".join(dealt[i]), mood=genre.tone))
        panels.append(Panel(id=f"t{i + 1}", scene_id=f"s{i + 1}", shot=first.framing, angle="eye_level", location_id=loc, character_ids=first.characters, action=first.action.strip(),
                            dialogue=[Line(speaker_id="narrator", text=t.narration.strip())], caption="", motion=first.action.strip(), seconds=seconds, shots=shots))
    progress(1.0, "Plan complete")
    return OriginalStory(bible=bible, scenes=scenes, panels=panels, warnings=[])
