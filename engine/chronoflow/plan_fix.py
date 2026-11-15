"""Automatic repairs for an uploaded Video Plan (the rules live in plan_check.py).

Only things that can be repaired without guessing the story: names and codes (ids, enums, numbers), defaults for optional fields, structure the rules imply
(who starts from the previous picture, the total length), and mechanical text rules the pipeline's own validators apply (a direction after a verb of travel,
"face" for "head", one character per clause, negated or text-in-picture clauses removed, narration cut to its length budget). Nothing is ever invented about the
story: a missing end picture, a narration that is too short or a missing `shows` stays a problem. Every repair is returned as a plain sentence for the owner.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any

from engine.chronoflow import plan_check as pc

ROLES = ("protagonist", "companion", "antagonist", "mentor", "other")
AGES = ("child", "teen", "adult", "elder")
GENDERS = ("male", "female", "neutral")
NARRATOR_WORDS = {"narrator", "narration", "voice-over", "voiceover", "voice over", "voice", "yes", "true", "on"}
NO_NARRATION_WORDS = {"none", "no", "false", "off", "silent", "silence", ""}
CONNECTIVE = r"(?:,|\b(?:with|and|beside|next to|alongside|while|as)\b)"
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
TAGIFY = re.compile(r"\s*(?:;|\.\s+|\bwith\b|\band\b|\bwearing\b|\bwho has\b|\bhas\b)\s*", re.I)


def slug(text: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(text).lower()).strip("_")[:24] or "x"


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(m.group()) if m else None


def tidy_number(x: float) -> int | float:
    return int(x) if float(x).is_integer() else round(x, 2)


def words(text: Any) -> int:
    return len(str(text or "").split())


def tagify(text: str) -> str:
    parts = [p.strip(" ,.") for p in TAGIFY.split(text) if p and p.strip(" ,.")]
    return ", ".join(parts)


def normalize_framing(text: str) -> str:
    t = text.strip().lower()
    if "close" in t or "detail" in t or "macro" in t:
        return "close"
    if any(w in t for w in ("wide", "establishing", "long", "full", "aerial", "master", "landscape")):
        return "wide"
    return "medium"


def normalize_camera(text: str) -> str:
    t = text.strip().lower()
    if "push" in t or "zoom in" in t or "dolly in" in t:
        return "slow push-in"
    if "pan" in t and "left" in t:
        return "slow pan left"
    if "pan" in t and "right" in t:
        return "slow pan right"
    return ""


def drop_clauses(text: str, rule: re.Pattern, min_words: int) -> tuple[str, bool]:
    """Remove the `;`/`,`-separated pieces that match `rule`, unless too little text would be left."""
    parts = re.split(r"([;,])", text)
    pieces = [(parts[i], parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)]
    kept = [(p, s) for p, s in pieces if not rule.search(p)]
    if len(kept) == len(pieces) or not kept:
        return text, False
    out = "".join(p + s for p, s in kept).rstrip(" ,;")
    if text.rstrip().endswith("."):
        out = out.rstrip(".") + "."
    return (out, True) if words(out) >= min_words else (text, False)


def insert_direction(text: str, way: str) -> tuple[str, bool]:
    out, pos, changed = [], 0, False
    for m in pc.MOVE.finditer(text):
        out.append(text[pos:m.end()])
        if not pc.WAY.search(" ".join(text[m.end():].split()[:8])):
            out.append(f" {way}")
            changed = True
        pos = m.end()
    return "".join(out) + text[pos:], changed


def split_two_names(text: str, names: list[str]) -> tuple[str, bool]:
    """A clause that names two characters: start a new clause (`;`) at the second name."""
    changed = False
    for _ in range(6):
        hit = None
        for clause in pc.CLAUSE.split(text):
            found = sorted((m.start(), n) for n in names for m in [re.search(r"\b" + re.escape(n) + r"\b", clause, re.I)] if m)
            if len(found) > 1:
                hit = (clause, found[1][0])
                break
        if hit is None:
            break
        clause, at = hit
        cut = re.search(r"\s*" + CONNECTIVE + r"?\s*$", clause[:at], re.I)
        new = clause[:cut.start()].rstrip() + "; " + clause[at:]
        text, changed = text.replace(clause, new, 1), True
    return text, changed


class Fixer:
    def __init__(self, plan: dict[str, Any]):
        self.p = plan
        self.changes: list[str] = []

    def note(self, message: str) -> None:
        if message not in self.changes:
            self.changes.append(message)

    # ---- the plan as a whole
    def top(self) -> None:
        p = self.p
        if p.get("panelflow_plan") != 2:
            p["panelflow_plan"] = 2
            self.note('set "panelflow_plan" to 2')
        target = str(p.get("target") or "").strip().lower()
        if target not in ("film", "cards", "short"):
            p["target"] = "cards" if "card" in target else "film"
            self.note(f'"target" was {target!r}: set to "{p["target"]}"')
        elif p.get("target") != target:
            p["target"] = target
        if not str(p.get("title") or "").strip():
            p["title"] = "Untitled video"
            self.note('"title" was empty: set to "Untitled video"')
        if not str(p.get("logline") or "").strip():
            p["logline"] = str(p["title"])
            self.note('"logline" was empty: used the title')
        fmt = str(p.get("format") or "").strip().lower().replace(" ", "")
        want = "9:16" if fmt in ("9:16", "9x16", "vertical", "portrait", "shorts", "short") else "16:9"
        if p.get("format") != want:
            p["format"] = want
            self.note(f'"format" was {p.get("format")!r}: set to "{want}"' if fmt else '"format" was missing: set to "16:9"')
        genre = re.sub(r"[\s-]+", "_", str(p.get("genre") or "").strip().lower())
        if genre not in pc.GENRES:
            self.note(f'"genre" was {p.get("genre")!r}: set to "custom" (the explainer look)')
            genre = "custom"
        p["genre"] = genre
        if not isinstance(p.get("style"), str):
            p["style"] = ""
            self.note('"style" was not text: set to empty')
        if not isinstance(p.get("rules"), list):
            p["rules"] = []
            self.note('"rules" was missing: set to an empty list')

    # ---- cast, places, scenes (ids and defaults)
    def _lookup(self, items: list[dict[str, Any]], what: str, name_key: str | None) -> dict[str, str]:
        used, table = set(), {}
        for it in items:
            old = it.get("id")
            base = slug(old if old else (it.get(name_key) if name_key else "") or what)
            new, n = base, 2
            while new in used:
                new, n = f"{base[:21]}_{n}", n + 1
            used.add(new)
            if old != new:
                self.note(f'{what} id {old!r} became "{new}" (ids use lowercase letters, digits and _)')
            for key in (old, slug(old) if old else None, it.get(name_key) if name_key else None, slug(it.get(name_key)) if name_key and it.get(name_key) else None):
                if key:
                    table.setdefault(str(key).strip().lower(), new)
            it["id"] = new
        return table

    def structure(self) -> dict[str, dict[str, str]]:
        p = self.p
        for key in ("cast", "places", "scenes", "takes"):
            if not isinstance(p.get(key), list):
                p[key] = []
            p[key] = [x for x in p[key] if isinstance(x, dict)]
        cast_t = self._lookup(p["cast"], "cast", "name")
        place_t = self._lookup(p["places"], "place", "name")
        for i, s in enumerate(p["scenes"], 1):
            s.setdefault("id", f"s{i}")
        scene_t = self._lookup(p["scenes"], "scene", "title")
        for c in p["cast"]:
            missing = []
            if not str(c.get("name") or "").strip():
                c["name"] = str(c["id"]).replace("_", " ").title()
                missing.append("name")
            role = str(c.get("role") or "").strip().lower()
            if role not in ROLES:
                c["role"] = "other"
                missing.append("role")
            age = str(c.get("age_group") or "").strip().lower()
            if age not in AGES:
                c["age_group"] = "child" if re.search(r"child|kid|boy|girl", age) else "teen" if "teen" in age else "elder" if re.search(r"old|elder", age) else "adult"
                missing.append("age_group")
            gender = str(c.get("gender") or "").strip().lower()
            if gender not in GENDERS:
                c["gender"] = "female" if re.search(r"\b(female|woman|girl|she)\b", gender) else "male" if re.search(r"\b(male|man|boy|he)\b", gender) else "neutral"
                missing.append("gender")
            for key, default in (("species", "human"), ("personality", "calm")):
                if not str(c.get(key) or "").strip():
                    c[key] = default
                    missing.append(key)
            if missing:
                self.note(f"cast {c['id']}: filled in {', '.join(missing)} with plain defaults")
            look = str(c.get("look") or "")
            if look and look.count(",") < 2:
                tags = tagify(look)
                if tags != look:
                    c["look"] = tags
                    self.note(f"cast {c['id']}: wrote the look as comma-separated tags")
        for x in p["places"]:
            if not str(x.get("name") or "").strip():
                x["name"] = str(x["id"]).replace("_", " ").title()
            look = str(x.get("look") or "")
            if look and look.count(",") < 1:
                tags = tagify(look)
                if tags != look:
                    x["look"] = tags
                    self.note(f"place {x['id']}: wrote the look as comma-separated tags")
        for s in p["scenes"]:
            place = str(s.get("place") or "").strip().lower()
            mapped = place_t.get(place) or place_t.get(slug(place)) or (p["places"][0]["id"] if p["places"] else s.get("place"))
            if s.get("place") != mapped:
                s["place"] = mapped
                self.note(f"scene {s['id']}: place set to \"{mapped}\"")
            filled = [k for k, v in (("title", s["id"].replace("_", " ").title()), ("summary", None), ("mood", "neutral"), ("music", "")) if k not in s or (k in ("title", "summary", "mood") and not str(s.get(k) or "").strip())]
            for k in filled:
                s[k] = s["title"] if k == "summary" and s.get("title") else {"title": s["id"].replace("_", " ").title(), "mood": "neutral", "music": ""}.get(k, "")
            if filled:
                self.note(f"scene {s['id']}: filled in {', '.join(filled)}")
        return {"cast": cast_t, "scene": scene_t}

    # ---- production settings
    def production(self) -> None:
        p = self.p
        if not isinstance(p.get("production"), dict):
            p["production"] = {}
            self.note('"production" was missing: created it')
        pr = p["production"]
        longest = max([number(t.get("seconds")) or 0 for t in p["takes"]] or [0])
        clip = number(pr.get("clip_seconds"))
        if clip is None or not 2 <= clip <= 60:
            clip = min(60.0, max(2.0, longest or 5.0))
            self.note(f'"clip_seconds" was {pr.get("clip_seconds")!r}: set to {tidy_number(clip)}')
        pr["clip_seconds"] = tidy_number(clip) if pr.get("clip_seconds") != tidy_number(clip) else pr["clip_seconds"]
        join = str(pr.get("join") or "").strip().lower()
        want = "seamless_chain" if "seamless" in join else "matched_pictures"
        if pr.get("join") != want:
            self.note(f'"join" was {pr.get("join")!r}: set to "{want}"' if pr.get("join") else '"join" was missing: set to "matched_pictures"')
            pr["join"] = want
        narr = pr.get("narration")
        key = str(narr).strip().lower() if not isinstance(narr, bool) else ("true" if narr else "false")
        has_text = any(str(t.get("narration") or "").strip() for t in p["takes"])
        if key in NARRATOR_WORDS:
            want_n = "narrator"
        elif key in NO_NARRATION_WORDS and narr is not None:
            want_n = "none"
        else:
            want_n = "narrator" if has_text else "none"
        if narr != want_n:
            pr["narration"] = want_n
            self.note(f'"narration" was {narr!r}: set to "{want_n}"' if narr is not None else f'"narration" was missing: set to "{want_n}"')
        if not isinstance(pr.get("music"), str) or not pr["music"].strip():
            pr["music"] = "none"
            self.note('"music" was missing: set to "none"')

    # ---- one take
    def take(self, i: int, t: dict[str, Any], prev: dict[str, Any] | None, tables: dict[str, dict[str, str]]) -> None:
        p, pr = self.p, self.p["production"]
        tid = t["id"]
        names = [c["name"] for c in p["cast"]]
        scene = str(t.get("scene") or "").strip().lower()
        mapped = tables["scene"].get(scene) or tables["scene"].get(slug(scene)) or (prev["scene"] if prev else (p["scenes"][0]["id"] if p["scenes"] else t.get("scene")))
        if t.get("scene") != mapped:
            t["scene"] = mapped
            self.note(f'{tid}: scene set to "{mapped}"')
        clip = number(pr["clip_seconds"]) or 5.0
        sec = number(t.get("seconds"))
        new_sec = clip if sec is None else max(1.0, min(sec, clip))
        if sec is None or abs(new_sec - sec) > 1e-9 or not isinstance(t.get("seconds"), (int, float)) or isinstance(t.get("seconds"), bool):
            t["seconds"] = tidy_number(new_sec)
            self.note(f"{tid}: length {t.get('seconds') if sec is None else tidy_number(sec)!s} s became {tidy_number(new_sec)} s (the clip length is {tidy_number(clip)} s)")
        if t.get("framing") not in ("wide", "medium", "close"):
            t["framing"] = normalize_framing(str(t.get("framing") or ""))
            self.note(f'{tid}: framing set to "{t["framing"]}"')
        if t.get("camera", "") not in pc_cameras():
            t["camera"] = normalize_camera(str(t.get("camera") or ""))
            self.note(f'{tid}: camera set to "{t["camera"]}" (the camera stays fixed unless it is a slow push-in or pan)')
        for key in ("camera", "atmosphere"):
            if key not in t:
                t[key] = ""
                self.note(f"{tid}: {key} was missing: left empty")
        for key in ("start_picture", "end_picture", "motion", "narration", "shows"):
            if key in t and not isinstance(t[key], str):
                t[key] = str(t[key] or "")
        cast = []
        for c in t.get("cast") if isinstance(t.get("cast"), list) else []:
            new = tables["cast"].get(str(c).strip().lower()) or tables["cast"].get(slug(c))
            if new and new not in cast:
                cast.append(new)
            elif not new:
                self.note(f'{tid}: removed unknown character {c!r} from the cast')
        if not cast:
            text = " ".join(str(t.get(k, "")) for k in ("start_picture", "end_picture", "motion") if t.get(k))
            cast = [c["id"] for c in p["cast"] if re.search(r"\b" + re.escape(c["name"]) + r"\b", text, re.I)]
            if cast:
                self.note(f"{tid}: cast read from the pictures: {', '.join(cast)}")
        seen = " ".join(str(t.get(k, "")) for k in ("start_picture", "end_picture") if t.get(k))
        extra = [c["id"] for c in p["cast"] if c["id"] not in cast and re.search(r"\b" + re.escape(c["name"]) + r"\b", seen, re.I)]
        if extra:  # the pictures name them, so the cast must too (the cast is everyone in the first picture)
            cast = [c["id"] for c in p["cast"] if c["id"] in cast or c["id"] in extra]
            self.note(f"{tid}: added {', '.join(extra)} to the cast because the pictures name them")
        if t.get("cast") != cast:
            t["cast"] = cast
        self.text(i, t, names)
        self.narration(t)
        if t.get("beats") is not None and (number(pr["clip_seconds"]) or 5) < 8:
            del t["beats"]
            self.note(f"{tid}: removed beats (they are only for clips of 8 seconds or more)")

    def text(self, i: int, t: dict[str, Any], names: list[str]) -> None:
        tid, way = t["id"], ("to the right" if i % 2 == 0 else "to the left")
        for field in ("start_picture", "end_picture", "motion"):
            text = str(t.get(field) or "")
            if not text:
                continue
            new = re.sub(r"\b(his|her|its|their|the|a|my|your)\s+head\b", r"\1 face", text, flags=re.I)
            if new != text:
                self.note(f'{tid}: {field}: wrote "face" instead of "head" (the movement detector reads "head" as travelling)')
            for label, rule, minimum, message in (
                ("text", pc.BANNED, 6 if field == "motion" else 8, "removed a part that asked for readable text (pictures cannot hold text)"),
                ("negation", pc.NEG, 6 if field == "motion" else 8, "removed a part that said what must not appear (the video model draws every word)"),
                ("speech", pc.SPEECH, 6 if field == "motion" else 8, "removed a part where someone speaks on screen (the narration is the voice-over)"),
            ):
                cut, did = drop_clauses(new, rule, minimum)
                if did:
                    new = cut
                    self.note(f"{tid}: {field}: {message}")
            if field != "motion":
                split, did = split_two_names(new, names)
                if did:
                    new = split
                    self.note(f"{tid}: {field}: put each character in its own clause, separated by ';'")
            added, did = insert_direction(new, way)
            if did:
                new = added
                self.note(f'{tid}: {field}: added a direction ("{way}") after a verb of travel: draw the start and end pictures on different sides')
            new = re.sub(r"\s{2,}", " ", new).strip()
            if new != text:
                t[field] = new

    def narration(self, t: dict[str, Any]) -> None:
        tid, sec = t["id"], number(t.get("seconds")) or 5.0
        if self.p["production"]["narration"] != "narrator":
            return
        budget = int(max(1.0, sec - 0.8) * 2.8)
        text = str(t.get("narration") or "").strip()
        if words(text) > budget:
            keep, used = [], 0
            for s in SENTENCE_END.split(text):
                if used + words(s) <= budget:
                    keep.append(s)
                    used += words(s)
                else:
                    break
            cut = " ".join(keep)
            if not keep or used < math.ceil(budget * 0.6):
                cut = " ".join(text.split()[:budget]).rstrip(",;:")
                cut += "" if cut[-1:] in ".!?" else "."
            t["narration"] = cut
            self.note(f"{tid}: narration cut from {words(text)} to {words(cut)} words to fit {tidy_number(sec)} s")
        shows = str(t.get("shows") or "").strip()
        if words(shows) > 25:
            t["shows"] = " ".join(shows.split()[:25])
            self.note(f'{tid}: "shows" cut to 25 words')
        narration = str(t.get("narration") or "")
        shows = str(t.get("shows") or "").strip()
        if narration.strip() and (words(shows) < 4 or not pc.stems(shows) & pc.stems(narration)):
            pick = self.shows_from_pictures(t, narration)
            if pick:
                t["shows"] = pick
                self.note(f'{tid}: "shows" taken from the part of the pictures the narration talks about: "{pick}"')

    def shows_from_pictures(self, t: dict[str, Any], narration: str) -> str:
        """Nothing is invented: the best part (4-25 words) of the take's own pictures by words shared with the narration, scenery before characters."""
        names = [c["name"] for c in self.p["cast"]]
        talk, best = pc.stems(narration), (0, 0, "")
        for field in ("end_picture", "start_picture"):
            for clause in pc.CLAUSE.split(str(t.get(field) or "")):
                c = clause.strip(" .,;")
                if 4 <= words(c) <= 25:
                    shared = len(pc.stems(c) & talk)
                    scenery = 0 if any(re.search(r"\b" + re.escape(n) + r"\b", c, re.I) for n in names) else 1
                    if (shared, scenery) > best[:2]:
                        best = (shared, scenery, c)
        return best[2] if best[0] > 0 else ""

    # ---- who starts from whom
    def joins(self) -> None:
        takes = self.p["takes"]
        for i, t in enumerate(takes):
            prev = takes[i - 1] if i else None
            first = prev is None or prev.get("scene") != t.get("scene")
            sf = str(t.get("start_from") or "").strip().lower()
            sf = sf if sf in ("new_picture", "previous_end") else None
            has_start = words(t.get("start_picture")) >= 8
            same_cast = prev is not None and sorted(prev.get("cast", [])) == sorted(t.get("cast", []))
            if first:
                want = "new_picture"
            elif sf == "previous_end":
                want = "previous_end" if same_cast else ("new_picture" if has_start else "previous_end")
            else:
                want = "previous_end" if (not has_start and same_cast and prev.get("end_picture")) else "new_picture"
            if t.get("start_from") != want:
                t["start_from"] = want
                self.note(f'{t["id"]}: start_from set to "{want}"')
            if want == "previous_end" and t.get("start_picture"):
                del t["start_picture"]
                self.note(f'{t["id"]}: removed start_picture (this take starts from the previous end picture)')
        pr = self.p["production"]
        if pr["join"] == "seamless_chain" and (len(self.p["scenes"]) > 1 or any(t.get("start_from") != "previous_end" for t in takes[1:]) or len({t.get("framing") for t in takes}) > 1
                                                or self.p.get("format") != "16:9" or (number(pr["clip_seconds"]) or 5) > 5):
            pr["join"] = "matched_pictures"
            self.note('"join" seamless_chain needs one scene, one shot size and 16:9 clips of about 4.5 s: set to "matched_pictures"')

    def renumber(self) -> None:
        ids = [t.get("id") for t in self.p["takes"]]
        if any(not isinstance(x, str) or not re.fullmatch(r"[a-z0-9_]{1,24}", x or "") for x in ids) or len(set(ids)) != len(ids):
            for n, t in enumerate(self.p["takes"], 1):
                t["id"] = f"t{n:02d}"
            self.note("take ids were missing, repeated or not lowercase slugs: renumbered t01, t02, ...")

    def run_once(self) -> None:
        self.top()
        tables = self.structure()
        self.renumber()
        self.production()
        for i, t in enumerate(self.p["takes"]):
            self.take(i, t, self.p["takes"][i - 1] if i else None, tables)
        self.joins()
        total = sum(number(t.get("seconds")) or 0 for t in self.p["takes"])
        cur = number(self.p["production"].get("total_seconds"))
        if self.p["takes"] and (cur is None or abs(cur - total) > max(number(self.p["production"]["clip_seconds"]) or 1, 1)):
            self.p["production"]["total_seconds"] = tidy_number(total)
            self.note(f'"total_seconds" was {self.p["production"].get("total_seconds") if cur is None else tidy_number(cur)}: set to {tidy_number(total)} (what the takes add up to)')


def pc_cameras() -> tuple[str, ...]:
    return ("", "slow push-in", "slow pan left", "slow pan right")


def autofix(plan: Any) -> tuple[Any, list[str]]:
    """(the repaired copy, what was changed). The plan passed in is never modified. A plan that is not an object is returned unchanged."""
    if not isinstance(plan, dict):
        return plan, []
    fixer = Fixer(copy.deepcopy(plan))
    for _ in range(3):  # a repair can enable the next one (ids first, then who is in a take)
        before = len(fixer.changes)
        fixer.run_once()
        if len(fixer.changes) == before:
            break
    return fixer.p, fixer.changes
