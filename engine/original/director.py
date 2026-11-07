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
LOCOMOTION = re.compile(r"\b(walk|walks|walking|run|runs|running|jog|jogs|stride|strides|march|marches|travel|travels|head|heads|enter|enters|leave|leaves|approach|approaches|rush|rushes)\b", re.I)
HORIZONTAL = re.compile(r"\b(toward|towards|away from|to the left|to the right|from left to right|from right to left|left to right|right to left|across the frame|forward|straight ahead)\b", re.I)  # up/down is not a way to walk


def needs_direction(action: str) -> bool:
    """True when somebody WALKS, runs or heads somewhere without a horizontal direction within eight words after the verb (relative to the camera, or left/right)."""
    return any(not HORIZONTAL.search(" ".join(action[m.end():].split()[:8])) for m in LOCOMOTION.finditer(action))


def fix_direction(action: str, k: int = 0) -> str:
    """The 9B model does not reliably say which way a walker goes, so the Director does: the missing direction is inserted right after the verb. A sideways walk
    (to the right on even takes, to the left on odd ones) keeps the walker in profile and the direction readable; 'toward/away from the camera' walks are what H3 turns around."""
    way = "to the right" if k % 2 == 0 else "to the left"
    out, pos = [], 0
    for m in LOCOMOTION.finditer(action):
        out.append(action[pos:m.end()])
        if not HORIZONTAL.search(" ".join(action[m.end():].split()[:8])):
            out.append(f" {way}")
        pos = m.end()
    return "".join(out) + action[pos:]


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
    atmosphere: list[str] = Field(default_factory=list, description="the sky and light of each part, in order, ONE entry per part: 5-14 words of what is seen (cloud cover, light colour and strength). It changes from part to part the way the story builds or calms down")
    must_show: list[str] = Field(default_factory=list, description="up to 4 short phrases from the owner's brief for what the viewer must SEE: who is there, how many, what they do (e.g. 'the guide walks through the landscape')")


class _ShotOut(BaseModel):
    framing: str = Field(description="wide, medium or close")
    camera: str = Field(default="", description="leave empty for a fixed camera; only if the shot needs it: slow push-in, slow pan left or slow pan right")
    characters: list[str] = Field(description="ids of EVERY character visible in this shot (may be empty)")
    action: str = Field(description="what the viewer SEES in this shot, one or two concrete sentences: who is where, doing what, which way anything moves relative to the camera; the fact shown as a picture")


class _TakeOut(BaseModel):
    location_id: str
    end_state: str = Field(default="", description="STORYBOARD only: what the LAST picture of the shot shows in the same framing: who stands where in the frame and what they are doing then")
    narration: str = Field(description="the voice-over for this take: friendly spoken sentences that explain the take's facts, no stage directions")
    shots: list[_ShotOut]


def normalize_framing(text: str) -> str:
    t = text.strip().lower()
    if "close" in t or "detail" in t or "macro" in t:
        return "close"
    if any(w in t for w in ("wide", "establishing", "long", "full", "aerial", "master", "landscape")):
        return "wide"
    return "medium"


def normalize_camera(text: str) -> str:
    """A fixed camera unless the wording clearly asks for one of the three slow moves; anything else (tracking, dolly, handheld, zoom out...) becomes a fixed camera."""
    t = text.strip().lower()
    if "push" in t or "zoom in" in t or "dolly in" in t:
        return "slow push-in"
    if "pan" in t and "left" in t:
        return "slow pan left"
    if "pan" in t and "right" in t:
        return "slow pan right"
    return ""


class _BoardTake(BaseModel):
    """Storyboard mode: ONE shot and its two pictures, every field required (the 9B skips optional fields and invents extra shots when a list is allowed)."""
    location_id: str
    narration: str = Field(description="the voice-over for this take: friendly spoken sentences that explain the take's facts, no stage directions")
    shot: _ShotOut
    end_state: str = Field(description="what the LAST picture of the shot shows in the same framing: who stands where in the frame (left, center or right side) and what they are doing then; at least 8 words")


def stacked(text: str, names: list[str]) -> str | None:
    """A character ridden, carried or perched on another ('Luna sits on her right shoulder', 'Maya carries Luna'): the image model draws BOTH the carried and a separate one (measured: a second cat in 3 of 8 storyboard pictures), so characters stay apart. Returns the offending name or None."""
    for n in names:
        if re.search(rf"{n}.{{0,40}}"+r"\b(shoulder|lap|arms|head|back|perch\w*)\b", text, re.I) or re.search(r"\b(carr\w+|cradl\w+|hug\w+|lift\w+|hold\w*)\s+(?:her\s+|his\s+|the\s+)?"+n, text, re.I):
            return n
    return None


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


def check_writer(o: _Writer, takes: int, genre: Genre, brief: str = "", sky: bool = False) -> list[str]:
    p: list[str] = []
    if sky and (len(o.atmosphere) != takes or any(not 4 <= len(a.split()) <= 16 for a in o.atmosphere)):
        p.append(f"atmosphere: exactly {takes} entries (one per part), each 5-14 words about the sky and the light")
    elif sky and takes > 1 and any(content_words(a) == content_words(b) for a, b in zip(o.atmosphere, o.atmosphere[1:])):
        p.append("atmosphere: neighbouring parts must look different (the sky and light change as the story builds or calms down)")
    bw = content_words(brief)
    for m in o.must_show:  # a requirement is something the OWNER said: it must come from the brief, not from the model's own plan
        if bw and not content_words(m) <= bw:
            p.append(f"must_show {m!r} is not in the owner's brief; copy phrases from the brief only")
    if brief and MOVE_VERB.search(brief) and not any(MOVE_VERB.search(m) for m in o.must_show):
        p.append("the brief says someone or something moves (walks, runs, flies ...): put that action in must_show, copied from the brief")
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


def check_take(o: _TakeOut, bible, seconds: float, facts: list[str], genre: Genre, take_index: int = 0, storyboard: bool = False) -> list[str]:
    p: list[str] = []
    if storyboard:
        if len(o.shots) != 1:
            p.append("STORYBOARD: exactly ONE shot per take (one framing, one continuous action between a first and a last picture)")
        if len(o.end_state.split()) < 8:
            p.append("end_state: describe the LAST picture of the shot in at least 8 words: who stands where in the frame and what they are doing then")
        elif o.shots and [c.id for c in bible.characters if c.name.lower() in o.end_state.lower() and c.id not in [x.strip().lower() for x in o.shots[0].characters]]:
            p.append("end_state mentions a character who is not in the shot")
    chars = {c.id: c for c in bible.characters}
    locs = {x.id for x in bible.locations}
    for s in o.shots:  # tolerate wording, not substance: any framing / camera wording maps to the nearest allowed value
        s.framing = normalize_framing(s.framing)
        s.camera = normalize_camera(s.camera)
        s.characters = [c.strip().lower() for c in s.characters]
        s.action = fix_direction(s.action, take_index)
    by_name = {x.name.lower(): x.id for x in bible.locations}
    o.location_id = by_name.get(o.location_id.strip().lower(), o.location_id.strip().lower())
    if o.location_id not in locs:
        p.append(f"location_id must be one of {sorted(locs)}")
    words = len(o.narration.split())
    budget = narration_budget(seconds)
    if not budget * 0.65 <= words <= budget:
        p.append(f"narration has {words} words; write {int(budget * 0.85)} words (allowed {int(budget * 0.65)}-{budget}) so it fills the {seconds:.0f} s (measured: 9-13 words in an 18-word slot left half the video silent)")
    if SPEECH.search(" ".join(s.action for s in o.shots)):
        p.append("nobody speaks on screen: the narration is a voice-over; describe what the viewer sees, not speech")
    if not storyboard and not 2 <= len(o.shots) <= 3:
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
        named = [c.name for c in chars.values() if c.name.lower() in s.action.lower()]
        absent = [n for n in named if next(c.id for c in chars.values() if c.name == n) not in s.characters]
        if absent:
            p.append(f"shot {k}: {absent} appear in the action but are not listed in 'characters'")
        if re.search(r"\b(text|caption|label|sign reading|words|subtitle|title card)\b", s.action, re.I):
            p.append(f"shot {k}: the picture cannot hold readable text; show the idea as a picture instead")
    if sm.forbidden_hits(o.narration + " ".join(s.action for s in o.shots), genre):
        p.append("remove forbidden words")
    names = [c.name for c in chars.values() if len(chars) > 1]
    for k, text in [(f"shot {i + 1}", s.action) for i, s in enumerate(o.shots)] + ([("end_state", o.end_state)] if o.end_state else []):
        hit = stacked(text, names)
        if hit:
            p.append(f"{k}: {hit} is carried by or sits on another character; characters stand or sit SEPARATELY on the ground, never on a shoulder, in arms or on a lap")
    return p


STOP_WORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "with", "her", "his", "their", "she", "he", "they", "it", "is", "are", "be", "for", "by", "as", "that", "this",
              "through", "along", "one", "two", "young", "own", "pet", "video", "viewer", "shows", "show", "shown",
              "guide", "landscape", "scene", "woman", "girl", "man", "boy", "person", "character", "characters", "across"}  # roles and generic places say nothing about WHAT is shown


def content_words(text: str) -> set[str]:
    """Rough stems (first 5 letters of every content word): enough to ask 'does a shot talk about walking?' without an NLP library."""
    out = set()
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in STOP_WORDS or len(w) <= 2:
            continue
        for suffix in ("ing", "ed", "es", "s"):  # walks / walked / walking are one word
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                w = w[:-len(suffix)]
                break
        out.add(w[:5])
    return out


def uncovered(must_show: list[str], panels: list[Panel], cast_text: str = "") -> list[str]:
    """Requirements of the brief that no shot of the plan shows: a requirement is covered when at least half of its content words (stems) occur in the shots' actions."""
    actions = " ".join(s["action"] for p in panels for s in p.shots)
    shown = content_words(actions + " " + cast_text)  # the cast covers "a young woman guide" and "one cat"
    out = []
    for r in must_show:
        if LOCOMOTION.search(r) and not LOCOMOTION.search(actions):  # "the guide walks": somebody must walk in what is SHOWN (a start action), not only be said to have walked
            out.append(r)
            continue
        words = content_words(r)
        if words and len(words & shown) * 2 < len(words):
            out.append(r)
    return out


STORYBOARD_ASK = ("STORYBOARD: this take is ONE continuous shot with ONE framing, drawn as two pictures: `action` = what the FIRST picture shows and what then happens, `end_state` = what the "
                  "LAST picture shows, in the same framing. Use the frame: say where each character stands in the frame at the start and at the end (left, center or right side); if somebody "
                  "walks, they end at a clearly different place (walking to the right = left side at the start, right side at the end). Keep the same characters in both pictures.")


async def _take(provider, bible, premise, genre, i: int, n: int, seconds: float, facts: list[str], prev: str, extra: str = "", storyboard: bool = False) -> _TakeOut:
    cast = "; ".join(f"{c.id} = {c.name} ({c.species}, {c.age_group})" for c in bible.characters)
    places = "; ".join(f"{x.id} = {x.name}" for x in bible.locations)
    shots_ask = "ONE shot" if storyboard else "2-3 shots inside this take"
    ask = (f"Video: {premise.title}. {premise.logline}\nCast: {cast}\nPlaces: {places}\n"
           f"Take {i + 1} of {n}, {seconds:.0f} seconds long. It must explain: {' | '.join(facts)}\nEarlier narration (do not repeat it): {prev or 'none'}\n"
           f"Write the narration (about {int(narration_budget(seconds) * 0.85)} words, never more than {narration_budget(seconds)}) and {shots_ask} that SHOW the facts as pictures "
           "(a story-world visual metaphor or a real scene, no text on screen). Only characters who are in the first shot may appear later in the take. The camera is fixed "
           "unless a shot truly needs a slow move. Nobody speaks on screen; the narration is a voice-over." + (f"\n{STORYBOARD_ASK}" if storyboard else "") + (f"\n{extra}" if extra else ""))
    from engine.llm.errors import GenerationLimitError

    as_take = lambda o: _TakeOut(location_id=o.location_id, narration=o.narration, shots=[o.shot], end_state=o.end_state) if storyboard else o  # noqa: E731
    for temperature, tokens in ((0.7, 1800), (0.5, 2800), (0.3, 4000)):  # the 9B sometimes runs on until the token limit: ask again, cooler and with more room
        try:
            got = await sm._ask(provider, ask, _BoardTake if storyboard else _TakeOut, lambda o: check_take(as_take(o), bible, seconds, facts, genre, i, storyboard), temperature=temperature, max_tokens=tokens, attempts=7)
            out = as_take(got)
            check_take(out, bible, seconds, facts, genre, i, storyboard)  # normalises wording on the object that is returned
            return out
        except GenerationLimitError:
            continue
    raise ValueError("the model ran past its length limit three times for this take")


def _panel(i: int, t: _TakeOut, seconds: float, facts: list[str], genre: Genre, sky: str = "") -> tuple[Scene, Panel]:
    shots = [{"at": round(seconds * k / len(t.shots) * 2) / 2, "framing": s.framing, "camera": s.camera.strip(), "action": s.action.strip(), "characters": s.characters}
             for k, s in enumerate(t.shots)]
    first = t.shots[0]
    return (Scene(id=f"s{i + 1}", location_id=t.location_id, character_ids=first.characters, summary=" ".join(facts), mood=genre.tone),
            Panel(id=f"t{i + 1}", scene_id=f"s{i + 1}", shot=first.framing, angle="eye_level", location_id=t.location_id, character_ids=first.characters, action=first.action.strip(),
                  dialogue=[Line(speaker_id="narrator", text=t.narration.strip())], caption="", motion=first.action.strip(), seconds=seconds, shots=shots, end_state=t.end_state.strip(), atmosphere=sky.strip()))


async def direct(brief: str, provider, total_seconds: float = 60.0, max_take: float = MAX_TAKE, progress=lambda pct, msg: None, storyboard: bool = False) -> OriginalStory:
    """The whole plan from one sentence. Raises ValueError if a stage cannot be made to pass its checks (the message lists the problems).
    After the takes are written, every requirement the owner's brief made about what the viewer sees (`must_show`) must appear in some shot; a take is written again for each
    that does not (measured on the first storm video: the brief said the guide walks through the landscape and the plan never showed her walking)."""
    genre = GENRES["explainer"]
    n = take_count(total_seconds, max_take)
    seconds = round(total_seconds / n, 2)
    progress(0.05, "Writer: premise and teaching points")
    w = await sm._ask(provider, f"Brief from the owner: {brief}\nPlan an informative video of {total_seconds:.0f} seconds in {n} parts. Give a title, a two-sentence logline (name the guide "
                      f"and any companion the brief asks for), the setting, {n if storyboard and n > 4 else n * 2} teaching facts in the order they are explained (the FIRST is a hook that makes the viewer curious, the LAST a one-sentence takeaway; accurate and concrete), " + (f"atmosphere (the sky and light of each of the {n} parts, in order, changing as the story builds or calms down), " if storyboard else "") + "and must_show: "
                      "up to 4 short phrases copied from the brief for everything the brief says the viewer must SEE (who is there, how many, what they do).",
                      _Writer, lambda o: check_writer(o, n, genre, brief, storyboard), temperature=0.7, max_tokens=1100)
    premise = sm.Premise(title=w.title.strip(), genre="explainer", logline=w.logline.strip(), tone=genre.tone, setting=w.setting.strip())
    progress(0.2, "Production designer: cast and places")
    bible = await sm._make_bible(provider, genre, premise)
    dealt = split_facts([f.strip() for f in w.facts], n)
    skies = [a.strip() for a in w.atmosphere] if storyboard else [""] * n
    sky_ask = lambda i: f"Sky and light in this take: {skies[i]}. Do not describe any other weather or light." if skies[i] else ""  # noqa: E731
    scenes: list[Scene] = []
    panels: list[Panel] = []
    warnings: list[str] = []
    for i in range(n):
        progress(0.3 + 0.5 * i / n, f"Director: take {i + 1} of {n}")
        t = await _take(provider, bible, premise, genre, i, n, seconds, dealt[i], " ".join(p.dialogue[0].text for p in panels)[-400:], sky_ask(i), storyboard=storyboard)
        sc, pa = _panel(i, t, seconds, dealt[i], genre, skies[i])
        scenes.append(sc)
        panels.append(pa)
    for r, i in zip(uncovered([m.strip() for m in w.must_show], panels, " ".join(f"{c.name} {c.species} {c.age_group} {c.gender} {c.role} {c.look}" for c in bible.characters)), range(n)):  # one repair per missing requirement, each in a different take
        progress(0.85, f"Director: the brief needs '{r}' to be shown; rewriting take {i + 1}")
        prev = " ".join(p.dialogue[0].text for k, p in enumerate(panels) if k != i)[-400:]
        try:
            t = await _take(provider, bible, premise, genre, i, n, seconds, dealt[i], prev, f"The owner's brief requires this to be SEEN in this take (as a clear action): {r}. {sky_ask(i)}", storyboard=storyboard)
            scenes[i], panels[i] = _panel(i, t, seconds, dealt[i], genre, skies[i])
        except ValueError as exc:  # best effort: keep the take that passed its checks and say what is missing
            warnings.append(f"the brief says '{r}' but no take shows it (rewrite of take {i + 1} failed: {str(exc)[:160]})")
    progress(1.0, "Plan complete")
    return OriginalStory(bible=bible, scenes=scenes, panels=panels, warnings=warnings)
