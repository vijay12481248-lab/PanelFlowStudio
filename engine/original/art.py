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
    count = {0: "no humans", 1: "solo"}.get(len(shown), "multiple others")
    parts = [count, *looks, panel.action.rstrip("."), SHOT_TAGS.get(panel.shot, ""), ANGLE_TAGS.get(panel.angle, ""),
             loc.look if loc else "", genre.art_style, QUALITY]
    return ", ".join(p for p in parts if p), NEGATIVE


def sheet_prompt(c: Character, story: OriginalStory) -> str:
    style = GENRES[story.bible.premise.genre].art_style
    return f"solo, {c.look}, full body, standing, neutral pose, looking at viewer, simple white background, character sheet, {style}, {QUALITY}"


def seed_for(story: OriginalStory, key: str, attempt: int = 0) -> int:
    h = hashlib.sha256(f"{story.bible.premise.title}|{key}".encode()).digest()
    return int.from_bytes(h[:6], "big") + attempt * 7919


class ComfyRunner:
    """Runs the approved anime_sdxl workflow and returns PNG bytes."""

    def __init__(self, client: ComfyUIClient | None = None, workflow_id: str = "anime_sdxl"):
        self.client = client or ComfyUIClient()
        reg = ComfyWorkflowRegistry(self.client)
        pre = reg.preflight(workflow_id)
        if not pre["ready"]:
            raise RuntimeError(f"ComfyUI workflow not ready: missing nodes {pre['missing_nodes']}, models {pre['missing_models']}")
        self.workflow, _ = reg.load(workflow_id)
        self.meta = reg.metadata(workflow_id)

    def generate(self, pos: str, neg: str, seed: int, width: int, height: int, prefix: str, timeout: float = 300.0,
                 is_cancelled: Callable[[], bool] = lambda: False) -> bytes:
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


class ArtRecord(BaseModel):
    panel_id: str
    image: str
    prompt_hash: str
    seed: int
    attempts: int
    score: float | None = None
    missing: list[str] = Field(default_factory=list)


def _hash(pos: str, neg: str) -> str:
    return hashlib.sha256(f"{pos}\n{neg}\n{W}x{H}".encode()).hexdigest()[:16]


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
            f.write_bytes(runner.generate(sheet_prompt(c, story), NEGATIVE, seed_for(story, "sheet_" + c.id), W, H, f"sheet_{c.id}"))
    chars = {c.id: c for c in story.bible.characters}
    panels = story.panels[:limit] if limit else story.panels
    done = reused = 0
    for n, p in enumerate(panels, 1):
        if is_cancelled():
            raise RuntimeError("cancelled")
        progress(n / len(panels), f"Panel {n}/{len(panels)}")
        pos, neg = build_prompt(story, p)
        rec, img = db.get(p.id), ws / "panels" / f"{p.id}.png"
        if rec and rec.prompt_hash == _hash(pos, neg) and img.exists():
            reused += 1
            continue
        shown = [chars[c] for c in p.character_ids if c in chars][:2]
        best: tuple[float, bytes, int, list[str]] | None = None
        emphasis: list[str] = []
        for attempt in range(MAX_ATTEMPTS):
            seed = seed_for(story, p.id, attempt)
            pos_i, _ = build_prompt(story, p, emphasis)
            png = runner.generate(pos_i, neg, seed, W, H, f"panel_{p.id}")
            score, missing = 1.0, []
            if provider is not None and shown:
                tmp = ws / "panels" / f"_try_{p.id}.png"
                tmp.write_bytes(png)
                score, missing = asyncio.run(check_panel(provider, tmp, shown, p.shot))
                tmp.unlink(missing_ok=True)
            if best is None or score > best[0]:
                best = (score, png, seed, missing)
            if provider is None or score >= THRESHOLD:
                break
            emphasis = missing
        score, png, seed, missing = best
        img.write_bytes(png)
        db[p.id] = ArtRecord(panel_id=p.id, image=str(img), prompt_hash=_hash(pos, neg), seed=seed, attempts=attempt + 1,
                             score=score if provider is not None and shown else None, missing=missing)
        save()
        done += 1
    scores = [r.score for r in db.values() if r.score is not None]
    return {"generated": done, "reused": reused, "panels": len(panels),
            "mean_score": round(sum(scores) / len(scores), 3) if scores else None,
            "below_threshold": [r.panel_id for r in db.values() if r.score is not None and r.score < THRESHOLD]}
