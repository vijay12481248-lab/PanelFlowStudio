"""FastAPI router for YouTube packaging and thumbnail research."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.models import ProjectRecord
from engine.database.session import get_db
from engine.security.paths import resolve_contained_path
from engine.story.packaging import (
    YouTubePackagingData,
    generate_youtube_packaging,
)

router = APIRouter(prefix="/api/projects", tags=["youtube-packaging"])


class PackagingGenerateRequest(BaseModel):
    profile_name: Optional[str] = None
    focus_character: Optional[str] = None
    style_tone: str = Field(default="dramatic", pattern=r"^(dramatic|action|mysterious|hype|emotional)$")
    custom_hook: Optional[str] = None


@router.get("/{project_id}/youtube/packaging", response_model=YouTubePackagingData)
async def get_youtube_packaging(
    project_id: str,
    refresh: bool = Query(default=False),
    profile_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> YouTubePackagingData:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    workspace = Path(str(project.workspace_path))
    cached_file = workspace / "generated" / "youtube_packaging.json"

    if not refresh and cached_file.is_file():
        try:
            target = resolve_contained_path(workspace, Path("generated") / "youtube_packaging.json", must_be_file=True)
            data = json.loads(target.read_text(encoding="utf-8"))
            return YouTubePackagingData.model_validate(data)
        except Exception:
            pass

    try:
        return await generate_youtube_packaging(db, project_id, profile_name=profile_name)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{project_id}/youtube/packaging/generate", response_model=YouTubePackagingData)
async def generate_packaging_endpoint(
    project_id: str,
    request: PackagingGenerateRequest,
    db: Session = Depends(get_db),
) -> YouTubePackagingData:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        return await generate_youtube_packaging(
            db,
            project_id=project_id,
            profile_name=request.profile_name,
            focus_character=request.focus_character,
            style_tone=request.style_tone,
            custom_hook=request.custom_hook,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
