"""Art engine: story panels -> ComfyUI images (cached, resumable), character sheets and a vision-based consistency check.

Consistency baseline (no extra models): every panel prompt repeats each character's exact `look` tags, and a vision model
checks the result against those tags; a panel scoring below THRESHOLD is regenerated with a new seed and the missing tags
emphasised, keeping the best attempt. The measured score is stored per panel so the approach can be judged (and replaced,
e.g. by IP-Adapter) with data.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.service import _history_images, _patch_workflow
from engine.original.genres import GENRES
from engine.original.models import Character, OriginalStory, Panel

W, H = 1344, 768  # SDXL-friendly 16:9, the video frame shape
THRESHOLD = 0.6
SHOT_TAGS = {"wide": "wide shot, scenery, from a distance", "medium": "cowboy shot", "close": "close-up, portrait",
             "extreme_close": "extreme close-up, detail focus", "over_shoulder": "from behind, over the shoulder"}
ANGLE_TAGS = {"eye_level": "", "low": "from below", "high": "from above", "dutch": "dutch angle"}
POSE_KEYS = {"eyes closed", "sleeping", "yawning", "smiling", "tears"}  # deterministic requirements from the narration
QUALITY = "safe, masterpiece, high score, great score, absurdres"
NEGATIVE = ("lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, worst quality, "
            "low quality, low score, bad score, average score, signature, watermark, username, blurry, nsfw, nude, "
            "suggestive, revealing clothes, speech bubble")


def build_prompt(story: OriginalStory, panel: Panel, emphasis: list[str] | None = None) -> tuple[str, str]:
    genre = GENRES[story.bible.premise.genre]
    chars = {c.id: c for c in story.bible.characters}
    shown = [chars[c] for c in panel.character_ids if c in chars][:2]
    loc = next((x for x in story.bible.locations if x.id == panel.location_id), None)
    looks = []
    for c in shown:
        tags = c.look
        for t in emphasis or []:
            tags = tags.replace(t, f"({t}:1.3)")
        looks.append(tags)
    count = {0: "no humans", 1: "solo", 2: "2others"}.get(len(shown), "multiple others")
    keys = [f"({k}:1.4)" if (k in (emphasis or []) or k in POSE_KEYS) else k for k in panel.key_visuals]
    parts = [count, *looks, *keys, panel.action.rstrip("."), SHOT_TAGS.get(panel.shot, ""), ANGLE_TAGS.get(panel.angle, ""),
             loc.look if loc else "", genre.art_style, QUALITY]
    neg = NEGATIVE + (", open eyes, looking at viewer" if "eyes closed" in panel.key_visuals else "")
    return ", ".join(p for p in parts if p), neg


SHEET_NEGATIVE = NEGATIVE + ", multiple views, split screen, collage, reference sheet, multiple characters, 2girls, 2boys"


def sheet_prompt(c: Character, story: OriginalStory) -> str:
    """One clean portrait per character: it is also the IP-Adapter reference, so it must show exactly one subject."""
    style = GENRES[story.bible.premise.genre].art_style
    return f"solo, {c.look}, upper body, portrait, looking at viewer, simple plain background, {style}, {QUALITY}"


def seed_for(story: OriginalStory, key: str, attempt: int = 0) -> int:
    h = hashlib.sha256(f"{story.bible.premise.title}|{key}".encode()).digest()
    return int.from_bytes(h[:6], "big") + attempt * 7919


class ComfyRunner:
    """Runs the approved anime_sdxl workflow (anime_sdxl_ipa when a character reference is given); returns PNG bytes."""

    def __init__(self, client: ComfyUIClient | None = None, workflow_id: str = "anime_sdxl", ipa_id: str = "anime_sdxl_ipa",
                 ipa2_id: str = "anime_sdxl_ipa2"):
        self.client = client or ComfyUIClient()
        reg = ComfyWorkflowRegistry(self.client)
        pre = reg.preflight(workflow_id)
        if not pre["ready"]:
            raise RuntimeError(f"ComfyUI workflow not ready: missing nodes {pre['missing_nodes']}, models {pre['missing_models']}")
        self.workflow, _ = reg.load(workflow_id)
        self.meta = reg.metadata(workflow_id)
        self.ipa = None  # optional: without its nodes/models panels fall back to prompt-only consistency
        try:
            if reg.preflight(ipa_id)["ready"]:
                self.ipa = (reg.load(ipa_id)[0], reg.metadata(ipa_id))
        except Exception:
            self.ipa = None
        self.ipa2 = None  # two-character panels: left/right masked references; falls back to the single-reference workflow
        try:
            if reg.preflight(ipa2_id)["ready"]:
                self.ipa2 = (reg.load(ipa2_id)[0], reg.metadata(ipa2_id))
        except Exception:
            self.ipa2 = None

    def _upload(self, path: Path) -> str:
        """Copy a reference image into ComfyUI's input folder (name derived from content, so reruns reuse it)."""
        import urllib.request

        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        name, boundary = f"pf_{digest[:16]}.png", "pfboundary" + digest[:8]
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n").encode()
        tail = (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n").encode()
        req = urllib.request.Request(self.client.base_url + "upload/image", data=head + data + tail,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["name"]

    def generate(self, pos: str, neg: str, seed: int, width: int, height: int, prefix: str, timeout: float = 300.0,
                 is_cancelled: Callable[[], bool] = lambda: False, reference: Path | None = None,
                 reference_b: Path | None = None, reference_weight: float | None = None) -> bytes:
        if reference is not None and reference_b is not None and self.ipa2 is not None and (width, height) == (W, H):
            wf = _patch_workflow(self.ipa2[0], self.ipa2[1]["patch_slots"], pos, neg, width, height, seed, prefix,
                                 reference_image=self._upload(reference), reference_image_b=self._upload(reference_b))
        elif reference is not None and self.ipa is not None:
            wf = _patch_workflow(self.ipa[0], self.ipa[1]["patch_slots"], pos, neg, width, height, seed, prefix,
                                 reference_image=self._upload(reference), reference_weight=reference_weight)
        else:
            wf = _patch_workflow(self.workflow, self.meta["patch_slots"], pos, neg, width, height, seed, prefix)
        pid = self.client.submit_prompt(wf)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if is_cancelled():
                raise RuntimeError("cancelled")
            imgs = _history_images(self.client.history(pid), pid)
            if imgs:
                i = imgs[0]
                return self.client.download_output(i["filename"], i["subfolder"], i["type"])
            time.sleep(1.5)
        raise TimeoutError(f"ComfyUI produced no image within {timeout:.0f}s")


class _TagCheck(BaseModel):
    tag: str
    visible: bool


class _Check(BaseModel):
    results: list[_TagCheck]


VISIBLE_TAGS = {"close": 2, "extreme_close": 2}  # tags are ordered hair, eyes, build, outfit, item: only the first ones identify
CORE_TAGS = 3  # the local vision model is too noisy on the rest (it denied a clearly visible "fox cub"), so only the core identity is checked
MAX_ATTEMPTS = 2


async def check_panel(provider, image: Path, chars: list[Character], shot: str = "medium") -> tuple[float, list[str]]:
    """Score 0..1: per expected character, the share of its look tags the vision model confirms as visible.

    One call per character with an explicit tag list: asking for per-character matches by *name* made the model answer with
    tag names instead of character names, so everything scored 0 on the first real run.
    """
    if not chars:
        return 1.0, []
    scores, missing = [], []
    for c in chars:
        tags = [t.strip() for t in c.look.split(",") if t.strip()][:VISIBLE_TAGS.get(shot, CORE_TAGS)]
        prompt = ("Look at this illustration. For each visual tag below, say whether it is clearly visible on the character "
                  f"described as '{c.name}' ({tags[0]}). Return every tag exactly as written, with visible true or false. "
                  "If the character is not in the picture, every tag is false.\nTags:\n" + "\n".join(f"- {t}" for t in tags))
        raw = await provider.analyze_vision(image, prompt, format_schema=_Check.model_json_schema(), max_tokens=600, temperature=0.0)
        try:
            res = _Check.model_validate_json(raw)
        except Exception:
            scores.append(0.0)  # an unparseable answer must not be mistaken for a pass
            continue
        seen = {r.tag.strip().lower(): r.visible for r in res.results}
        bad = [t for t in tags if not seen.get(t.lower(), False)]
        scores.append(1 - len(bad) / len(tags))
        missing += bad
    return sum(scores) / len(scores), sorted(set(missing))


POSE_WORDS = ("closed", "asleep", "sleeping", "from behind", "back to", "turned away", "facing away", "looking up", "looking down")
MATCH_THRESHOLD = 0.6
POSE_WEIGHT = 0.3  # the portrait looks at the viewer with open eyes; a lower pin lets "eyes closed" or "from behind" through


def pose_sensitive(panel: Panel) -> bool:
    text = " ".join(panel.key_visuals + [panel.action]).lower()
    return any(w in text for w in POSE_WORDS)


async def check_match(provider, image: Path, keys: list[str]) -> tuple[float, list[str]]:
    """Share of the narration's key visuals the vision model can see (0..1) and the ones it cannot."""
    if not keys:
        return 1.0, []
    prompt = ("Look at this illustration. For each item below say whether it is clearly visible in the picture. Return every "
              "item exactly as written with visible true or false.\nItems:\n" + "\n".join(f"- {k}" for k in keys))
    raw = await provider.analyze_vision(image, prompt, format_schema=_Check.model_json_schema(), max_tokens=500, temperature=0.0)
    try:
        res = _Check.model_validate_json(raw)
    except Exception:
        return 0.0, list(keys)
    seen = {r.tag.strip().lower(): r.visible for r in res.results}
    bad = [k for k in keys if not seen.get(k.lower(), False)]
    return 1 - len(bad) / len(keys), bad


class ArtRecord(BaseModel):
    panel_id: str
    image: str
    prompt_hash: str
    seed: int
    attempts: int
    score: float | None = None
    match_score: float | None = None  # does the picture show what the narration says (vision check of key_visuals)
    missing: list[str] = Field(default_factory=list)


def _hash(pos: str, neg: str, ref: str = "") -> str:
    return hashlib.sha256(f"{pos}\n{neg}\n{W}x{H}\n{ref}".encode()).hexdigest()[:16]


def generate_art(story: OriginalStory, ws: Path, runner: ComfyRunner, provider=None, limit: int | None = None,
                 progress: Callable[[float, str], None] = lambda p, m: None,
                 is_cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Character sheets first, then panels in story order. Existing images with an unchanged prompt are reused."""
    (ws / "sheets").mkdir(parents=True, exist_ok=True)
    (ws / "panels").mkdir(exist_ok=True)
    db_path = ws / "art.json"
    db = {r["panel_id"]: ArtRecord(**r) for r in json.loads(db_path.read_text())} if db_path.exists() else {}

    def save():
        db_path.write_text(json.dumps([r.model_dump() for r in db.values()], indent=1), encoding="utf-8")

    for c in story.bible.characters:
        f = ws / "sheets" / f"{c.id}.png"
        if not f.exists():
            f.write_bytes(runner.generate(sheet_prompt(c, story), SHEET_NEGATIVE, seed_for(story, "sheet_" + c.id), W, H, f"sheet_{c.id}"))
    chars = {c.id: c for c in story.bible.characters}
    panels = story.panels[:limit] if limit else story.panels
    done = reused = 0
    for n, p in enumerate(panels, 1):
        if is_cancelled():
            raise RuntimeError("cancelled")
        progress(n / len(panels), f"Panel {n}/{len(panels)}")
        pos, neg = build_prompt(story, p)
        shown = [chars[c] for c in p.character_ids if c in chars][:2]
        # the first character on screen has its face pinned to its sheet
        ref = ws / "sheets" / f"{shown[0].id}.png" if shown and getattr(runner, "ipa", None) is not None else None
        # two characters: the first is pinned to the left half, the second to the right half (needs the masked workflow)
        ref_b = ws / "sheets" / f"{shown[1].id}.png" if len(shown) == 2 and getattr(runner, "ipa2", None) is not None else None
        rec, img = db.get(p.id), ws / "panels" / f"{p.id}.png"
        if rec and rec.prompt_hash == _hash(pos, neg, (ref.name if ref else "") + (ref_b.name if ref_b else "")) and img.exists():
            reused += 1
            continue
        best: tuple | None = None
        emphasis: list[str] = []
        for attempt in range(MAX_ATTEMPTS):
            seed = seed_for(story, p.id, attempt)
            pos_i, _ = build_prompt(story, p, emphasis)
            png = runner.generate(pos_i, neg, seed, W, H, f"panel_{p.id}", reference=ref, reference_b=ref_b,
                                  reference_weight=POSE_WEIGHT if pose_sensitive(p) else None)
            score, missing, match, unmatched = 1.0, [], 1.0, []
            if provider is not None and (shown or p.key_visuals):
                tmp = ws / "panels" / f"_try_{p.id}.png"
                tmp.write_bytes(png)
                if shown:
                    score, missing = asyncio.run(check_panel(provider, tmp, shown, p.shot))
                match, unmatched = asyncio.run(check_match(provider, tmp, p.key_visuals))
                tmp.unlink(missing_ok=True)
            total = 0.7 * match + 0.3 * score  # what the narration says leads; the face is pinned by the reference already
            if best is None or total > best[0]:
                best = (total, png, seed, missing, score, match, unmatched)
            if provider is None or match >= MATCH_THRESHOLD:
                break  # the identity score is recorded but does not trigger redraws: its tags are too noisy to act on
            emphasis = missing + unmatched
        total, png, seed, missing, score, match, unmatched = best
        img.write_bytes(png)
        db[p.id] = ArtRecord(panel_id=p.id, image=str(img), prompt_hash=_hash(pos, neg, (ref.name if ref else "") + (ref_b.name if ref_b else "")), seed=seed, attempts=attempt + 1,
                             score=score if provider is not None and shown else None,
                             match_score=match if provider is not None and p.key_visuals else None, missing=missing + unmatched)
        save()
        done += 1
    scores = [r.score for r in db.values() if r.score is not None]
    return {"generated": done, "reused": reused, "panels": len(panels),
            "mean_score": round(sum(scores) / len(scores), 3) if scores else None,
            "mean_match": round(sum(m) / len(m), 3) if (m := [r.match_score for r in db.values() if r.match_score is not None]) else None,
            "below_threshold": [r.panel_id for r in db.values() if r.match_score is not None and r.match_score < MATCH_THRESHOLD]}
