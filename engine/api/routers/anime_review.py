"""Anime Review workflow endpoints (docs/ANIME_REVIEW.md). Every entry point goes through the rights gate."""
import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from engine.acquisition.rights.models import RightsDeclaration
from engine.anime.review import analysis, clips as clips_mod, packaging as packaging_mod, render as render_mod, ingest as ingest_mod, script as script_mod, timeline as timeline_mod, understanding
from engine.anime.review.channels import ChannelPreset, channel_store
from engine.anime.review.pipeline import ReviewJobSpec
from engine.anime.review.queue import JOB_TYPE, enqueue_review
from engine.database.session import get_db
from engine.jobs.manager import job_manager
from engine.llm.registry import llm_registry
from engine.anime.review.models import ClipPlan, EpisodeAnalysis, IngestRecord, ReviewScript, Timeline, Understanding

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


@router.post("/{slug}/voice", response_model=Timeline)
async def voice_and_sync(slug: str, voice: str = "am_michael", rate: float = 1.0):
    ws = _workspace(slug)
    rec = _load(ws, "source.json", IngestRecord)
    rec.rights.validate_for_acquisition()
    sc = _load(ws, "script.json", ReviewScript)
    plan = _load(ws, "clips.json", ClipPlan)
    return await asyncio.to_thread(timeline_mod.voice_script, sc, plan, ws, rec.fps, voice, rate)


@router.post("/{slug}/render")
async def render_review(slug: str, burn_captions: bool = True):
    """Renders the 1080p review and writes the YouTube package next to it."""
    ws = _workspace(slug)
    rec = _load(ws, "source.json", IngestRecord)
    rec.rights.validate_for_acquisition()
    sc, tl = _load(ws, "script.json", ReviewScript), _load(ws, "timeline.json", Timeline)
    plan, u = _load(ws, "clips.json", ClipPlan), _load(ws, "understanding.json", Understanding)
    src = Path(rec.local_path)
    out = await asyncio.to_thread(render_mod.render_review, sc, tl, src, rec.has_audio, ws, burn_captions)
    pkg = await asyncio.to_thread(packaging_mod.build_package, rec.title, sc, u, tl, plan, src, rec.rights, ws)
    return {"video": str(out), "srt": str(ws / "review.srt"), "package": pkg}


@router.get("/channels", response_model=list[ChannelPreset])
def list_channels():
    return channel_store.list()


@router.put("/channels", response_model=ChannelPreset)
def save_channel(preset: ChannelPreset):
    return channel_store.save(preset)


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str):
    channel_store.delete(channel_id)
    return {"deleted": channel_id}


class QueueItem(BaseModel):
    source: str
    title: str
    rights: RightsDeclaration
    channel_id: str


@router.post("/queue")
def queue_episodes(items: list[QueueItem], db: Session = Depends(get_db)):
    """One durable job per episode; all items are validated (rights, channel) before any is queued."""
    for it in items:
        try:
            it.rights.validate_for_acquisition()
            channel_store.get(it.channel_id)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=422, detail=f"{it.title}: {e}")
    queued = []
    for it in items:
        ws = WORKSPACE_ROOT / f"{ingest_mod.slugify(it.title)}_{uuid.uuid4().hex[:6]}"
        spec = ReviewJobSpec(source=it.source, title=it.title, rights=it.rights, channel_id=it.channel_id, workspace=str(ws))
        project_id, job_id = enqueue_review(db, spec)
        queued.append({"title": it.title, "project_id": project_id, "job_id": job_id, "workspace": str(ws)})
    return queued


@router.get("/jobs")
def list_review_jobs(limit: int = 50):
    return [j for j in job_manager.list_all_jobs(limit=200) if j["job_type"] == JOB_TYPE][:limit]
