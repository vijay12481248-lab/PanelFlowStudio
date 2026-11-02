"""Original Story Studio endpoints (docs/ORIGINAL_STORY_STUDIO.md)."""
import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.llm.registry import llm_registry
from engine.original import art as art_mod
from engine.original import story as story_mod
from engine.original.genres import GENRES
from engine.original.models import OriginalStory

router = APIRouter(prefix="/api/original", tags=["original"])
STORY_ROOT = Path(__file__).resolve().parents[3] / "output" / "Original_Stories"


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


@router.get("/story/{slug}", response_model=OriginalStory)
def get_story(slug: str):
    f = STORY_ROOT / Path(slug).name / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    return OriginalStory.model_validate_json(f.read_text(encoding="utf-8"))


@router.post("/story/{slug}/art")
async def create_art(slug: str, limit: int | None = None, check: bool = True):
    """Character sheets + panel images through ComfyUI (cached; reruns only redo changed panels). Long: minutes per ~10 panels."""
    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = OriginalStory.model_validate_json(f.read_text(encoding="utf-8"))
    provider = None
    if check:
        provider = llm_registry.get_ollama_provider()
        if not await provider.health_check():
            raise HTTPException(status_code=503, detail="Ollama is not reachable (needed for the consistency check)")
    try:
        runner = art_mod.ComfyRunner()
    except Exception as e:  # ComfyUI down or workflow/model missing
        raise HTTPException(status_code=503, detail=str(e))
    return await asyncio.to_thread(art_mod.generate_art, story, ws, runner, provider, limit)


@router.post("/story/{slug}/video")
async def create_video(slug: str, burn_captions: bool = True):
    """Voices every panel with an image, renders the 1080p video (Ken Burns, captions, music) and writes the YouTube package."""
    from engine.original import video as video_mod

    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = OriginalStory.model_validate_json(f.read_text(encoding="utf-8"))
    try:
        out = await asyncio.to_thread(video_mod.build_video, story, ws, None, 30.0, burn_captions)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {**out, "package": await asyncio.to_thread(video_mod.package, story, ws)}
