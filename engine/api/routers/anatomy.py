"""Anatomy review knowledge (docs/ANATOMY_REVIEW.md): how often each image model draws wrong bodies, and the owner's "the system missed this" flags."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.original.anatomy import store

router = APIRouter(prefix="/api/original/anatomy", tags=["anatomy"])


class FlagRequest(BaseModel):
    picture: str = Field(min_length=1, max_length=500)
    model: str = Field(default="flux2_klein_4b", max_length=100)
    note: str = Field(min_length=1, max_length=2000)


@router.get("/stats")
def anatomy_stats() -> dict:
    """Pictures checked, defect rate by model and kind, rate with lessons off and on, redraws, and the owner's flags."""
    return store.stats(store.checks_path())


@router.post("/flag")
def flag_missed_mistake(req: FlagRequest) -> dict:
    """The owner says a picture had a mistake the reviewer missed; it joins the labelled set and counts against the judges."""
    try:
        store.flag_missed(store.checks_path(), picture=req.picture, model=req.model, note=req.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
