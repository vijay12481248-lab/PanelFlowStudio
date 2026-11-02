"""Anime Review workflow endpoints (docs/ANIME_REVIEW.md). Every entry point goes through the rights gate."""
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.acquisition.rights.models import RightsDeclaration
from engine.anime.review import analysis, ingest as ingest_mod
from engine.anime.review.models import EpisodeAnalysis, IngestRecord

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
