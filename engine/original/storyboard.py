"""The storyboard approach: decide and CHECK every picture first, then let H3 animate only between pictures that are already right.

Why (measured on the first two storm videos, docs/H3_CLIP_EVAL.md): given one first picture and a prompt, H3 ignores the plan - the guide was told to walk to the right and walked toward
the camera, shots jumped, a cat grew a human hand. Here the Director's plan becomes pictures instead of sentences:

  1. every shot gets a START picture (what `Panel.action` shows) and an END picture (`Panel.end_state`), drawn with the SAME seed and the same cast/look tags so the characters match;
     where somebody walks, the start and end pictures put them on different sides of the frame (the direction is drawn, not asked for);
  2. every picture is checked (how many women, how many cats, against the plan) and redrawn if wrong - this is where "only one cat" is enforced, before any video is made;
  3. a shot that continues in the same place with the same cast starts from the PREVIOUS shot's end picture (the same file), so the boundary is seamless;
  4. each shot is then one first-and-last-frame clip (FL2VA): H3 fills in the motion between two pictures and must land on the end picture. Its sound is anchored to silence (no invented
     speech); the narration is mixed at the master.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from engine.original import art as art_mod
from engine.original import clip_identity as ci
from engine.original import film, h3_modes
from engine.original.animate import STATIC_CAMERA
from engine.original.models import OriginalStory, Panel
from engine.original.shotspec import ShotSpec

SIZE = (1344, 768)
RIGHT = re.compile(r"\bto the right\b", re.I)
LEFT = re.compile(r"\bto the left\b", re.I)


def walk_direction(panel: Panel) -> str | None:
    """'right' or 'left' when the shot has somebody walk that way (the Director writes it, `director.fix_direction` guarantees it), else None."""
    text = f"{panel.action} {panel.end_state}"
    r, l = RIGHT.search(text), LEFT.search(text)
    return None if (r and l) or not (r or l) else ("right" if r else "left")


def sides(n: int, direction: str | None, which: str) -> list[str] | None:
    """Screen sides for the cast of a shot in its start / end picture; None = leave the default layout. A walker starts on the far side from where it ends."""
    if not direction or n > 2:
        return None
    start = {"right": ["left", "center"], "left": ["center", "right"]}[direction][:n]
    end = {"right": ["center", "right"], "left": ["left", "center"]}[direction][:n]
    if n == 1:
        start, end = (["left"], ["right"]) if direction == "right" else (["right"], ["left"])
    return start if which == "start" else end


def third_of_frame(story: OriginalStory, panel: Panel, which: str) -> str:
    """Where in the frame the cast stands, in words the image model follows better than a layout hint: a walker is in the far third from where it ends (measured: with only side hints the
    guide stayed on the left in both pictures)."""
    d = walk_direction(panel)
    if not d:
        return ""
    side = ({"right": "left", "left": "right"}[d]) if which == "start" else d
    names = [c.name for c in story.bible.characters if c.id in panel.character_ids]
    return f"{' and '.join(names)} {'stands' if len(names) == 1 else 'stand'} in the {side} third of the frame; the rest of the frame shows the landscape."


CLAUSE_SPLIT = re.compile(r"\s*(?:;|,\s*while\s+|\s+while\s+|,\s*as\s+|\s+as\s+|\.\s+)\s*", re.I)


def split_actions(text: str, names: dict[str, str], first: str) -> tuple[str, dict[str, str]]:
    """Describe every character exactly ONCE. The image model draws a second animal when the cast layout already places the cat and the action sentence places it again ('Miso sits on a
    rock to her right': a second small cat in 3 of 8 storyboard pictures). A clause that names exactly one OTHER character moves to that character's own entry (its name removed);
    everything else stays with the first character. Returns (the first character's text, {other id: its text})."""
    rest, own = [], {cid: [] for cid in names if cid != first}
    for clause in (c for c in CLAUSE_SPLIT.split(text) if c.strip()):
        named = [cid for cid, nm in names.items() if re.search(rf"\b{re.escape(nm)}\b", clause, re.I)]
        if len(named) == 1 and named[0] != first:
            own[named[0]].append(re.sub(rf"\b{re.escape(names[named[0]])}\b\s*(?:and\s+)?", "", clause, flags=re.I).strip(" ,"))
        else:
            rest.append(clause.strip(" ,"))
    return ". ".join(r for r in rest if r), {cid: ", ".join(v) for cid, v in own.items() if v}


def clauses(text: str, names: dict[str, str]) -> tuple[list[str], list[str]]:
    """(clauses about the weather/scenery, clauses that name a character): the two kinds of thing a picture description says."""
    scene, chars = [], []
    for clause in (c.strip(" ,") for c in CLAUSE_SPLIT.split(text) if c.strip()):
        (chars if any(re.search(rf"\b{re.escape(nm)}\b", clause, re.I) for nm in names.values()) else scene).append(clause)
    return scene, chars


def end_text(story: OriginalStory, panel: Panel) -> str:
    """The END picture is the START picture's world with the characters in their end places: the scenery and effects (clouds, bolts, glow) are taken from the start description
    and only the character clauses from the end state. (Measured: when the two pictures differed in weather and effects, H3 filled the gap with smoke puffs, rings and lightning.)"""
    names = {c.id: c.name for c in story.bible.characters if c.id in panel.character_ids}
    scene_start, _ = clauses(panel.action, names)
    _, chars_end = clauses(panel.end_state, names)
    return ". ".join(chars_end + scene_start) if chars_end else panel.end_state


def keyframe_prompt(story: OriginalStory, panel: Panel, which: str) -> tuple[str, str]:
    """The art prompt for the start or end picture of a shot: the shot's own framing, the cast on the sides the walk needs, the action (start) or end state (end)."""
    text = panel.action if which == "start" else end_text(story, panel)
    spec: ShotSpec = film.film_spec(story, panel.model_copy(update={"action": ""}))
    if spec.characters:
        names = {c.id: c.name for c in story.bible.characters if c.id in panel.character_ids}
        mine, others = split_actions(text or panel.action, names, spec.characters[0].id)
        spec.characters[0].action = (mine.rstrip(".") + ". " + third_of_frame(story, panel, which)).strip()
        for cp in spec.characters[1:]:
            cp.action = others.get(cp.id, "")
    else:
        spec = film.film_spec(story, panel.model_copy(update={"action": text or panel.action}))
    for cp, side in zip(spec.characters, sides(len(spec.characters), walk_direction(panel), which) or []):
        cp.side = side
    return art_mod.build_prompt(story, panel.model_copy(update={"director": spec.model_dump()}), style="natural", engine="qwen")


def panel_first_kind(story: OriginalStory, panel: Panel) -> str | None:
    kinds = list(film.cast_kinds(story, panel.character_ids[:1]))
    return kinds[0] if kinds else None


def continues(prev: Panel | None, panel: Panel) -> bool:
    """The shot starts where the previous one ended: same place, same cast (then its start picture IS the previous end picture)."""
    return prev is not None and prev.location_id == panel.location_id and set(prev.character_ids) == set(panel.character_ids) and bool(prev.end_state)


def _kinds(story: OriginalStory, panel: Panel) -> dict[str, int]:
    return {k: len(v) for k, v in film.cast_kinds(story, panel.character_ids).items()}


async def picture_problems(story: OriginalStory, panel: Panel, png: bytes, provider) -> list[str]:
    """A kind of character counted differently from the plan (None = the two answers disagreed, not a problem)."""
    bad = []
    for kind, expected in _kinds(story, panel).items():
        n = await ci.count_png(provider, png, kind)
        if n is not None and n != expected:
            bad.append(f"{kind}: counted {n}, planned {expected}")
    return bad


def hist_distance(a: bytes, b: bytes) -> float:
    from engine.original.clip_eval import SIZE as SZ, _hist

    img = lambda x: cv2.resize(cv2.imdecode(np.frombuffer(x, np.uint8), cv2.IMREAD_COLOR), SZ, interpolation=cv2.INTER_AREA)  # noqa: E731
    return round(float(cv2.compareHist(_hist(img(a)).astype(np.float32), _hist(img(b)).astype(np.float32), cv2.HISTCMP_BHATTACHARYYA)), 3)


async def draw(story: OriginalStory, ws: Path, runner, provider, tries: int = 4, progress: Callable[[str], None] = print) -> dict:
    """Draw and check the start and end picture of every shot (`film/frames/<id>.png`, `film/frames/<id>_end.png`). Returns {shot: {...}}; `unresolved` lists pictures
    that still miscount after `tries` draws (they are kept, and reported)."""
    fd = film.film_dir(ws)
    report: dict = {}
    prev: Panel | None = None
    for p in story.panels:
        start, end = fd / "frames" / f"{p.id}.png", fd / "frames" / f"{p.id}_end.png"
        chained = continues(prev, p) and (fd / "frames" / f"{prev.id}_end.png").exists() and not report.get(prev.id, {}).get("problems", {}).get("end")  # a bad end picture is not passed on
        kind = panel_first_kind(story, p)
        if chained and walk_direction(p) and kind:  # a walker cannot start on the side it walks to
            side = await ci.side_of(provider, (fd / "frames" / f"{prev.id}_end.png").read_bytes(), kind)
            far = {"right": "left", "left": "right"}[walk_direction(p)]
            chained = side in (far, "center", None)
        info = {"chained": chained, "attempts": 0, "problems": {}, "direction": walk_direction(p)}
        for attempt in range(tries):
            info["attempts"] = attempt + 1
            seed = art_mod.seed_for(story, p.id, attempt)
            if chained:
                shutil.copy2(fd / "frames" / f"{prev.id}_end.png", start)
            else:
                pos, neg = keyframe_prompt(story, p, "start")
                start.write_bytes(runner.generate(pos, neg, seed, SIZE[0], SIZE[1], f"sb_{p.id}_start"))
            pos, neg = keyframe_prompt(story, p, "end")
            end.write_bytes(runner.generate(pos, neg, seed, SIZE[0], SIZE[1], f"sb_{p.id}_end"))  # the same seed: the same characters, a different moment
            info["problems"] = {w: await picture_problems(story, p, f.read_bytes(), provider) for w, f in (("start", start), ("end", end))}
            if info["direction"] and panel_first_kind(story, p):  # a walker must really start on one side and end on the other
                kind = panel_first_kind(story, p)
                walk = ci.walk_ok(info["direction"], await ci.side_of(provider, start.read_bytes(), kind), await ci.side_of(provider, end.read_bytes(), kind))
                if walk:
                    info["problems"]["walk"] = walk
            info["problems"] = {k: v for k, v in info["problems"].items() if v}
            progress(f"  {p.id}: try {attempt + 1}{' (start = previous end)' if chained else ''}: {info['problems'] or 'cast counts match the plan'}")
            if not info["problems"]:
                break
        info["start_end_colour_distance"] = hist_distance(start.read_bytes(), end.read_bytes())
        report[p.id] = info
        prev = p
    (fd / "storyboard.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


STAY_IN_FRAME = ("Everyone stays inside the frame for the whole shot, in the same place and size as in the pictures. The camera never tilts, pans or moves. Weather, smoke and light effects "
                 "stay small and in the background and never cover the characters or fill the frame. Nothing new appears between the two pictures: no smoke, dust clouds, rings, bolts or glow that are not already in them.")  # measured: with only the story text H3 filled the middle of 4 of 8 shots with smoke, a different scene or a tilt up to the sky


def clip_prompt(story: OriginalStory, panel: Panel, seconds: float) -> str:
    """The FL2VA prompt: the start action, the closed cast, the camera, and how the shot must end (the last picture)."""
    d = walk_direction(panel)
    names = [c.name for c in story.bible.characters if c.id in panel.character_ids]
    if d:
        move = f"{' and '.join(names)} {'walks' if len(names) == 1 else 'walk'} {'to the right' if d == 'right' else 'to the left'} across the frame, in profile, from their place in the first picture to their place in the last picture."
    else:
        move = "Everyone stays where they are and moves only a little (a turn of the head, a gesture, a blink)."
    # The story text (lightning arcs, air lifts people) is NOT sent: both pictures already show it, and H3 acts out every event it is told about (a "massive lightning bolt" made a whole new lightning scene in the middle of a shot).
    _, chars_end = clauses(panel.end_state, {c.id: c.name for c in story.bible.characters if c.id in panel.character_ids})
    last = ". ".join(chars_end) if chars_end else panel.end_state.rstrip(".")  # only where the characters are: the pictures carry the rest
    action = f"The scene changes gradually and smoothly from the first picture into the last picture. {move} {film.count_clause(story, panel.character_ids)} {STAY_IN_FRAME} The last picture shows: {last}"
    return h3_modes.fl2va_prompt(action, seconds, camera=panel.camera or STATIC_CAMERA)


def make_clips(story: OriginalStory, ws: Path, ids: list[str] | None = None, timeout: float = 3600.0, progress: Callable[[str], None] = print, attempt: int = 0) -> dict:
    """One FL2VA clip per shot, `film/clips/<id>.mp4`, between its start and end picture, sound anchored to silence; the narrator's voice is written to `film/voice/<id>.wav` for the
    master. A clip newer than its pictures and prompt is reused."""
    from engine.narration.runtime import audio as rt
    from engine.original.animate import release_ollama

    fd = film.film_dir(ws)
    release_ollama()
    tts, voices = rt.KokoroTts(), film.film_voices(story, ws)
    log_path = fd / "clips.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    made, reused, failed = [], [], []
    for p in story.panels:
        if ids and p.id not in ids:
            continue
        start, end, out = fd / "frames" / f"{p.id}.png", fd / "frames" / f"{p.id}_end.png", fd / "clips" / f"{p.id}.mp4"
        if not (start.exists() and end.exists()):
            failed.append({"shot": p.id, "error": "no storyboard pictures"})
            continue
        spoken = film.voice_shot(story, ws, p, tts, voices)  # the narration wav (also fixes the take's minimum length)
        secs = max(film.snap_frames(p.seconds) / film.FPS, spoken[1] if spoken else 0)
        silent, secs = film.silent_shot(ws, p, secs)
        prompt = clip_prompt(story, p, secs)
        seed = int(hashlib.sha256(f"{story.bible.premise.title}|{p.id}|storyboard{f'|retry{attempt}' if attempt else ''}".encode()).hexdigest()[:12], 16)  # a retry is a new seed, nothing else
        sig = hashlib.sha256(f"{prompt}|{seed}|{secs}|{start.stat().st_mtime_ns}|{end.stat().st_mtime_ns}".encode()).hexdigest()[:16]
        if out.exists() and log.get(p.id, {}).get("sig") == sig:
            reused.append(p.id)
            continue
        progress(f"  clip {p.id}: {secs:.2f} s between its two pictures")
        t0 = time.monotonic()
        try:
            out.write_bytes(h3_modes.make_clip("fl2va", prompt, seed=seed, seconds=secs, first=start, last=end, voice=silent, timeout=timeout, prefix=f"video/sb_{p.id}"))
        except Exception as exc:
            failed.append({"shot": p.id, "error": str(exc)[:200]})
            continue
        log[p.id] = {"sig": sig, "seed": seed, "seconds": secs, "prompt": prompt, "workflow": "fastvideo_h3_film_fl2va_voice", "elapsed_s": round(time.monotonic() - t0, 1), "stats": film.clip_stats(out)}
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
        made.append(p.id)
    return {"made": made, "reused": reused, "failed": failed}


def landing(ws: Path, panel: Panel) -> dict:
    """How close the clip's first and last frames are to its two pictures (mean gray difference, 0-255): a clip that did not land on the storyboard is a defect."""
    from engine.original.continuity import edge_frames

    fd = ws / "film"
    first, last = edge_frames(fd / "clips" / f"{panel.id}.mp4")
    g = lambda im: cv2.cvtColor(cv2.resize(im, (384, 216)), cv2.COLOR_BGR2GRAY).astype(np.float32)  # noqa: E731
    ref = lambda name: g(cv2.imread(str(fd / "frames" / name)))  # noqa: E731
    return {"start_gray_diff": round(float(np.abs(g(first) - ref(f"{panel.id}.png")).mean()), 1), "end_gray_diff": round(float(np.abs(g(last) - ref(f"{panel.id}_end.png")).mean()), 1)}
