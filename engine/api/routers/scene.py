"""Scene Director endpoints (docs/SCENE_DIRECTOR.md): brief -> plan -> picture, and the owner's ratings."""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from engine.config.settings import settings
from engine.database.session import get_db
from engine.jobs.workflow import enqueue_project_operation
from engine.llm.registry import llm_registry
from engine.original import scene_job, scene_store
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


# ---- runs, the owner's feedback and the knowledge base (docs/SCENE_DIRECTOR.md) ----------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    liked: int = Field(ge=0, le=100)  # how much the owner liked the picture, in percent
    agrees_with_ai: bool
    good_tags: list[str] = Field(default_factory=list, max_length=12)
    wrong_tags: list[str] = Field(default_factory=list, max_length=12)
    note: str = Field(default="", max_length=4000)


@router.get("/runs")
def list_runs(unreviewed: bool = False, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return scene_store.list_runs(db, unreviewed=unreviewed, limit=limit, offset=offset)


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    try:
        return scene_store.get_run(db, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")


@router.get("/runs/{run_id}/image")
def run_image(run_id: str, db: Session = Depends(get_db)):
    try:
        run = scene_store.get_run(db, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")
    root = scene_job.SCENE_ROOT.resolve()
    path = (root / run["project_id"] / run["image_path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():  # a stored path can never lead out of the scene folder
        raise HTTPException(status_code=404, detail="picture not found")
    return FileResponse(path)


@router.post("/runs/{run_id}/feedback")
def submit_feedback(run_id: str, req: FeedbackRequest, db: Session = Depends(get_db)):
    try:
        return scene_store.submit_feedback(db, run_id, liked=req.liked, agrees_with_ai=req.agrees_with_ai, good_tags=req.good_tags, wrong_tags=req.wrong_tags, note=req.note)
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/runs/{run_id}/dismiss")
def dismiss_run(run_id: str, db: Session = Depends(get_db)):
    try:
        return scene_store.dismiss(db, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")


@router.get("/knowledge/stats")
def knowledge_stats(db: Session = Depends(get_db)):
    return scene_store.stats(db)


@router.get("/knowledge/search")
def knowledge_search(q: str = "", limit: int = 20, db: Session = Depends(get_db)):
    return scene_store.search(db, q, limit)
