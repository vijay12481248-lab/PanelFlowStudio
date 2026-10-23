"""Project-contained, immutable custom background images for the scene renderer."""
from io import BytesIO
from pathlib import Path
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from engine.database.models import ProjectRecord
from engine.database.session import get_db
from engine.security.paths import contained_file_response, project_path, resolve_contained_path, write_contained_image

router = APIRouter(prefix="/api/projects/{project_id}/backgrounds", tags=["backgrounds"])
MAX_IMAGE_BYTES = 16 * 1024 * 1024


def store_background_image(workspace: Path, data: bytes) -> tuple[Path, int, int]:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Background image must be smaller than 16 MB")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"} or getattr(source, "is_animated", False):
                raise ValueError("Choose a still PNG, JPEG, or WebP image")
            if source.width * source.height > 24_000_000:
                raise ValueError("Background image must be at most 24 megapixels")
            image = ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Cannot read background image. Choose a PNG, JPEG, or WebP file") from exc
    directory = resolve_contained_path(workspace, "backgrounds")
    directory.mkdir(parents=True, exist_ok=True)
    target = project_path(workspace, "backgrounds", f"{uuid.uuid4().hex}.png")
    write_contained_image(workspace, target, image, "PNG")
    return target, image.width, image.height


def _project(db: Session, project_id: str):
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.post("")
async def upload_background(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Background image must be smaller than 16 MB")
        chunks.append(chunk)
    try:
        path, width, height = store_background_image(Path(project.workspace_path), b"".join(chunks))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"image_url": f"/api/projects/{project_id}/backgrounds/{path.name}/file", "width": width, "height": height}


@router.get("/{filename}/file")
def get_background(project_id: str, filename: str, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    if not re.fullmatch(r"[a-f0-9]{32}\.png", filename):
        raise HTTPException(404, "Background image not found")
    try:
        path = project_path(project.workspace_path, "backgrounds", filename, must_be_file=True)
        return contained_file_response(project.workspace_path, path, media_type="image/png")
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise HTTPException(404, "Background image not found; upload it again") from exc
