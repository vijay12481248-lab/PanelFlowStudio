"""Original Story Studio endpoints (docs/ORIGINAL_STORY_STUDIO.md)."""
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.llm.registry import llm_registry
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
