"""Scene Director endpoints (docs/SCENE_DIRECTOR.md): brief -> plan -> picture, and the owner's ratings."""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.config.settings import settings
from engine.jobs.workflow import enqueue_project_operation
from engine.llm.registry import llm_registry
from engine.original import scene_job
from engine.original.scene_plan import ScenePlan, load_playbook, validate_plan
from engine.original.scene_planner import apply_corrections, plan_to_words, propose
from engine.original.scene_ratings import REASONS, Rating, load_ratings, save_rating, summary

router = APIRouter(prefix="/api/original/scene", tags=["scene"])


def ratings_path() -> Path:
    return settings.app_data_dir / "config" / "scene_ratings.json"


class ProposeRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    scene_type: str | None = None


class CorrectRequest(BaseModel):
    plan: ScenePlan
    corrections: dict[str, str]


class GenerateRequest(BaseModel):
    project_id: str
    plan: ScenePlan
    seed: int | None = None


class RateRequest(BaseModel):
    brief_id: str = Field(min_length=1)
    good: bool
    mode: Literal["raw", "director"] = "director"
    reason: str = ""
    seconds: float = 0.0
    plan_path: str = ""


@router.post("/propose")
async def propose_plan(req: ProposeRequest):
    provider = llm_registry.get_ollama_provider()  # local first, no cloud or mock fallback
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    try:
        return (await propose(provider, req.brief, req.scene_type)).model_dump()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/correct")
def correct_plan(req: CorrectRequest):
    try:
        plan = apply_corrections(req.plan, load_playbook(req.plan.scene_type), req.corrections)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"plan": plan.model_dump(), "summary": plan_to_words(plan)}


@router.post("/generate")
def generate(req: GenerateRequest):
    try:
        problems = validate_plan(req.plan, load_playbook(req.plan.scene_type))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))
    job_id = enqueue_project_operation(
        req.project_id, scene_job.JOB_TYPE, scene_job.build_scene_operation(req.project_id, {"plan": req.plan.model_dump(), "seed": req.seed}),
        priority=20, requires_gpu=True, gpu_vram_mb=10000, max_retries=1, job_input={"plan": req.plan.model_dump(), "seed": req.seed})
    return {"job_id": job_id, "status": "QUEUED"}


@router.post("/rate")
def rate(req: RateRequest):
    if not req.good and req.reason and req.reason not in REASONS:
        raise HTTPException(status_code=422, detail=f"reason must be one of {list(REASONS)}")
    save_rating(ratings_path(), Rating(brief_id=req.brief_id, mode=req.mode, good=req.good, reason=req.reason, seconds=req.seconds, plan_path=req.plan_path))
    return summary(load_ratings(ratings_path()))


@router.get("/ratings/summary")
def ratings_summary(mode: Literal["raw", "director"] | None = None):
    rows = load_ratings(ratings_path())
    return summary([r for r in rows if mode is None or r.mode == mode])
