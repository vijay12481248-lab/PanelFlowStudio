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
import os
import time
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.service import _history_images, _patch_workflow
from engine.original.genres import GENRES
from engine.original.models import Character, OriginalStory, Panel
from engine.original import review as review_mod
from engine.original import shotspec

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


def build_prompt(story: OriginalStory, panel: Panel, emphasis: list[str] | None = None, style: str = "tags",
                 must: list[str] | None = None, attempt: int = 0) -> tuple[str, str]:
    if panel.director:  # a directed shot: the composer writes the detailed prompt from the structured spec
        spec = shotspec.ShotSpec(**panel.director)
        if style == "natural":
            spec = spec.model_copy(update={"key_visuals": list(dict.fromkeys(spec.key_visuals + (must or [])))[:8]})  # the narration's own facts
            if attempt >= 2:  # last attempt: widen the frame so the objects the narration names fit in with the character
                spec = spec.model_copy(update={"shot": {"close": "medium", "extreme_close": "medium", "medium": "wide"}.get(spec.shot, spec.shot)})
            return shotspec.compose_natural(story, spec, panel.location_id, emphasis, simplify=attempt >= 2)
        return shotspec.compose(story, spec, panel.location_id, emphasis)
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


def sheet_prompt(c: Character, story: OriginalStory, style_kind: str = "tags") -> str:
    """One clean portrait per character: it is also the IP-Adapter reference, so it must show exactly one subject."""
    style = GENRES[story.bible.premise.genre].art_style
    if style_kind == "natural":
        return (f"Character reference portrait, upper body, facing the viewer, plain background, {style}. "
                f"{shotspec.describe_character(c)}. {shotspec.NATURAL_SUFFIX}")
    return f"solo, {shotspec.person_tags(c)}, {c.look}, upper body, portrait, looking at viewer, simple plain background, {style}, {QUALITY}"


def seed_for(story: OriginalStory, key: str, attempt: int = 0) -> int:
    h = hashlib.sha256(f"{story.bible.premise.title}|{key}".encode()).digest()
    return int.from_bytes(h[:6], "big") + attempt * 7919


class ComfyRunner:
    """Runs the approved anime_sdxl workflow (anime_sdxl_ipa when a character reference is given); returns PNG bytes."""

    def __init__(self, client: ComfyUIClient | None = None, workflow_id: str = "anime_sdxl", ipa_id: str = "anime_sdxl_ipa",
                 ipa2_id: str = "anime_sdxl_ipa2", engine: str | None = None, flux_id: str = "flux_schnell"):
        self.client = client or ComfyUIClient()
        reg = ComfyWorkflowRegistry(self.client)
        engine = engine or os.environ.get("PANELFLOW_IMAGE_ENGINE", "auto")  # auto | flux | sdxl
        self.flux = None  # a prompt-following model: it reads sentences, so objects and actions in the narration survive
        if engine in ("auto", "flux"):
            try:
                if reg.preflight(flux_id)["ready"]:
                    self.flux = (reg.load(flux_id)[0], reg.metadata(flux_id))
            except Exception:
                self.flux = None
            if engine == "flux" and self.flux is None:
                raise RuntimeError("FLUX was requested but its workflow is not ready (model file missing or ComfyUI down)")
        self.engine = "flux" if self.flux is not None else "sdxl"
        self.style = "natural" if self.flux is not None else "tags"
        pre = reg.preflight(workflow_id) if self.flux is None or engine == "auto" else {"ready": True}
        if not pre["ready"] and self.flux is None:
            raise RuntimeError(f"ComfyUI workflow not ready: missing nodes {pre['missing_nodes']}, models {pre['missing_models']}")
        self.workflow, self.meta = (reg.load(workflow_id)[0], reg.metadata(workflow_id)) if pre["ready"] else (None, None)
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
        if self.flux is not None:
            wf = _patch_workflow(self.flux[0], self.flux[1]["patch_slots"], pos, neg, width, height, seed, prefix)
        elif reference is not None and reference_b is not None and self.ipa2 is not None and (width, height) == (W, H):
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
MATCH_THRESHOLD = 0.7
DIRECTED_ATTEMPTS = 3
POSE_WEIGHT = 0.3  # the portrait looks at the viewer with open eyes; a lower pin lets "eyes closed" or "from behind" through


def pose_sensitive(panel: Panel) -> bool:
    if panel.director:
        return shotspec.pose_sensitive(shotspec.ShotSpec(**panel.director))
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


class _Judgement(BaseModel):
    score: float = Field(description="share of the required items the description shows, 0 to 1")
    missing: list[str] = Field(default_factory=list, description="required items not shown or contradicted, as short phrases")


async def describe_image(provider, image: Path) -> str:
    """What a viewer would say the picture shows: free text is something the vision model does well, unlike yes/no lists."""
    return (await provider.analyze_vision(
        image, "Describe this illustration in detail for someone who cannot see it: each character (kind of creature, hair or fur, "
        "clothes), their body pose, their facial expression and whether their eyes are open or closed, what they are doing, objects "
        "they hold, the place, the lighting and mood. Be literal, do not guess what is not visible, and use at most 90 words.", max_tokens=1000, temperature=0.0)).strip()


async def judge_shot(provider, required: str, description: str) -> tuple[float, list[str]]:
    """Text-only comparison of what the shot REQUIRES with what the picture was described as showing."""
    prompt = (f"REQUIRED in the picture:\n{required}\n\nWHAT THE PICTURE ACTUALLY SHOWS (a literal description):\n{description}\n\n"
              "Which required items are NOT shown or are contradicted by the description? Different wording for the same thing counts as shown "
              "(a fox cub is the orange fox). List only real misses, as short phrases. score = share of required items that are shown.")
    out = await provider.generate_structured(prompt, _Judgement, system_prompt="You are a strict, literal reviewer.", temperature=0.0,
                                             max_tokens=400, num_ctx=8192)
    return max(0.0, min(1.0, out.score)), [m.strip() for m in out.missing if m.strip()]


class ArtRecord(BaseModel):
    panel_id: str
    image: str
    prompt_hash: str
    seed: int
    attempts: int
    score: float | None = None
    match_score: float | None = None  # does the picture show what the narration says (described, then judged against the shot spec)
    description: str = ""  # what the accepted picture was described as showing
    status: str = ""  # accept | accept_low | needs_review | unverified (only set for directed shots)
    review: dict = Field(default_factory=dict)  # the full Review: every requirement, both witnesses, confidence, decision
    claims: list[dict] = Field(default_factory=list)  # what the narration asserts that must be visible
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
            f.write_bytes(runner.generate(sheet_prompt(c, story, getattr(runner, "style", "tags")), "" if getattr(runner, "style", "tags") == "natural" else SHEET_NEGATIVE, seed_for(story, "sheet_" + c.id), W, H, f"sheet_{c.id}"))
    chars = {c.id: c for c in story.bible.characters}
    panels = story.panels[:limit] if limit else story.panels
    done = reused = 0
    for n, p in enumerate(panels, 1):
        if is_cancelled():
            raise RuntimeError("cancelled")
        progress(n / len(panels), f"Panel {n}/{len(panels)}")
        style, engine = getattr(runner, "style", "tags"), getattr(runner, "engine", "sdxl")
        pos, neg = build_prompt(story, p, style=style)
        shown = [chars[c] for c in p.character_ids if c in chars][:2]
        # the first character on screen has its face pinned to its sheet
        ref = ws / "sheets" / f"{shown[0].id}.png" if shown and getattr(runner, "ipa", None) is not None else None
        # two characters: the first is pinned to the left half, the second to the right half (needs the masked workflow)
        ref_b = ws / "sheets" / f"{shown[1].id}.png" if len(shown) == 2 and getattr(runner, "ipa2", None) is not None else None
        rec, img = db.get(p.id), ws / "panels" / f"{p.id}.png"
        if rec and rec.prompt_hash == _hash(pos, neg, engine + (ref.name if ref else "") + (ref_b.name if ref_b else "")) and img.exists():
            reused += 1
            continue
        best: tuple | None = None
        emphasis: list[str] = []
        claims: list[review_mod.Claim] = []
        spec = shotspec.ShotSpec(**p.director) if p.director else None
        if provider is not None and spec is not None and p.caption:
            try:  # the narration's own visible facts, extracted independently of the shot director
                claims = asyncio.run(review_mod.extract_claims(provider, p.caption))
            except Exception:
                claims = []
        must = [c.text for c in claims if c.critical]
        for attempt in range(DIRECTED_ATTEMPTS if p.director else MAX_ATTEMPTS):
            seed = seed_for(story, p.id, attempt)
            pos_i, _ = build_prompt(story, p, emphasis, style, must, attempt)
            png = runner.generate(pos_i, neg, seed, W, H, f"panel_{p.id}", reference=ref, reference_b=ref_b,
                                  reference_weight=POSE_WEIGHT if (pose_sensitive(p) or attempt > 0) else None)  # retries loosen the pin
            score, missing, match, unmatched, desc, rev = 1.0, [], 1.0, [], "", None
            if provider is not None and (shown or p.key_visuals):
                tmp = ws / "panels" / f"_try_{p.id}.png"
                tmp.write_bytes(png)
                if spec is not None:
                    try:
                        rev = asyncio.run(review_mod.review_image(provider, tmp, claims, spec, chars))
                        match, desc = rev.score, rev.description
                    except Exception as e:  # a model hiccup must not stop a whole episode: keep the picture, mark it unverified
                        desc = f"(not verified: {str(e)[:80]})"
                else:
                    if shown:
                        score, missing = asyncio.run(check_panel(provider, tmp, shown, p.shot))
                    match, unmatched = asyncio.run(check_match(provider, tmp, p.key_visuals))
                tmp.unlink(missing_ok=True)
            rank = review_mod.RANK[rev.decision] if rev is not None else (1.5 if spec is not None else (2 if match >= MATCH_THRESHOLD else 0))
            key = (rank, match)
            if best is None or key > best[0]:
                best = (key, png, seed, missing, score, match, unmatched, desc, rev)
            if provider is None or rank >= 2 or (rev is None and spec is not None):
                break  # accepted, or unverifiable (a model error): do not burn attempts on a judge that is not answering
            emphasis = (rev.missing_critical + [i.item for i in rev.items if not i.critical and i.verdict != "shown"][:2]) if rev else missing + unmatched
        key, png, seed, missing, score, match, unmatched, desc, rev = best
        img.write_bytes(png)
        status = ("" if spec is None else "unverified" if rev is None else {"accept": "accept", "accept_low": "accept_low"}.get(rev.decision, "needs_review"))
        db[p.id] = ArtRecord(panel_id=p.id, image=str(img), prompt_hash=_hash(pos, neg, engine + (ref.name if ref else "") + (ref_b.name if ref_b else "")),
                             seed=seed, attempts=attempt + 1, score=score if provider is not None and shown and spec is None else None,
                             match_score=match if provider is not None and (p.key_visuals or spec is not None) and (rev is not None or spec is None) else None,
                             missing=(rev.missing_critical if rev else missing + unmatched), description=desc, status=status,
                             review=rev.model_dump() if rev else {}, claims=[c.model_dump() for c in claims])
        save()
        done += 1
    scores = [r.score for r in db.values() if r.score is not None]
    recs = list(db.values())
    review_mod.write_report(panels, ws, [r.model_dump() for r in recs])
    return {"generated": done, "reused": reused, "panels": len(panels),
            "mean_score": round(sum(scores) / len(scores), 3) if scores else None,
            "mean_match": round(sum(m) / len(m), 3) if (m := [r.match_score for r in recs if r.match_score is not None]) else None,
            "accepted": [r.panel_id for r in recs if r.status == "accept"],
            "accepted_low_confidence": [r.panel_id for r in recs if r.status == "accept_low"],
            "needs_review": [r.panel_id for r in recs if r.status == "needs_review"],
            "below_threshold": [r.panel_id for r in recs if r.status == "needs_review"
                                or (not r.status and r.match_score is not None and r.match_score < MATCH_THRESHOLD)]}
