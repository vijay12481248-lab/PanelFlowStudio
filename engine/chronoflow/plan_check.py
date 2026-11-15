#!/usr/bin/env python3
"""Read and check a PanelFlow Plan v2 (film / cards). Usage: python check_plan.py plan.json   (standard library only; prints problems, exit 1 if any)."""
import json
import math
import re
import sys

W = lambda s: len(s.split())  # noqa: E731
STOP = set("the a an and or of to in on at with her his their she he they it is are be for by as that this through along one two over under into from up down then while there near above below around behind beside time shows show shown".split())
MOVE = re.compile(r"\b(walk|walks|walking|run|runs|running|jog|jogs|stride|strides|march|marches|travel|travels|head|heads|enter|enters|leave|leaves|approach|approaches|rush|rushes)\b", re.I)
WAY = re.compile(r"\b(toward|towards|away from|to the left|to the right|from left to right|from right to left|left to right|right to left|across the frame|forward|straight ahead)\b", re.I)
BANNED = re.compile(r"\b(text|caption|label|sign reading|words|subtitle|title card|letters)\b", re.I)
NEG = re.compile(r"\b(no|not|without|never|nothing|none)\b", re.I)
STACK = re.compile(r"\b(on (his|her|their|the) (shoulder|back|head|lap)|in (his|her|their) arms|carries|carrying|holds the (cat|dog|animal))\b", re.I)
SPEECH = re.compile(r"\b(says|said|speaks|speaking|talks|talking|asks|replies|whispers|shouts)\b", re.I)
CURLY = {0x201C: '"', 0x201D: '"', 0x2018: "'", 0x2019: "'"}  # curly quotes to straight ones (str.translate takes code points)
TRAIL = re.compile(r",(\s*[}\]])")  # a comma before a closing bracket
GENRES = {"bedtime", "horror", "mystery", "fantasy", "anime_adventure", "mythology", "vox", "explainer", "custom"}


def read_plan(text):
    """The plan object inside whatever a chatbot sent back: a code fence, a sentence before or after, a BOM, curly quotes, a trailing comma. ValueError says what is wrong."""
    t = (text or "").lstrip(chr(0xFEFF)).strip()  # a byte-order mark
    if not t:
        raise ValueError("The file is empty.")
    start, end = t.find("{"), t.rfind("}")
    if start < 0:
        raise ValueError("No JSON object found: the plan must start with { and end with }.")
    body = t[start : end + 1] if end > start else t[start:]
    err = None
    for fix in (lambda s: s, lambda s: s.translate(CURLY), lambda s: TRAIL.sub(lambda m: m.group(1), s.translate(CURLY))):
        try:
            data = json.loads(fix(body))
            break
        except ValueError as ex:
            err = ex
    else:
        raise ValueError(f"Not valid JSON: {err}")
    if not isinstance(data, dict):
        raise ValueError("The plan must be one JSON object.")
    return data


def stems(t):
    out = set()
    for w in re.findall(r"[a-z]+", t.lower()):
        if w in STOP or len(w) <= 2:
            continue
        for s in ("ing", "ed", "es", "s"):
            if w.endswith(s) and len(w) - len(s) >= 3:
                w = w[: -len(s)]
                break
        out.add(w[:5])
    return out


def check(p):
    e = []
    add = lambda m: e.append(m)  # noqa: E731
    if p.get("panelflow_plan") != 2:
        add('"panelflow_plan" must be 2')
    for k in ("title", "logline"):
        if not str(p.get(k, "")).strip():
            add(f'"{k}" is empty')
    for k in ("cast", "places", "scenes"):
        if not p.get(k):
            add(f'"{k}" is empty')
    if p.get("target") not in ("film", "cards"):
        add('"target" must be "film" or "cards" (the Short/Reel variant has its own checklist)')
    if p.get("format") not in ("16:9", "9:16"):
        add('"format" must be "16:9" or "9:16"')
    if p.get("genre") not in GENRES:
        add(f'"genre" must be one of {sorted(GENRES)}')
    pr = p.get("production", {})
    clip, total = pr.get("clip_seconds"), pr.get("total_seconds")
    if not isinstance(clip, (int, float)) or not 2 <= clip <= 60:
        add("production.clip_seconds must be a number from 2 to 60")
        clip = 5
    if not isinstance(total, (int, float)) or total <= 0:
        add("production.total_seconds must be a positive number")
        total = 0
    if pr.get("join") not in ("matched_pictures", "seamless_chain", "clip_tail"):
        add('production.join must be "matched_pictures", "seamless_chain" or "clip_tail"')
    narrated = pr.get("narration") == "narrator"
    if pr.get("narration") not in ("narrator", "none"):
        add('production.narration must be "narrator" or "none"')
    cast = {c.get("id"): c for c in p.get("cast", [])}
    places = {x.get("id") for x in p.get("places", [])}
    scenes = {s.get("id"): s for s in p.get("scenes", [])}
    for label, ids in (("cast", [c.get("id") for c in p.get("cast", [])]), ("places", [x.get("id") for x in p.get("places", [])]), ("scenes", list(scenes))):
        if len(ids) != len(set(ids)) or not all(re.fullmatch(r"[a-z0-9_]{1,24}", str(i)) for i in ids):
            add(f"{label}: ids must be unique and match [a-z0-9_]{{1,24}}")
    for c in cast.values():
        for k in ("name", "role", "species", "age_group", "gender", "look", "personality"):
            if not str(c.get(k, "")).strip():
                add(f"cast {c.get('id')}: missing {k}")
        if str(c.get("look", "")).count(",") < 2:
            add(f"cast {c.get('id')}: look must be comma-separated visual tags (at least 3), not a sentence")
    for x in p.get("places", []):
        if str(x.get("look", "")).count(",") < 1:
            add(f"place {x.get('id')}: look must be comma-separated visual tags")
    for s in scenes.values():
        if s.get("place") not in places:
            add(f"scene {s.get('id')}: place {s.get('place')!r} is not in places")
    takes = p.get("takes", [])
    if not takes:
        add("takes is empty")
    secs = sum(t.get("seconds", 0) for t in takes if isinstance(t.get("seconds"), (int, float)))
    if total and abs(secs - total) > max(clip, 1):
        add(f"the takes add up to {secs:g} s but production.total_seconds is {total:g} (allowed difference: one clip, {clip:g} s)")
    said, prev_scene = "", None
    for i, t in enumerate(takes):
        n = t.get("id", f"take {i + 1}")
        add_t = lambda m, n=n: add(f"{n}: {m}")  # noqa: E731
        if t.get("scene") not in scenes:
            add_t(f"scene {t.get('scene')!r} does not exist")
        sec = t.get("seconds")
        if not isinstance(sec, (int, float)) or not 1 <= sec <= clip + 1e-6:
            add_t(f"seconds must be a number from 1 to clip_seconds ({clip:g})")
            sec = clip
        if t.get("framing") not in ("wide", "medium", "close"):
            add_t('framing must be "wide", "medium" or "close"')
        if t.get("camera", "") not in ("", "slow push-in", "slow pan left", "slow pan right"):
            add_t('camera must be "" or "slow push-in", "slow pan left", "slow pan right"')
        tc = t.get("cast", [])
        for c in tc:
            if c not in cast:
                add_t(f"cast id {c!r} is not defined")
        start_from = t.get("start_from")
        if start_from not in ("new_picture", "previous_end", "clip_tail"):
            add_t('start_from must be "new_picture", "previous_end" or "clip_tail"')
        first_in_scene = t.get("scene") != prev_scene
        if first_in_scene and start_from != "new_picture":
            add_t('the first take of every scene must use start_from "new_picture" (a new place or time is a cut)')
        if start_from == "new_picture" and W(t.get("start_picture", "")) < 8:
            add_t("start_picture is needed (at least 8 words: who stands where in the frame, doing what)")
        if start_from in ("previous_end", "clip_tail") and t.get("start_picture"):
            add_t("start_picture must be left out when start_from is previous_end or clip_tail")
        if start_from == "previous_end" and i > 0 and sorted(t.get("cast", [])) != sorted(takes[i - 1].get("cast", [])) and takes[i - 1].get("end_picture"):
            add_t("a take that starts from the previous end picture must have the same cast as the previous take")
        if t.get("end_picture") is not None and W(t.get("end_picture", "")) < 8:
            add_t("end_picture needs at least 8 words (who stands where in the frame, doing what)")
        if W(t.get("motion", "")) < 6:
            add_t("motion needs one concrete action in at least 6 words")
        body = " ".join(str(t.get(k, "")) for k in ("start_picture", "motion", "end_picture"))
        if BANNED.search(body):
            add_t("pictures cannot hold readable text: remove words like text/caption/label/sign reading")
        if NEG.search(body):
            add_t("never name what must NOT appear (the video model draws every word you give it): rewrite without no/not/without/never")
        if SPEECH.search(body):
            add_t("nobody speaks on screen; the narration is a voice-over")
        if STACK.search(body):
            add_t("characters stand or sit separately, never on a shoulder, in arms or on a lap")
        for m in MOVE.finditer(body):
            if not WAY.search(" ".join(body[m.end():].split()[:8])):
                add_t("somebody moves without a direction: write 'to the left', 'to the right', 'toward the camera' or 'away from the camera' right after the verb")
                break
        names = [c["name"] for c in cast.values() if c.get("name")]
        for nm in names:
            for field in ("start_picture", "end_picture"):
                if nm.lower() in str(t.get(field, "")).lower() and next(k for k, v in cast.items() if v.get("name") == nm) not in tc:
                    add_t(f"{nm} appears in {field} but is not in this take's cast")
        bt = t.get("beats")
        if bt is not None:
            if clip < 8:
                add_t("beats are only for clip_seconds of 8 or more; with shorter clips write ONE action in motion")
            ats = [b.get("at") for b in bt if isinstance(b, dict)]
            if not bt or len(bt) > max(1, int(sec // 4)) or ats != sorted(ats) or any(not isinstance(a, (int, float)) or not 0 <= a < sec for a in ats):
                add_t(f"beats: use at most one beat per 4 s ({max(1, int(sec // 4))} here), with increasing 'at' seconds inside the take")
            if any(not isinstance(b, dict) or W(b.get("action", "")) < 6 for b in bt):
                add_t("each beat needs an 'action' of at least 6 words")
        if narrated:
            b = int(max(1.0, sec - 0.8) * 2.8)
            wc = W(t.get("narration", ""))
            if not math.ceil(b * 0.6) <= wc <= b:
                add_t(f"narration has {wc} words; for {sec:g} s write {int(b * 0.9)} (allowed {math.ceil(b * 0.6)}-{b})")
            if not 4 <= W(t.get("shows", "")) <= 25:
                add_t('"shows" must name the ONE visible thing that carries this take (4-25 words)')
            elif not stems(t["shows"]) & stems(t.get("narration", "")):
                add_t("the narration must mention what the viewer sees (the words in \"shows\")")
            mine = stems(t.get("narration", ""))
            if said and mine and len(mine & stems(said)) / len(mine) > 0.7:
                add_t("the narration repeats what earlier takes already said; explain the NEXT step")
            said += " " + t.get("narration", "")
        prev_scene = t.get("scene")
    if pr.get("join") == "seamless_chain":
        if len(scenes) > 1 or any(t.get("start_from") != "previous_end" for t in takes[1:]) or len({t.get("framing") for t in takes}) > 1:
            add("join seamless_chain needs ONE scene, every take after the first starting from previous_end, and the same framing in every take")
        if p.get("format") != "16:9" or clip > 5:
            add("join seamless_chain is 16:9 only and about 4.5 s per clip (clip_seconds 4.5)")
    return e


if __name__ == "__main__":
    try:
        plan = read_plan(open(sys.argv[1], encoding="utf-8").read())
    except Exception as ex:  # noqa: BLE001
        sys.exit(str(ex))
    problems = check(plan)
    print("\n".join(f"- {m}" for m in problems) or "OK: no problems found")
    sys.exit(1 if problems else 0)
