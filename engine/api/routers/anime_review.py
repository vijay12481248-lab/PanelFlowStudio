"""Anime Review workflow endpoints (docs/ANIME_REVIEW.md). Every entry point goes through the rights gate."""
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.acquisition.rights.models import RightsDeclaration
from engine.anime.review import analysis, clips as clips_mod, ingest as ingest_mod, script as script_mod, understanding
from engine.llm.registry import llm_registry
from engine.anime.review.models import ClipPlan, EpisodeAnalysis, IngestRecord, ReviewScript, Understanding

router = APIRouter(prefix="/api/anime/review", tags=["anime-review"])
WORKSPACE_ROOT = Path(__file__).resolve().parents[3] / "output" / "Anime_Reviews"


class IngestRequest(BaseModel):
    source: str  # URL or local path
    title: str
    rights: RightsDeclaration


def _workspace(slug: str) -> Path:
    ws = WORKSPACE_ROOT / ingest_mod.slugify(slug)
    return ws


@router.post("/ingest", response_model=IngestRecord)
async def ingest_episode(req: IngestRequest):
    try:
        return await asyncio.to_thread(ingest_mod.ingest, req.source, _workspace(req.title), req.rights, req.title)
    except ValueError as e:  # includes the rights refusal
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))


@router.post("/{slug}/analyze", response_model=EpisodeAnalysis)
async def analyze_episode(slug: str, use_asr: bool = True):
    ws = _workspace(slug)
    src = ws / "source.json"
    if not src.exists():
        raise HTTPException(status_code=404, detail="episode not ingested")
    rec = IngestRecord.model_validate_json(src.read_text(encoding="utf-8"))
    rec.rights.validate_for_acquisition()
    return await asyncio.to_thread(analysis.analyze, rec, ws, use_asr)


def _load(ws: Path, name: str, model):
    f = ws / name
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"{name} missing - run the previous step first")
    return model.model_validate_json(f.read_text(encoding="utf-8"))


@router.post("/{slug}/understand", response_model=Understanding)
async def understand_episode(slug: str):
    ws = _workspace(slug)
    rec = _load(ws, "source.json", IngestRecord)
    rec.rights.validate_for_acquisition()
    a = _load(ws, "analysis.json", EpisodeAnalysis)
    provider = llm_registry.get_ollama_provider()  # local first; no silent cloud/mock fallback
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    u = await understanding.understand(a, rec.title, provider, Path(a.audio_path) if a.audio_path else None)
    (ws / "understanding.json").write_text(u.model_dump_json(indent=2), encoding="utf-8")
    return u


@router.post("/{slug}/clips", response_model=ClipPlan)
async def plan_clips(slug: str, target_video_sec: float = 480.0):
    ws = _workspace(slug)
    _load(ws, "source.json", IngestRecord).rights.validate_for_acquisition()
    a = _load(ws, "analysis.json", EpisodeAnalysis)
    u = _load(ws, "understanding.json", Understanding)
    rms = understanding.energy_peaks(Path(a.audio_path))[1] if a.audio_path else None
    plan = clips_mod.select_clips(a, u.beats, target_video_sec, rms)
    (ws / "clips.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return plan


@router.post("/{slug}/script", response_model=ReviewScript)
async def write_review_script(slug: str, tone: str = "warm, witty, honest fan reviewer", language: str = "English"):
    ws = _workspace(slug)
    rec = _load(ws, "source.json", IngestRecord)
    rec.rights.validate_for_acquisition()
    u = _load(ws, "understanding.json", Understanding)
    plan = _load(ws, "clips.json", ClipPlan)
    provider = llm_registry.get_ollama_provider()
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    try:
        sc = await script_mod.write_script(rec.title, u, plan, provider, tone, language)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    (ws / "script.json").write_text(sc.model_dump_json(indent=2), encoding="utf-8")
    return sc
