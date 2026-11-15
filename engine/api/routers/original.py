"""Original Story Studio endpoints (docs/ORIGINAL_STORY_STUDIO.md)."""
import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.llm.registry import llm_registry
from engine.original import art as art_mod
from engine.original import refine as refine_mod
from engine.original import review as review_mod
from engine.original import shotspec
from engine.original.beats import BEATS_FILE, expand_story, media_story
from engine.original import story as story_mod
from engine.original.genres import GENRES
from engine.original.models import OriginalStory

router = APIRouter(prefix="/api/original", tags=["original"])
STORY_ROOT = Path(__file__).resolve().parents[3] / "output" / "Original_Stories"


def _resolve_story_ws(slug: str, episode: str | None = None) -> Path:
    slug_name = Path(slug).name
    ws = STORY_ROOT / slug_name
    if episode:
        ep_name = Path(episode).name
        if (ws / ep_name).exists():
            return ws / ep_name
        series_ep = STORY_ROOT / "series" / slug_name / ep_name
        if series_ep.exists():
            return series_ep
    if not ws.exists():
        series_dir = STORY_ROOT / "series" / slug_name
        if series_dir.exists():
            if episode:
                ep_name = Path(episode).name
                if (series_dir / ep_name).exists():
                    return series_dir / ep_name
            return series_dir
    return ws


class StoryboardBeatCard(BaseModel):
    panel_id: str
    order: int
    shot: str
    angle: str
    action: str
    caption: str
    status: str  # accept | accept_low | needs_review | repaired | unverified
    score: float | None = None
    audio_duration: float = 0.0
    image_url: str = ""
    candidate_count: int = 0
    selected_candidate: int = 1
    iterations: list[dict] = Field(default_factory=list)
    defects: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class StoryboardWorkbenchData(BaseModel):
    slug: str
    episode: str | None = None
    title: str = ""
    genre: str = ""
    total_panels: int = 0
    beats: list[StoryboardBeatCard] = Field(default_factory=list)


class ApprovePanelRequest(BaseModel):
    episode: str | None = None
    reason: str | None = None


class ApprovePanelResponse(BaseModel):
    panel_id: str
    status: str
    message: str


class RerollPanelRequest(BaseModel):
    episode: str | None = None
    seed: int | None = None
    prompt: str | None = None


class RerollPanelResponse(BaseModel):
    panel_id: str
    status: str
    seed: int
    candidate_file: str
    candidate_n: int
    iterations: list[dict] = Field(default_factory=list)


class ScalePanelRequest(BaseModel):
    episode: str | None = None
    sigma: float = 0.35
    steps: int = 4


class ScalePanelResponse(BaseModel):
    panel_id: str
    status: str
    width: int
    height: int
    scale_info: dict = Field(default_factory=dict)


class ScaleStoryRequest(BaseModel):
    episode: str | None = None
    sigma: float = 0.35
    steps: int = 4


class ScaleStoryResponse(BaseModel):
    slug: str
    episode: str | None = None
    scaled_panels: int
    results: list[ScalePanelResponse] = Field(default_factory=list)


class InpaintPanelRequest(BaseModel):
    mask_png_base64: str = Field(default="", description="Base64-encoded PNG mask (white=redraw, black=preserve)")
    mask: str = Field(default="", description="Alternative alias for mask_png_base64")
    prompt: str = Field(default="", description="Scene prompt describing whole picture with corrected area")
    negative_prompt: str = Field(default="", description="Negative prompt")
    seed: int | None = Field(default=None, description="PRNG seed")
    episode: str | None = Field(default=None, description="Optional episode subfolder")


class InpaintPanelResponse(BaseModel):
    panel_id: str
    candidate_file: str
    candidate_n: int
    seed: int
    sha256: str
    image: str = ""
    candidate: dict = Field(default_factory=dict)
    selected: int | None = None
    prompt: str = ""
    iterations: list[dict] = Field(default_factory=list)


class StoryRequest(BaseModel):
    genre: str
    idea: str = Field(default="", max_length=600)
    scenes: int | None = Field(default=None, ge=3, le=14)


@router.get("/genres")
def genres():
    return {k: {"tone": g.tone, "scenes": g.scenes, "child_safe": g.child_safe} for k, g in GENRES.items()}


@router.post("/story")
async def create_story(req: StoryRequest):
    """Writes premise, bible, outline and panel script with the local LLM and stores story.json."""
    if req.genre not in GENRES:
        raise HTTPException(status_code=422, detail=f"genre must be one of {sorted(GENRES)}")
    provider = llm_registry.get_ollama_provider()  # local first, no cloud or mock fallback
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    try:
        story = await story_mod.generate_story(req.genre, provider, req.idea, req.scenes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    slug = f"{req.genre}_{uuid.uuid4().hex[:6]}"
    ws = STORY_ROOT / slug
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "story.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    return {"slug": slug, "title": story.bible.premise.title, "panels": len(story.panels), "scenes": len(story.scenes),
            "estimated_minutes": story_mod.estimated_minutes(story), "warnings": story.warnings}


def _story_videos(folder: Path) -> list[Path]:
    """Finished renders in a story folder, newest first (the *_backup and v*_prev copies are not listed)."""
    return sorted(folder.glob("story_1080p*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)


@router.get("/stories")
def list_stories():
    """Every story folder under output/Original_Stories: the dashboard shows these next to the database projects."""
    out = []
    if not STORY_ROOT.exists():
        return out
    for folder in STORY_ROOT.iterdir():
        f = folder / "story.json"
        if not folder.is_dir() or not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue    # a half-written story must not hide the others
        premise = (data.get("bible") or {}).get("premise") or {}
        videos = _story_videos(folder)
        out.append({
            "slug": folder.name,
            "title": premise.get("title") or folder.name,
            "genre": premise.get("genre") or folder.name.split("_")[0],
            "panels": len(data.get("panels") or []),
            "has_video": bool(videos),
            "video": videos[0].name if videos else None,
            "updated_at": max(p.stat().st_mtime for p in (f, *videos)),
        })
    return sorted(out, key=lambda s: -s["updated_at"])


class OpenStoryRequest(BaseModel):
    target: Literal["folder", "video"] = "folder"


@router.post("/story/{slug}/open")
def open_story(slug: str, req: OpenStoryRequest):
    """Open the story folder, or its newest finished video, with the desktop's default app."""
    folder = STORY_ROOT / Path(slug).name
    if not (folder / "story.json").exists():
        raise HTTPException(status_code=404, detail="story not found")
    target = folder
    if req.target == "video":
        videos = _story_videos(folder)
        if not videos:
            raise HTTPException(status_code=404, detail="this story has no rendered video yet")
        target = videos[0]
    if not hasattr(os, "startfile"):
        raise HTTPException(status_code=501, detail="opening files is only supported on Windows")
    os.startfile(str(target))
    return {"opened": True, "path": str(target)}


@router.get("/story/{slug}", response_model=OriginalStory)
def get_story(slug: str):
    f = STORY_ROOT / Path(slug).name / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    return OriginalStory.model_validate_json(f.read_text(encoding="utf-8"))


@router.post("/story/{slug}/art")
async def create_art(slug: str, limit: int | None = None, check: bool = True, refine: bool = False):
    """Character sheets + panel images through ComfyUI (cached; reruns only redo changed panels). Long: minutes per ~10 panels.

    refine=true runs directed panels through the review -> plan -> repair/redraw loop (slower; needs the consistency check, i.e. check=true).
    Every candidate is kept under panels/_candidates/ and repaired pictures are flagged for a look."""
    if refine and not check:
        raise HTTPException(status_code=422, detail="refine needs the picture review: it cannot run with check=false")
    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = media_story(ws)
    provider = None
    if check:
        provider = llm_registry.get_ollama_provider()
        if not await provider.health_check():
            raise HTTPException(status_code=503, detail="Ollama is not reachable (needed for the consistency check)")
    try:
        runner = art_mod.ComfyRunner()
    except Exception as e:  # ComfyUI down or workflow/model missing
        raise HTTPException(status_code=503, detail=str(e))
    return await asyncio.to_thread(art_mod.generate_art, story, ws, runner, provider, limit, refine=True if refine else None)


@router.post("/story/{slug}/panel/{panel_id}/inpaint", response_model=InpaintPanelResponse)
async def inpaint_panel_endpoint(slug: str, panel_id: str, req: InpaintPanelRequest):
    """Inpaints a single story panel with adaptive mask padding, Gaussian blur feathering, and 0-pixel drift splicing."""
    raw_mask_b64 = req.mask_png_base64 or req.mask
    if not raw_mask_b64:
        raise HTTPException(status_code=422, detail="mask_png_base64 must not be empty")

    if "," in raw_mask_b64:
        raw_mask_b64 = raw_mask_b64.split(",", 1)[1]

    try:
        mask_bytes = base64.b64decode(raw_mask_b64)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid base64 mask: {e}")

    ws = STORY_ROOT / Path(slug).name
    if req.episode:
        ep_ws = ws / req.episode
        if ep_ws.exists():
            ws = ep_ws
        else:
            series_ep = STORY_ROOT / "series" / Path(slug).name / req.episode
            if series_ep.exists():
                ws = series_ep
    elif not ws.exists():
        series_dir = STORY_ROOT / "series" / Path(slug).name
        if series_dir.exists():
            ws = series_dir

    if not ws.exists():
        raise HTTPException(status_code=404, detail=f"Story '{slug}' not found")

    panel_file = ws / "panels" / f"{panel_id}.png"
    if not panel_file.exists():
        raise HTTPException(status_code=404, detail=f"Panel image '{panel_id}.png' not found")

    try:
        runner = art_mod.ComfyRunner()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        result = await asyncio.to_thread(
            art_mod.inpaint_panel,
            ws=ws,
            panel_id=panel_id,
            mask_bytes=mask_bytes,
            prompt=req.prompt,
            neg=req.negative_prompt,
            seed=req.seed,
            runner=runner,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return InpaintPanelResponse(**result)


@router.get("/story/{slug}/workbench", response_model=StoryboardWorkbenchData)
def get_storyboard_workbench(slug: str, episode: str | None = None):
    """Retrieve full storyboard workbench data for an episode or story including all beat cards, status, duration, and candidate metadata."""
    ws = _resolve_story_ws(slug, episode)
    if not ws.exists():
        raise HTTPException(status_code=404, detail=f"Story workspace '{slug}' not found")

    story_file = ws / BEATS_FILE
    if not story_file.exists():
        story_file = ws / "story.json"
    if not story_file.exists():
        raise HTTPException(status_code=404, detail=f"No story or beats found in workspace '{slug}'")

    story = OriginalStory.model_validate_json(story_file.read_text(encoding="utf-8"))

    art_path = ws / "art.json"
    art_records: dict[str, dict] = {}
    if art_path.exists():
        try:
            raw_art = json.loads(art_path.read_text(encoding="utf-8"))
            art_records = {r.get("panel_id", ""): r for r in raw_art if isinstance(r, dict)}
        except Exception:
            art_records = {}

    beats: list[StoryboardBeatCard] = []
    for order, p in enumerate(story.panels, 1):
        rec = art_records.get(p.id, {})
        status = rec.get("status") or ("accept" if (ws / "panels" / f"{p.id}.png").exists() else "unverified")
        score = rec.get("score") if rec.get("score") is not None else rec.get("match_score")

        duration = 0.0
        wav_file = ws / "voice" / f"{p.id}.wav"
        if not wav_file.exists():
            wav_file = ws / "audio" / f"{p.id}.wav"
        if wav_file.exists():
            try:
                import wave
                with wave.open(str(wav_file), "rb") as wf:
                    duration = round(wf.getnframes() / float(wf.getframerate()), 2)
            except Exception:
                duration = 0.0
        if duration <= 0.0:
            if p.seconds and p.seconds > 0:
                duration = round(p.seconds, 2)
            elif p.caption:
                word_count = len(p.caption.split())
                duration = round(max(1.5, word_count / 2.5), 2)

        panel_png = ws / "panels" / f"{p.id}.png"
        image_url = ""
        if panel_png.exists():
            ep_param = f"?episode={episode}" if episode else ""
            image_url = f"/api/original/story/{slug}/panel/{p.id}/file{ep_param}"

        iterations = rec.get("iterations", [])
        selected = rec.get("selected") or (iterations[-1]["n"] if iterations else 1)
        rev = rec.get("review", {})
        defects = rev.get("defects", []) if isinstance(rev, dict) else []
        reasons = rev.get("reasons", []) if isinstance(rev, dict) else []

        beats.append(StoryboardBeatCard(
            panel_id=p.id,
            order=order,
            shot=p.shot,
            angle=p.angle,
            action=p.action,
            caption=p.caption,
            status=status,
            score=round(score, 3) if score is not None else None,
            audio_duration=duration,
            image_url=image_url,
            candidate_count=len(iterations),
            selected_candidate=selected,
            iterations=iterations,
            defects=defects,
            reasons=reasons,
        ))

    return StoryboardWorkbenchData(
        slug=slug,
        episode=episode,
        title=story.bible.premise.title if story.bible and story.bible.premise else slug,
        genre=story.bible.premise.genre if story.bible and story.bible.premise else "",
        total_panels=len(beats),
        beats=beats,
    )


@router.get("/story/{slug}/panel/{panel_id}/file")
def get_panel_file(slug: str, panel_id: str, episode: str | None = None, candidate: int | None = None):
    """Serve canonical or candidate panel PNG image file."""
    ws = _resolve_story_ws(slug, episode)
    if not ws.exists():
        raise HTTPException(status_code=404, detail="Story not found")

    if candidate is not None:
        target_file = ws / "panels" / "_candidates" / panel_id / f"c{candidate:03d}.png"
    else:
        target_file = ws / "panels" / f"{panel_id}.png"

    if not target_file.exists():
        raise HTTPException(status_code=404, detail=f"Image file '{target_file.name}' not found")

    return FileResponse(
        str(target_file),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/story/{slug}/panel/{panel_id}/approve", response_model=ApprovePanelResponse)
def approve_panel(slug: str, panel_id: str, req: ApprovePanelRequest):
    """Overrule false alarm on ambiguous panel and set status to 'accept'."""
    ws = _resolve_story_ws(slug, req.episode)
    if not ws.exists():
        raise HTTPException(status_code=404, detail="Story not found")

    art_path = ws / "art.json"
    if not art_path.exists():
        raise HTTPException(status_code=404, detail="art.json not found")

    try:
        raw_art = json.loads(art_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read art.json: {e}")

    found = False
    for rec in raw_art:
        if rec.get("panel_id") == panel_id:
            rec["status"] = "accept"
            rev = rec.setdefault("review", {})
            reasons = rev.setdefault("reasons", [])
            approve_note = req.reason or "Approved as-is by creator"
            if approve_note not in reasons:
                reasons.append(approve_note)
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Panel '{panel_id}' not found in art.json")

    art_path.write_text(json.dumps(raw_art, indent=1), encoding="utf-8")
    return ApprovePanelResponse(panel_id=panel_id, status="accept", message="Panel approved by creator")


@router.post("/story/{slug}/panel/{panel_id}/reroll", response_model=RerollPanelResponse)
async def reroll_panel(slug: str, panel_id: str, req: RerollPanelRequest):
    """Regenerate single panel with new PRNG seed (seed + 7919) and update candidate archive."""
    ws = _resolve_story_ws(slug, req.episode)
    if not ws.exists():
        raise HTTPException(status_code=404, detail="Story not found")

    story_file = ws / BEATS_FILE
    if not story_file.exists():
        story_file = ws / "story.json"
    if not story_file.exists():
        raise HTTPException(status_code=404, detail="story.json not found")

    story = OriginalStory.model_validate_json(story_file.read_text(encoding="utf-8"))
    panel = next((p for p in story.panels if p.id == panel_id), None)
    if panel is None:
        raise HTTPException(status_code=404, detail=f"Panel '{panel_id}' not found in story")

    art_path = ws / "art.json"
    raw_art = []
    if art_path.exists():
        try:
            raw_art = json.loads(art_path.read_text(encoding="utf-8"))
        except Exception:
            raw_art = []

    rec = next((r for r in raw_art if r.get("panel_id") == panel_id), None)
    existing_seed = rec.get("seed", 42) if rec else 42
    iters = rec.get("iterations", []) if rec else []

    new_seed = req.seed if req.seed is not None else (existing_seed + 7919)

    try:
        runner = art_mod.ComfyRunner()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ComfyUI runner unavailable: {e}")

    shown = [c for c in story.bible.characters if c.id in panel.character_ids][:2]
    spec = shotspec.ShotSpec(**panel.director) if panel.director else None
    spec_shot = spec.shot if spec else panel.shot
    pw, ph = art_mod.frame_size(story) or shotspec.resolve_dimensions(spec_shot, num_characters=len(shown), default=(1344, 768))

    style = getattr(runner, "style", "tags")
    engine = getattr(runner, "engine", "qwen")
    pos_i, neg_i = art_mod.build_prompt(story, panel, style=style, runner=runner, engine=engine)
    if req.prompt:
        pos_i = req.prompt

    ref = ws / "sheets" / f"{shown[0].id}.png" if shown and getattr(runner, "ipa", None) is not None else None
    ref_b = ws / "sheets" / f"{shown[1].id}.png" if len(shown) == 2 and getattr(runner, "ipa2", None) is not None else None

    png = await asyncio.to_thread(
        runner.generate,
        pos=pos_i,
        neg=neg_i,
        seed=new_seed,
        width=pw,
        height=ph,
        prefix=f"panel_{panel_id}_reroll",
        reference=ref,
        reference_b=ref_b,
    )

    cand = art_mod._record_candidate(
        ws,
        panel_id,
        iters,
        png,
        kind="generate",
        attempt=len(iters),
        seed=new_seed,
        prompt=pos_i,
        negative=neg_i,
        width=pw,
        height=ph,
        engine=str(engine),
        workflow="qwen_image_21" if engine == "qwen" else "",
    )

    panel_img = ws / "panels" / f"{panel_id}.png"
    panel_img.write_bytes(png)

    provider = llm_registry.get_ollama_provider()
    rev = None
    status = "accept"
    if await provider.health_check() and spec is not None:
        tmp = ws / "panels" / f"_try_reroll_{panel_id}.png"
        tmp.write_bytes(png)
        try:
            claims = await review_mod.extract_claims(provider, panel.caption) if panel.caption else []
            chars_dict = {c.id: c for c in story.bible.characters}
            rev = await review_mod.review_image(provider, tmp, claims, spec, chars_dict, review_mode="assisted")
            status = "accept" if rev.decision == "accept" else "needs_review"
            cand["review"] = art_mod._review_summary(rev)
        except Exception:
            status = "unverified"
        finally:
            tmp.unlink(missing_ok=True)

    if rec:
        rec["seed"] = new_seed
        rec["selected"] = cand["n"]
        rec["status"] = status
        rec["iterations"] = iters
        if rev:
            rec["review"] = rev.model_dump()
            rec["score"] = rev.score
    else:
        new_rec = {
            "panel_id": panel_id,
            "image": str(panel_img),
            "seed": new_seed,
            "attempts": 1,
            "score": rev.score if rev else 1.0,
            "status": status,
            "review": rev.model_dump() if rev else {},
            "iterations": iters,
            "selected": cand["n"],
        }
        raw_art.append(new_rec)

    art_path.write_text(json.dumps(raw_art, indent=1), encoding="utf-8")

    return RerollPanelResponse(
        panel_id=panel_id,
        status=status,
        seed=new_seed,
        candidate_file=cand["file"],
        candidate_n=cand["n"],
        iterations=iters,
    )


@router.post("/story/{slug}/panel/{panel_id}/scale", response_model=ScalePanelResponse)
async def scale_panel_endpoint(slug: str, panel_id: str, req: ScalePanelRequest):
    """Two-stage composition-preserving scaling for a single panel: 2x Lanczos + partial-denoise refiner pass."""
    ws = _resolve_story_ws(slug, req.episode)
    if not ws.exists():
        raise HTTPException(status_code=404, detail="Story not found")

    panel_img = ws / "panels" / f"{panel_id}.png"
    if not panel_img.exists():
        raise HTTPException(status_code=404, detail=f"Panel image '{panel_id}.png' not found")

    story_file = ws / BEATS_FILE
    if not story_file.exists():
        story_file = ws / "story.json"
    story = OriginalStory.model_validate_json(story_file.read_text(encoding="utf-8")) if story_file.exists() else None
    panel = next((p for p in story.panels if p.id == panel_id), None) if story else None

    prompt = panel.action if panel else "masterpiece, highly detailed, clean lines"
    neg = "blurry, low quality, distorted"

    try:
        runner = art_mod.ComfyRunner()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ComfyUI runner unavailable: {e}")

    draft_bytes = panel_img.read_bytes()
    try:
        refined_bytes, scale_info = await asyncio.to_thread(
            refine_mod.scale_and_refine_panel,
            runner=runner,
            draft_bytes=draft_bytes,
            prompt=prompt,
            neg=neg,
            seed=42,
            sigma=req.sigma,
            steps=req.steps,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scaling failed: {e}")

    art_path = ws / "art.json"
    raw_art = []
    if art_path.exists():
        try:
            raw_art = json.loads(art_path.read_text(encoding="utf-8"))
        except Exception:
            raw_art = []
    rec = next((r for r in raw_art if r.get("panel_id") == panel_id), None)
    iters = rec.get("iterations", []) if rec else []

    cand = art_mod._record_candidate(
        ws,
        panel_id,
        iters,
        refined_bytes,
        kind="scale_2x",
        seed=42,
        prompt=prompt,
        width=scale_info["width"],
        height=scale_info["height"],
        workflow="qwen_image_21_inpaint",
    )
    panel_img.write_bytes(refined_bytes)

    if rec:
        rec["selected"] = cand["n"]
        rec["iterations"] = iters
        rec["status"] = "accept"
    else:
        raw_art.append({
            "panel_id": panel_id,
            "image": str(panel_img),
            "seed": 42,
            "status": "accept",
            "iterations": iters,
            "selected": cand["n"],
        })
    art_path.write_text(json.dumps(raw_art, indent=1), encoding="utf-8")

    return ScalePanelResponse(
        panel_id=panel_id,
        status="accept",
        width=scale_info["width"],
        height=scale_info["height"],
        scale_info=scale_info,
    )


@router.post("/story/{slug}/scale", response_model=ScaleStoryResponse)
async def scale_story_endpoint(slug: str, req: ScaleStoryRequest):
    """Batch two-stage composition-preserving scaling for all panels in an episode or story."""
    ws = _resolve_story_ws(slug, req.episode)
    if not ws.exists():
        raise HTTPException(status_code=404, detail="Story not found")

    story_file = ws / BEATS_FILE
    if not story_file.exists():
        story_file = ws / "story.json"
    if not story_file.exists():
        raise HTTPException(status_code=404, detail="Story file not found")

    story = OriginalStory.model_validate_json(story_file.read_text(encoding="utf-8"))
    results: list[ScalePanelResponse] = []

    for p in story.panels:
        panel_file = ws / "panels" / f"{p.id}.png"
        if not panel_file.exists():
            continue
        scale_req = ScalePanelRequest(episode=req.episode, sigma=req.sigma, steps=req.steps)
        res = await scale_panel_endpoint(slug=slug, panel_id=p.id, req=scale_req)
        results.append(res)

    return ScaleStoryResponse(
        slug=slug,
        episode=req.episode,
        scaled_panels=len(results),
        results=results,
    )


@router.post("/story/{slug}/animate")
async def animate_story(slug: str, beats: str | None = None, max_clips: int | None = None, seconds: float = 3.6):
    """Animates beats with the fast H3 image-to-video workflow (about a minute each) into clips/<beat>.mp4; the video step then shows them.
    `beats` is a comma list of beat ids; without it the most active beat of each scene is chosen (about one in five, or `max_clips`)."""
    from engine.original import animate as animate_mod

    if not 1.0 <= seconds <= 8.0:
        raise HTTPException(status_code=422, detail="seconds must be between 1 and 8")
    ws = STORY_ROOT / Path(slug).name
    if not (ws / "story.json").exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = media_story(ws)
    ids = [b.strip() for b in beats.split(",") if b.strip()] if beats else None
    try:
        return await asyncio.to_thread(animate_mod.animate_beats, story, ws, ids, max_clips, seconds=seconds)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # ComfyUI down, workflow or models missing
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/story/{slug}/video")
async def create_video(slug: str, burn_captions: bool = True):
    """Voices every panel with an image, renders the 1080p video (Ken Burns, captions, music) and writes the YouTube package."""
    from engine.original import video as video_mod

    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = media_story(ws)
    try:
        out = await asyncio.to_thread(lambda: video_mod.build_video(story, ws, None, 30.0, burn_captions, size=video_mod.frame_canvas(story)))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {**out, "package": await asyncio.to_thread(video_mod.package, story, ws)}


@router.post("/story/{slug}/pages")
async def create_pages(slug: str):
    """Letters the panels (balloons, narrator box, SFX) and composes comic pages + a PDF from the generated art."""
    from engine.original import pages as pages_mod

    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = media_story(ws)
    try:
        return await asyncio.to_thread(pages_mod.build_pages, story, ws)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---- series: a persistent cast/world, many episodes, one daily queue ---------------------------------------------------
from datetime import date as _date

from fastapi import Depends
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.jobs.manager import job_manager
from engine.original.queue import JOB_TYPE, enqueue_episodes
from engine.original.series import SeriesStore, publish_times

SERIES_ROOT = STORY_ROOT / "series"


def _store() -> SeriesStore:
    return SeriesStore(SERIES_ROOT)


class SeriesRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    genre: str
    idea: str = Field(default="", max_length=600)
    channel_id: str = ""


class EpisodesRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=30)
    start_date: _date | None = None  # first publish day; default tomorrow, then one per day at 18:00
    scenes: int | None = Field(default=None, ge=3, le=14)
    check: bool = True
    refine: bool = False  # review each picture, then repair or redraw it (slower; needs check=true)
    animate: bool = False  # animate about one beat in five with the fast H3 workflow (about a minute each)
    preview: bool = False  # fast preview pass (0.25 MP drafts in 8-11s, sets status="draft", skips video render)


@router.post("/series")
async def create_series(req: SeriesRequest):
    if req.genre not in GENRES:
        raise HTTPException(status_code=422, detail=f"genre must be one of {sorted(GENRES)}")
    if req.channel_id:
        from engine.anime.review.channels import channel_store
        try:
            channel_store.get(req.channel_id)
        except KeyError as e:
            raise HTTPException(status_code=422, detail=str(e))
    provider = llm_registry.get_ollama_provider()
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    try:
        bible = await story_mod.generate_series_bible(req.genre, provider, req.idea)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _store().create(req.name, req.genre, bible, req.channel_id, req.idea)


@router.get("/series")
def list_series():
    return _store().list()


@router.get("/series/{series_id}")
def get_series(series_id: str):
    try:
        return _store().get(series_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="series not found")


@router.post("/series/{series_id}/episodes")
def queue_episodes(series_id: str, req: EpisodesRequest, db: Session = Depends(get_db)):
    """Queues `count` consecutive episodes as durable jobs with one publish slot per day (upload itself is not automated yet)."""
    if req.refine and not req.check:
        raise HTTPException(status_code=422, detail="refine needs the picture review: it cannot run with check=false")
    store = _store()
    try:
        store.get(series_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="series not found")
    try:
        return enqueue_episodes(db, store, series_id, req.count, publish_times(req.count, req.start_date), req.scenes, req.check, req.refine, req.animate, req.preview)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/jobs")
def list_episode_jobs(limit: int = 50):
    return [j for j in job_manager.list_all_jobs(limit=200) if j["job_type"] == JOB_TYPE][:limit]


class UploadRequest(BaseModel):
    made_for_kids: bool  # required: a legal declaration the channel owner makes, never defaulted
    privacy: str = "private"
    schedule: bool = False  # private upload that YouTube publishes at the episode's slot
    confirm_public: bool = False
    force: bool = False


@router.post("/series/{series_id}/episodes/{number}/upload", status_code=202)
def upload_episode_route(series_id: str, number: int, req: UploadRequest):
    """Starts the upload in the background (minutes for a long video); poll the series for `upload_status`."""
    import threading

    from engine.api.routers.youtube import auth as yt_auth
    from engine.original import upload as upload_mod
    from engine.youtube.auth import AuthError
    from engine.youtube.client import YouTubeClient

    store = _store()
    if not yt_auth.status()["connected"]:
        raise HTTPException(status_code=409, detail="YouTube is not connected")
    kwargs = dict(made_for_kids=req.made_for_kids, privacy=req.privacy, schedule=req.schedule,
                  confirm_public=req.confirm_public, force=req.force)
    try:
        upload_mod.plan_upload(store, series_id, number, **kwargs)  # refuse before starting anything
    except KeyError:
        raise HTTPException(status_code=404, detail="series not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    def run():
        try:
            upload_mod.upload_episode(store, series_id, number, YouTubeClient(yt_auth), **kwargs)
        except (AuthError, Exception):  # the failure is recorded on the episode by upload_episode
            pass

    threading.Thread(target=run, daemon=True).start()
    return {"series": series_id, "episode": number, "status": "uploading"}


@router.post("/story/{slug}/beats")
async def create_beats(slug: str):
    """One picture per narrated moment: splits each panel's narration and writes a brief from the spoken text (beats.json)."""
    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    provider = llm_registry.get_ollama_provider()
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    story = await expand_story(OriginalStory.model_validate_json(f.read_text(encoding="utf-8")), provider)
    (ws / BEATS_FILE).write_text(story.model_dump_json(indent=2), encoding="utf-8")
    return {"beats": len(story.panels), "warnings": story.warnings}


# ------------------------------------------------------------------ animated film (engine/original/film.py, film_master.py, score.py)
_FILM_JOBS: dict[str, dict] = {}


def _film_start(slug: str, kind: str, fn) -> dict:
    """Runs one film stage in a background thread (a stage is minutes to hours). One at a time: the stages share one GPU."""
    import threading

    if any(j["status"] == "running" for j in _FILM_JOBS.values()):
        raise HTTPException(status_code=409, detail="another film stage is running (one GPU); poll /film/job/{id} or cancel it")
    job = {"id": uuid.uuid4().hex[:8], "slug": slug, "kind": kind, "status": "running", "progress": 0.0, "message": "starting", "result": None, "error": None,
           "cancel": False}
    _FILM_JOBS[job["id"]] = job

    def run():
        try:
            job["result"] = fn(lambda p, m: job.update(progress=round(p, 3), message=m), lambda: job["cancel"])
            job["status"] = "done"
        except BaseException as e:  # recorded on the job; the thread must not die silently
            job["status"], job["error"] = ("cancelled" if str(e) == "cancelled" else "failed"), str(e)[:600]

    threading.Thread(target=run, daemon=True).start()
    return {k: job[k] for k in ("id", "slug", "kind", "status")}


def _film_story(slug: str) -> tuple[Path, OriginalStory]:
    ws = STORY_ROOT / Path(slug).name
    if not (ws / "story.json").exists():
        raise HTTPException(status_code=404, detail="story not found")
    return ws, OriginalStory.model_validate_json((ws / "story.json").read_text(encoding="utf-8"))


def _ids(ids: str | None) -> list[str] | None:
    return [i.strip() for i in ids.split(",") if i.strip()] if ids else None


def _pairs(text: str | None) -> dict[str, int] | None:
    return {k: int(v) for k, v in (kv.split(":") for kv in text.split(","))} if text else None


@router.post("/story/{slug}/film/frames", status_code=202)
def film_frames(slug: str, ids: str | None = None, rerolls: str | None = None):
    """16:9 first frame per shot (`ids` = comma list; `rerolls` = `p003:1,p005:2` new seeds for pictures that were not good enough)."""
    from engine.original import film

    ws, story = _film_story(slug)
    rer = _pairs(rerolls)
    return _film_start(slug, "frames", lambda prog, cancelled: film.make_frames(story, ws, art_mod.ComfyRunner(), _ids(ids), rer, prog, cancelled))


@router.post("/story/{slug}/film/clips", status_code=202)
def film_clips(slug: str, ids: str | None = None, seeds: str | None = None, quiet: str | None = None, native_voice: bool = False):
    """H3 clip per shot from its frame; a speaking shot gets its character's voice anchored to the face (lip sync), or with native_voice=true
    H3 speaks the line itself in a voice described from the character (no TTS). Hours for a whole film."""
    from engine.original import film

    ws, story = _film_story(slug)
    sd = _pairs(seeds)
    return _film_start(slug, "clips", lambda prog, cancelled: film.make_clips(story, ws, _ids(ids), sd, progress=prog, is_cancelled=cancelled, quiet=_ids(quiet), native_voice=native_voice))


@router.post("/story/{slug}/film/score", status_code=202)
def film_score(slug: str):
    """One local ACE-Step cue per scene, sized from the clips already made (unloads ComfyUI and the LLM first)."""
    from engine.original import film_master, score

    ws, story = _film_story(slug)

    def run(prog, cancelled):
        secs: dict[str, float] = {}
        for c in film_master.timeline(story, ws):
            secs[c["scene"]] = secs.get(c["scene"], 0.0) + c["seconds"]
        score.free_gpu()
        return {k: str(v) for k, v in score.make_cues(story, ws, secs, prog).items()}

    return _film_start(slug, "score", run)


@router.post("/story/{slug}/film/master", status_code=202)
def film_master_render(slug: str, ids: str | None = None, music: bool = True, name: str = "film_master"):
    """Cuts every clip in story order, mixes the score under it (ducked), writes the 1080p mp4 and the SRT captions."""
    from engine.original import film_master

    ws, story = _film_story(slug)

    def run(prog, cancelled):
        cues = {sc.id: ws / "film" / "audio" / "music" / f"{sc.id}.wav" for sc in story.scenes} if music else None
        out = film_master.render(story, ws, cues, _ids(ids), name, story.bible.premise.title)
        return {**out, "loudness": film_master.loudness(Path(out["video"]))}

    return _film_start(slug, "master", run)


@router.get("/film/job/{job_id}")
def film_job(job_id: str):
    job = _FILM_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="film job not found (jobs live in engine memory; a restart forgets them)")
    return {k: v for k, v in job.items() if k != "cancel"}


@router.post("/film/job/{job_id}/cancel")
def film_job_cancel(job_id: str):
    job = _FILM_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="film job not found")
    job["cancel"] = True
    return {"id": job_id, "cancelling": True}


@router.get("/story/{slug}/film/status")
def film_status(slug: str):
    """What exists per shot: frame, clip, its measured motion (a clip below the stillness limit is flagged), and the running job if any."""
    from engine.original import film

    ws, story = _film_story(slug)
    fd = ws / "film"
    clips = json.loads((fd / "clips.json").read_text(encoding="utf-8")) if (fd / "clips.json").exists() else {}
    shots = []
    for p in story.panels:
        c = clips.get(p.id, {})
        shots.append({"id": p.id, "scene": p.scene_id, "frame": (fd / "frames" / f"{p.id}.png").exists(), "clip": (fd / "clips" / f"{p.id}.mp4").exists(),
                      "speaks": bool(p.dialogue), "seconds": c.get("stats", {}).get("seconds"), "motion": c.get("stats", {}).get("motion"),
                      "too_still": bool(c) and c.get("stats", {}).get("motion", 9) < film.MIN_MOTION})
    running = [{k: j[k] for k in ("id", "kind", "status", "progress", "message")} for j in _FILM_JOBS.values() if j["slug"] == Path(slug).name and j["status"] == "running"]
    return {"shots": len(shots), "frames": sum(s["frame"] for s in shots), "clips": sum(s["clip"] for s in shots),
            "seconds": round(sum(s["seconds"] or 0 for s in shots), 1), "too_still": [s["id"] for s in shots if s["too_still"]], "running": running, "detail": shots}


# ------------------------------------------------------------------ clip evaluation and the correction loop (engine/original/clip_eval.py, clip_loop.py)
def _shot_clip(slug: str, shot: str) -> tuple[Path, OriginalStory, Path]:
    ws, story = _film_story(slug)
    if not any(p.id == shot for p in story.panels):
        raise HTTPException(status_code=404, detail="shot not found")
    clip = ws / "film" / "clips" / f"{Path(shot).name}.mp4"
    return ws, story, clip


@router.get("/story/{slug}/film/clip/{shot}/eval")
def film_clip_eval(slug: str, shot: str, camera: str = "static"):
    """Measured review of one clip: camera path, hard cuts, flicker, stillness, colour drift, audio, as flags with timestamps (no overall score). camera=static|any."""
    from engine.original.clip_eval import evaluate

    if camera not in ("static", "any"):
        raise HTTPException(status_code=422, detail="camera must be static or any")
    _, _, clip = _shot_clip(slug, shot)
    if not clip.is_file():
        raise HTTPException(status_code=404, detail="no clip for this shot yet")
    return evaluate(clip, expect_camera=camera)


@router.post("/story/{slug}/film/clip/{shot}/improve", status_code=202)
def film_clip_improve(slug: str, shot: str, attempts: int = 3, camera: str = "static", suspected: bool = False, apply: bool = False, redraw: bool = True):
    """Correction loop for one shot (background job, one GPU): evaluate, change ONE thing, regenerate in an isolated workspace, keep the better clip, repeat. The real
    clip is only replaced with apply=true. History: GET .../history."""
    from engine.original import clip_loop

    if camera not in ("static", "any") or not 1 <= attempts <= 6:
        raise HTTPException(status_code=422, detail="camera must be static or any; attempts 1-6")
    ws, story, clip = _shot_clip(slug, shot)
    if not clip.is_file():
        raise HTTPException(status_code=404, detail="no clip for this shot yet")
    base = clip_loop.baseline_settings(story, ws, shot)

    def run(prog, cancelled):
        runner = art_mod.ComfyRunner() if redraw else None
        levers = clip_loop.DEFAULT_LEVERS | (clip_loop.FRAME_LEVERS if runner else frozenset())
        out = clip_loop.improve_clip(shot, ws, clip_loop.film_generate(story, ws, shot, runner, base), base, attempts=attempts, expect_camera=camera,
                                     act_on_suspected=suspected, apply=apply, levers=levers, planned_cuts=[x["at"] for x in base.get("shots", [])[1:]] or None)
        return {k: v for k, v in out.items() if k != "history"} | {"attempts": [{k: h.get(k) for k in ("attempt", "lever", "decision", "reason", "changed")} for h in out["history"]]}

    return _film_start(slug, "improve", run)


@router.get("/story/{slug}/film/clip/{shot}/history")
def film_clip_history(slug: str, shot: str):
    """Every correction attempt recorded for a shot (settings, evaluator flags, decision), oldest first."""
    ws, _, _ = _shot_clip(slug, shot)
    path = ws / "film" / "history" / f"{Path(shot).name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
