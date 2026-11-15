import re
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.database.models import PageRecord
from engine.projects.service import project_service
from engine.security.paths import contained_file_response, project_path
from engine.api.schemas import (
    PageResponse,
    PageReorderRequest,
    PageRotateRequest,
)

router = APIRouter(prefix="/api/projects/{project_id}/pages", tags=["pages"])

def format_page_response(page: PageRecord, project_id: str) -> PageResponse:
    return PageResponse(
        id=page.id,
        project_id=page.project_id,
        sequence=page.sequence,
        filename=page.filename,
        source_url=page.source_url,
        content_type=page.content_type,
        width=page.width,
        height=page.height,
        byte_size=page.byte_size,
        sha256=page.sha256,
        status=page.status,
        error_message=page.error_message,
        downloaded_at=page.downloaded_at.isoformat() if page.downloaded_at else "",
        image_url=f"/api/projects/{project_id}/pages/{page.id}/file",
    )

@router.get("", response_model=list[PageResponse])
def list_pages(project_id: str, db: Session = Depends(get_db)):
    pages = (
        db.query(PageRecord)
        .filter(PageRecord.project_id == project_id)
        .order_by(PageRecord.sequence.asc())
        .all()
    )
    return [format_page_response(p, project_id) for p in pages]

@router.post("/reorder", response_model=list[PageResponse])
def reorder_pages(project_id: str, req: PageReorderRequest, db: Session = Depends(get_db)):
    try:
        updated = project_service.reorder_pages(db, project_id, req.page_ids)
        return [format_page_response(p, project_id) for p in updated]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(project_id: str, page_id: str, db: Session = Depends(get_db)):
    try:
        project_service.delete_page(db, project_id, page_id)
        return None
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{page_id}/rotate", response_model=PageResponse)
def rotate_page(project_id: str, page_id: str, req: PageRotateRequest, db: Session = Depends(get_db)):
    try:
        page = project_service.rotate_page(db, project_id, page_id, req.degrees)
        return format_page_response(page, project_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

def ensure_page_source_file(project, page) -> Path | None:
    """Ensure the page file exists in workspace_path/source/page.filename.
    If missing, recovers it from page.source_url or output directories.
    """
    try:
        if not project or not project.workspace_path:
            return None
        source_dir = Path(project.workspace_path) / "source"
        target = source_dir / page.filename
        if target.is_file():
            return target

        # 1. Check if page.source_url is a file on disk
        if page.source_url:
            src_candidate = Path(page.source_url)
            if src_candidate.is_file():
                source_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_candidate, target)
                return target

        # 2. Check output directory for matching raw chapter slices
        cand_names = [
            page.filename,
            f"slice_{page.sequence:04d}.webp",
            f"slice_{page.sequence:04d}.jpg",
            f"slice_{page.sequence:04d}.png",
            f"page_{page.sequence:04d}.webp",
            f"page_{page.sequence:04d}.jpg",
        ]
        ch_match = re.search(r"chapter\s*(\d+)", project.title or "", re.IGNORECASE)
        ch_num = ch_match.group(1) if ch_match else None

        output_dir = Path("output")
        if output_dir.exists():
            if ch_num:
                for ch_dir in output_dir.rglob(f"chapter_{ch_num}"):
                    if ch_dir.is_dir():
                        for cname in cand_names:
                            cand_file = ch_dir / cname
                            if cand_file.is_file():
                                source_dir.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(cand_file, target)
                                return target

            for cname in cand_names:
                for found in output_dir.rglob(cname):
                    if found.is_file():
                        source_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(found, target)
                        return target
        return None
    except Exception:
        return None


@router.get("/{page_id}/file")
def get_page_image_file(project_id: str, page_id: str, db: Session = Depends(get_db)):
    project = project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    page = db.query(PageRecord).filter(PageRecord.id == page_id, PageRecord.project_id == project_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    # Recover source file if missing from disk
    ensure_page_source_file(project, page)

    try:
        file_path = project_path(project.workspace_path, "source", page.filename)
        return contained_file_response(project.workspace_path, file_path, media_type=page.content_type)
    except (ValueError, FileNotFoundError, OSError):
        # Fallback to normalized if source is unavailable
        try:
            norm_seq = project_path(project.workspace_path, "normalized", f"page_{page.sequence:04d}.jpg")
            if norm_seq.is_file():
                return contained_file_response(project.workspace_path, norm_seq, media_type="image/jpeg")
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found on disk")

@router.get("/{page_id}/normalized-file")
@router.get("/{page_id}/normalized")
def get_normalized_page_file(project_id: str, page_id: str, db: Session = Depends(get_db)):
    project = project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    page = db.query(PageRecord).filter(PageRecord.id == page_id, PageRecord.project_id == project_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    # Serve from normalized/ if available, otherwise fallback to source/
    try:
        norm_seq = project_path(project.workspace_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if norm_seq.is_file():
            return contained_file_response(project.workspace_path, norm_seq, media_type="image/jpeg")
        norm_path = project_path(project.workspace_path, "normalized", page.filename)
        if norm_path.is_file():
            return contained_file_response(project.workspace_path, norm_path, media_type="image/jpeg")
        source_path = project_path(project.workspace_path, "source", page.filename)
        return contained_file_response(project.workspace_path, source_path, media_type=page.content_type)
    except (ValueError, FileNotFoundError, OSError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found on disk")

