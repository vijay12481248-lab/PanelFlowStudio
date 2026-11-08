"""Explainer spec -> validated OriginalStory (the authoring format of the channel's "why does X happen?" flat-picture videos).

One text file per video (UTF-8, '#' comments, one record per line, fields split on ' | '):

    title:    Why Do We Yawn? The 3 Jobs of a Yawn
    slug:     vox_yawn
    logline:  one sentence for the description
    hook:     first description line (what the viewer gets)      [optional]
    cta:      comment prompt                                        [optional]
    tags:     why do we yawn, science of yawning, ...               [optional]
    thumb:    WORDS | p012                                          [1-3 words that do NOT repeat the title | panel id]
    char:     id | Name | role | age_group | species | gender | look | personality      [only for cast outside the library]
    loc:      id | Name | look                                                           [only for places outside the library]
    scene:    s1 | location_id | mood | chapter title | summary
    beat:     shot | location_id | char,char | narration (<= 24 words) | visual (what the picture shows, faces and feelings) | key; key   [last field optional]
    beat@p007a: ...   (explicit id: inserted beats keep every other picture's id, so a redraw only touches what changed)

The narration is the spoken line; the visual is what the art model draws (the system's prompt composer still writes the actual prompts).
`build_story` raises ValueError listing EVERY problem at once; `lint` returns warnings that do not block. Measured rules behind the checks:
a picture with no character in a "close" shot draws a stray person (so zero-character beats are forced to "wide"); only two characters are
drawn per picture; "red eyes" in a visual is drawn as blood; a character named in the narration must be in the picture or the picture
contradicts the words.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from engine.original.models import Bible, Character, Location, OriginalStory, Panel, Premise, Scene

MAX_WORDS = 24
MIN_WORDS = 6
MIN_SECONDS = 180.0  # the channel's floor
SECONDS_PER_WORD = 0.365  # measured on "Why Do We Cry?": 841 words -> 304 s with 39 beats
SHOTS = {"wide", "medium", "close", "extreme_close", "over_shoulder", "full", "full_body"}

# the channel's recurring cast and places (look strings are the ones the finished videos were drawn with)
CAST = {
    "maya": Character(id="maya", name="Maya", role="protagonist", age_group="adult", gender="female",
                      look="short black bob haircut, medium brown skin, dark brown eyes, round glasses, bright yellow hoodie, blue jeans",
                      personality="warm, tired, easily startled, curious"),
    "biscuit": Character(id="biscuit", name="Biscuit", role="companion", age_group="adult", species="cat", gender="male",
                         look="chubby orange tabby fur, white front paws, big green eyes, pink nose, blue collar with a gold tag",
                         personality="deadpan, patient, secretly a scientist"),
    "dev": Character(id="dev", name="Dev", role="other", age_group="adult", gender="male",
                     look="tall young man, short curly dark hair, light brown skin, kind brown eyes, no glasses, forest green sweater, grey trousers",
                     personality="shy, kind, bad at goodbyes"),
    "baby": Character(id="baby", name="Baby", role="other", age_group="child", gender="neutral",
                      look="tiny newborn baby, round face, small tuft of black hair, white onesie", personality="loud, sleepy"),
    "nana": Character(id="nana", name="Nana", role="other", age_group="elder", gender="female",
                      look="elderly woman, short silver curly hair, warm brown skin, round cheeks, lavender cardigan, kind eyes with laugh lines",
                      personality="warm, funny, full of stories"),
    "leo": Character(id="leo", name="Leo", role="other", age_group="child", gender="male",
                     look="eight year old boy, messy brown hair, freckles, big curious eyes, red t-shirt with a yellow star",
                     personality="endlessly curious, asks why about everything"),
    "priya": Character(id="priya", name="Priya", role="other", age_group="adult", gender="female",
                       look="woman scientist, long black braid, warm tan skin, white lab coat over a teal shirt, small gold earrings, no glasses",
                       personality="calm, clear, loves a good question"),
    "mochi": Character(id="mochi", name="Mochi", role="companion", age_group="adult", species="dog", gender="male",
                       look="small fluffy cream-colored dog, floppy ears, black nose, warm brown eyes, red bandana around the neck",
                       personality="loyal, goofy, always hopeful"),
}
PLACES = {
    "living_room": Location(id="living_room", name="Cozy Living Room",
                            look="cozy apartment living room in the evening, grey sofa, warm yellow lamp, television, tissue box on a wooden coffee table"),
    "kitchen": Location(id="kitchen", name="Sunny Kitchen",
                        look="small sunny apartment kitchen, wooden table, white walls, green plant on the window sill"),
    "diagram": Location(id="diagram", name="Explainer Backdrop",
                        look="plain deep navy blue explainer backdrop, clean empty space, simple bright canary yellow flat diagram shapes, no text"),
    "hallway": Location(id="hallway", name="Apartment Hallway",
                        look="apartment hallway outside a front door, warm yellow hallway light, a few cardboard moving boxes stacked against the wall"),
    "bedroom": Location(id="bedroom", name="Bedroom",
                        look="small cozy bedroom, bed with a blue blanket, bedside lamp with warm yellow light, window with a night sky"),
    "park": Location(id="park", name="City Park",
                     look="sunny city park, green grass, a wooden bench, big leafy trees, a path, blue sky with a few white clouds"),
    "classroom": Location(id="classroom", name="Classroom",
                          look="bright school classroom, rows of wooden desks, a green chalkboard with no writing, big window, a globe on a shelf"),
    "office": Location(id="office", name="Office",
                       look="open-plan office, desks with laptops, a big window, a green plant, a meeting table with chairs, bright daylight"),
    "stage": Location(id="stage", name="Small Theatre Stage",
                      look="small theatre stage with deep red curtains, a single bright spotlight circle on the wooden floor, dark audience seats beyond"),
    "nursery": Location(id="nursery", name="Nursery",
                        look="small dim nursery at night, wooden crib, soft yellow night lamp, star mobile hanging above the crib"),
    "cafe": Location(id="cafe", name="Cafe",
                     look="cozy cafe interior, wooden tables, hanging warm lamps, a counter with pastries, a big window with a street view"),
    "vet": Location(id="vet", name="Vet Room",
                    look="small veterinary exam room, a steel examination table, a poster of a cat on the wall, white walls, bright clinical light"),
    "attic": Location(id="attic", name="Attic",
                      look="cozy attic with wooden beams, dusty cardboard boxes, a small round window with warm golden light, an old wooden trunk"),
    "shelter": Location(id="shelter", name="Animal Shelter",
                        look="animal shelter hallway with rows of kennels with chain-link doors, a clean concrete floor, warm yellow ceiling lights"),
    "pool": Location(id="pool", name="Swimming Pool",
                     look="sunny outdoor swimming pool with bright blue water, a white tiled edge, a lifeguard chair, clear blue sky"),
    "auditorium": Location(id="auditorium", name="School Auditorium",
                           look="school auditorium with rows of red seats, a small stage with a red curtain, warm dim lighting"),
    "street": Location(id="street", name="City Street",
                       look="quiet city street in the afternoon, apartment buildings, a tree, a bus stop bench, clear blue sky"),
}


def _words(text: str) -> int:
    return len(text.split())


def estimate_seconds(story: OriginalStory) -> float:
    return sum(_words(p.caption) for p in story.panels) * SECONDS_PER_WORD


def _split(line: str, n: int, where: str, errs: list[str]) -> list[str] | None:
    parts = [x.strip() for x in re.split(r"\s*\|\s*", line)]  # an empty field is just "| |"
    if len(parts) != n:
        errs.append(f"{where}: expected {n} fields split by ' | ', got {len(parts)}")
        return None
    return parts


SHORT_MAX_WORDS = 140  # measured pace 0.365 s per spoken word -> about 51 s, safely inside the 60 s a Short is shown as a Short
SHORT_MIN_BEATS = 4
EXPLAINER_DIR = Path(__file__).resolve().parents[2] / "stories" / "explainers"


def is_short(text: str) -> bool:
    return re.search(r"^from:", text, re.M) is not None


def parse_short(text: str) -> dict:
    """Short spec -> {from, title, slug, hook, cta, tags, uses: [(beat id, narration)]}. A Short REUSES beats (visual, cast, place) of a full
    video by id and gives each its own narration; it is drawn 9:16 in its own workspace (`<slug>`), reusing the full video's character sheets.

        from: 01_yawn.txt     title: ...     slug: vox_yawn_short     hook: ...     cta: ...     tags: a, b
        use: p001 | the new, shorter narration for that beat
    """
    out: dict = {"uses": []}
    errs: list[str] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-z]+):\s*(.*)$", line)
        if not m:
            errs.append(f"line {n}: not 'key: value'")
        elif m.group(1) == "use":
            f = re.split(r"\s*\|\s*", m.group(2), maxsplit=2)
            if len(f) not in (2, 3) or not re.fullmatch(r"p\w+", f[0]):
                errs.append(f"line {n}: use: needs 'pNNN | narration [| a new visual for the 9:16 picture]'")
            else:
                out["uses"].append((f[0], f[1], f[2] if len(f) == 3 else ""))
        elif m.group(1) in ("from", "title", "slug", "hook", "cta", "tags"):
            out[m.group(1)] = m.group(2)
        else:
            errs.append(f"line {n}: unknown key '{m.group(1)}'")
    for k in ("from", "title", "slug"):
        if not out.get(k):
            errs.append(f"missing '{k}:'")
    if errs:
        raise ValueError("\n".join(errs))
    return out


def build_short(text: str, specs_dir: Path | None = None) -> OriginalStory:
    sp = parse_short(text)
    parent_text = ((specs_dir or EXPLAINER_DIR) / sp["from"]).read_text(encoding="utf-8")
    parent = build_story(parent_text)
    pm = {p.id: p for p in parent.panels}
    errs: list[str] = []
    for pid, _, _ in sp["uses"]:
        if pid not in pm:
            errs.append(f"use: {pid} is not a beat of {sp['from']}")
    words = sum(_words(n) for _, n, _ in sp["uses"])
    if words > SHORT_MAX_WORDS:
        errs.append(f"{words} narrated words; a Short holds at most {SHORT_MAX_WORDS} (about 51 s)")
    if len(sp["uses"]) < SHORT_MIN_BEATS:
        errs.append(f"{len(sp['uses'])} beats; at least {SHORT_MIN_BEATS}")
    if len({pid for pid, _, _ in sp["uses"]}) != len(sp["uses"]):
        errs.append("a beat is used twice")
    if errs:
        raise ValueError("\n".join(errs))
    custom = [ln for ln in parent_text.splitlines() if re.match(r"^(char|loc):", ln.strip())]
    first = pm[sp["uses"][0][0]]
    lines = [f"title: {sp['title']}", f"slug: {sp['slug']}", f"logline: {sp.get('hook') or sp['title']}", *custom,
             f"scene: s1 | {first.location_id} | punchy | {sp['title']} | {sp['title']}"]
    for pid, narr, visual in sp["uses"]:
        b = pm[pid]
        lines.append(f"beat@{pid}: {b.shot} | {b.location_id} | {','.join(b.character_ids)} | {narr} | {visual or b.action} | {'; '.join(b.key_visuals)}")
    story = build_story("\n".join(lines))
    tags = [t.strip() for t in sp["tags"].split(",") if t.strip()] if sp.get("tags") else None
    story.meta = {**{k: v for k, v in {"hook": sp.get("hook"), "cta": sp.get("cta"), "tags": tags}.items() if v}, "frame": "9:16"}
    return story


def parent_slug(text: str, specs_dir: Path | None = None) -> str:
    """Slug of the full video a Short was cut from (its character sheets are reused)."""
    return parse(((specs_dir or EXPLAINER_DIR) / parse_short(text)["from"]).read_text(encoding="utf-8"))["slug"]


def parse(text: str) -> dict:
    """Spec text -> raw records (no validation of meaning)."""
    if is_short(text):
        return parse_short(text)
    spec: dict = {"chars": [], "locs": [], "scenes": [], "beats": []}
    errs: list[str] = []
    cur_scene = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(beat)(?:@([A-Za-z0-9_]+))?:\s*(.*)$", line) or re.match(r"^([a-z]+):\s*(.*)$", line)
        if not m:
            errs.append(f"line {n}: not 'key: value'")
            continue
        key = m.group(1)
        if key == "beat":
            body = m.group(3)
            if len(re.split(r"\s*\|\s*", body)) == 5:  # the key-visuals field is optional
                body += " | "
            f = _split(body, 6, f"line {n} (beat)", errs)
            if f:
                spec["beats"].append({"id": m.group(2), "shot": f[0], "loc": f[1], "chars": [c for c in f[2].replace(" ", "").split(",") if c],
                                      "narration": f[3], "visual": f[4], "keys": [k.strip() for k in f[5].split(";") if k.strip()], "line": n,
                                      "scene": cur_scene})
            continue
        val = m.group(2)
        if key == "char":
            f = _split(val, 8, f"line {n} (char)", errs)
            if f:
                spec["chars"].append(f)
        elif key == "loc":
            f = _split(val, 3, f"line {n} (loc)", errs)
            if f:
                spec["locs"].append(f)
        elif key == "scene":
            f = _split(val, 5, f"line {n} (scene)", errs)
            if f:
                spec["scenes"].append(f)
                cur_scene = f[0]
        elif key in ("title", "slug", "logline", "hook", "cta", "tags", "thumb", "setting", "tone"):
            spec[key] = val
        else:
            errs.append(f"line {n}: unknown key '{key}'")
    if errs:
        raise ValueError("\n".join(errs))
    return spec


def build_story(text: str) -> OriginalStory:
    if is_short(text):
        return build_short(text)
    spec = parse(text)
    errs: list[str] = []
    for k in ("title", "slug", "logline"):
        if not spec.get(k):
            errs.append(f"missing '{k}:'")
    chars = dict(CAST)
    for cid, name, role, age, species, gender, look, pers in spec["chars"]:
        chars[cid] = Character(id=cid, name=name, role=role, age_group=age, species=species or "human", gender=gender, look=look, personality=pers)
    places = dict(PLACES)
    for lid, name, look in spec["locs"]:
        places[lid] = Location(id=lid, name=name, look=look)
    scene_ids = [s[0] for s in spec["scenes"]]
    if not spec["scenes"]:
        errs.append("no 'scene:' lines")
    if len(set(scene_ids)) != len(scene_ids):
        errs.append("duplicate scene ids")
    panels: list[Panel] = []
    seen_ids: set[str] = set()
    counter = 0
    for b in spec["beats"]:
        sid = b["scene"]
        w = f"line {b['line']}"
        if sid is None:
            errs.append(f"{w}: beat before any scene")
            continue
        if b["id"]:
            pid = b["id"]
        else:  # an explicit id never consumes a number, so inserting p007a leaves p008.. alone
            counter += 1
            pid = f"p{counter:03d}"
        if pid in seen_ids:
            errs.append(f"{w}: duplicate beat id {pid}")
        seen_ids.add(pid)
        nwords = _words(b["narration"])
        if not MIN_WORDS <= nwords <= MAX_WORDS:
            errs.append(f"{w} ({pid}): narration has {nwords} words, must be {MIN_WORDS}-{MAX_WORDS}: {b['narration'][:60]}")
        if b["shot"] not in SHOTS:
            errs.append(f"{w} ({pid}): shot '{b['shot']}' not in {sorted(SHOTS)}")
        if b["loc"] not in places:
            errs.append(f"{w} ({pid}): unknown location '{b['loc']}'")
        for c in b["chars"]:
            if c not in chars:
                errs.append(f"{w} ({pid}): unknown character '{c}'")
        if len(b["chars"]) > 2:
            errs.append(f"{w} ({pid}): {len(b['chars'])} characters, at most 2 are drawn per picture")
        if _words(b["visual"]) < 6:
            errs.append(f"{w} ({pid}): visual is too short to draw from")
        # "red wet eyes" is drawn as blood around the eyes (measured); a red FACE (a blush) is fine, so only red that directly describes the eyes is refused
        if re.search(r"\bred[\s-]+(?:\w+[\s-]+){0,2}eyes?\b|\beyes? (?:are |is |turn(?:s|ed)? |look(?:s|ed)? )?red\b|bloodshot|\bblood(?!\s+(?:vessels?|flow|sugar|pressure|cells?|test))", b["visual"], re.I):
            errs.append(f"{w} ({pid}): red eyes (or blood) are drawn as blood; say 'clear light-blue tears, clean white eyes'")
        for c in chars.values():
            if re.search(rf"\b{re.escape(c.name)}(?:'s)?\b", b["narration"]) and c.id not in b["chars"]:
                errs.append(f"{w} ({pid}): the narration names {c.name} but {c.id} is not in the picture's characters")
        shot = b["shot"] if b["chars"] else "wide"  # zero-character 'close' shots draw a stray person
        panels.append(Panel(id=pid, scene_id=sid or "", shot=shot, angle="eye_level", location_id=b["loc"], character_ids=b["chars"],
                            action=b["visual"], caption=b["narration"], key_visuals=b["keys"]))
    for s in spec["scenes"]:
        if s[1] not in places:
            errs.append(f"scene {s[0]}: unknown location '{s[1]}'")
        if not any(p.scene_id == s[0] for p in panels):
            errs.append(f"scene {s[0]} has no beats")
    thumb = [x.strip() for x in spec.get("thumb", "").split("|")]
    if spec.get("thumb"):
        words = thumb[0].split()
        if not 1 <= len(words) <= 3:
            errs.append("thumb: 1-3 words")
        if len(thumb) > 1 and thumb[1] not in seen_ids:
            errs.append(f"thumb: panel '{thumb[1]}' does not exist")
        if set(w.lower().strip("?!.,") for w in words) & set(w.lower().strip("?!.,") for w in spec.get("title", "").split() if len(w) > 3):
            errs.append("thumb: the thumbnail words repeat the title; use different words")
    if errs:
        raise ValueError("\n".join(errs))
    scenes = [Scene(id=sid, location_id=loc, character_ids=sorted({c for p in panels if p.scene_id == sid for c in p.character_ids}),
                    summary=summary, mood=mood, title=chapter) for sid, loc, mood, chapter, summary in spec["scenes"]]
    used = {c for p in panels for c in p.character_ids}
    used_locs = {p.location_id for p in panels} | {s.location_id for s in scenes}
    meta = {"frame": "16:9", **{k: v for k, v in {"hook": spec.get("hook"), "cta": spec.get("cta"),
                              "tags": [t.strip() for t in spec["tags"].split(",") if t.strip()] if spec.get("tags") else None,
                              "thumb_text": thumb[0] if spec.get("thumb") else None,
                              "thumb_panel": thumb[1] if len(thumb) > 1 else None}.items() if v}}
    bible = Bible(premise=Premise(title=spec["title"], genre="vox", logline=spec["logline"], tone=spec.get("tone", "witty, warm, curious"),
                                  setting=spec.get("setting", "Maya's apartment and the explainer backdrop.")),
                  characters=[chars[c] for c in chars if c in used], locations=[places[p] for p in places if p in used_locs],
                  rules=["Flat 2D vector art, no text or letters inside any picture", "Maya always wears round glasses and a bright yellow hoodie"])
    return OriginalStory(bible=bible, scenes=scenes, panels=panels, meta=meta)


def lint(story: OriginalStory) -> list[str]:
    """Non-blocking observations about a built story."""
    out: list[str] = []
    secs = estimate_seconds(story)
    if (story.meta or {}).get("frame") == "9:16":
        if secs > 56:
            out.append(f"estimated {secs:.0f}s is too long for a Short (aim under 56 s)")
        return out
    if secs < MIN_SECONDS:
        out.append(f"estimated {secs:.0f}s is under the channel floor of {MIN_SECONDS:.0f}s")
    if secs > 420:
        out.append(f"estimated {secs:.0f}s is long for this format (aim 3-6 minutes)")
    narr = [p.caption.lower() for p in story.panels]
    if len(set(narr)) != len(narr):
        out.append("repeated narration line")
    acts = [p.action.lower() for p in story.panels]
    if len(set(acts)) != len(acts):
        out.append("two beats have an identical visual")
    for p in story.panels:  # the art model cannot count past two (measured: "four fingers" drew three, "four circles" drew five)
        m = re.search(r"\b(three|four|five|six|seven|eight|nine|ten|[3-9])\b\s+(?:small |flat |glowing |yellow |round |tiny )*(?:fingers?|circles?|dots?|stars?|icons?|arrows?|hearts?|faces?|people|cups?|toys?|lines?)", p.action, re.I)
        if m:
            out.append(f"{p.id}: the visual asks for a count ('{m.group(0)}'); the picture will not match it, describe 'a few' or an arrangement")
    run = 0
    for p in story.panels:  # a long run of the same place with the same cast is a slideshow of one picture
        run = run + 1 if p.location_id == "diagram" else 0
        if run > 4:
            out.append(f"{p.id}: more than 4 diagram beats in a row")
    return out


def write_story(spec_path: Path, root: Path) -> tuple[OriginalStory, Path]:
    story = build_story(spec_path.read_text(encoding="utf-8"))
    slug = parse(spec_path.read_text(encoding="utf-8"))["slug"]
    ws = root / slug
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "story.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    return story, ws


if __name__ == "__main__":
    here = Path(__file__).resolve().parents[2]
    story, ws = write_story(Path(sys.argv[1]), here / "output" / "Original_Stories")
    print(f"{len(story.panels)} beats, {len(story.scenes)} scenes, ~{estimate_seconds(story):.0f}s -> {ws}")
    for w in lint(story):
        print("WARN", w)
