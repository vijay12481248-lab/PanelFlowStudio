from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.database.models import PanelRecord, PageRecord, ProjectRecord
from engine.projects.service import project_service
from engine.api.schemas import (
    NormalizeProjectRequest,
    DetectPanelsRequest,
    PanelCreateRequest,
    PanelUpdateRequest,
    PanelSplitRequest,
    PanelMergeRequest,
    PanelReorderRequest,
    PanelResponse,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["panels"])

def format_panel_response(p: PanelRecord, project_id: str) -> PanelResponse:
    return PanelResponse(
        id=p.id,
        project_id=p.project_id,
        page_id=p.page_id,
        sequence=p.sequence,
        page_sequence=p.page_sequence,
        x=p.x,
        y=p.y,
        width=p.width,
        height=p.height,
        normalized_x=getattr(p, "normalized_x", 0.0),
        normalized_y=getattr(p, "normalized_y", 0.0),
        normalized_width=getattr(p, "normalized_width", 0.0),
        normalized_height=getattr(p, "normalized_height", 0.0),
        crop_filename=p.crop_filename,
        reading_direction=p.reading_direction,
        detection_method=getattr(p, "detection_method", "AUTO"),
        confidence=p.confidence,
        panel_type=getattr(p, "panel_type", "STANDARD"),
        status=p.status,
        manually_modified=getattr(p, "manually_modified", False),
        created_at=p.created_at.isoformat() if p.created_at else "",
        image_url=f"/api/projects/{project_id}/panels/{p.id}/file",
    )

@router.post("/normalize")
def normalize_project(
    project_id: str,
    req: NormalizeProjectRequest | None = None,
    db: Session = Depends(get_db),
):
    target_width = req.target_width if req else 1920
    try:
        job_id = project_service.normalize_project(db, project_id, target_width=target_width)
        return {"job_id": job_id, "message": "Normalization job queued"}
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/detect-panels")
def detect_panels(
    project_id: str,
    req: DetectPanelsRequest | None = None,
    db: Session = Depends(get_db),
):
    direction = req.reading_direction if req else "ltr"
    min_area = req.min_area_ratio if req else 0.02
    profile = req.profile if req and hasattr(req, "profile") else "AUTO"
    try:
        job_id = project_service.detect_panels_project(
            db, project_id, reading_direction=direction, min_area_ratio=min_area, profile=profile
        )
        return {"job_id": job_id, "message": "Panel detection job queued"}
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/pages/{page_id}/detect-panels", response_model=list[PanelResponse])
def detect_page_panels(
    project_id: str,
    page_id: str,
    req: DetectPanelsRequest | None = None,
    db: Session = Depends(get_db),
):
    direction = req.reading_direction if req else "ltr"
    min_area = req.min_area_ratio if req else 0.02
    profile = req.profile if req and hasattr(req, "profile") else "AUTO"
    try:
        panels = project_service.detect_panels_page(
            db, project_id, page_id, reading_direction=direction, min_area_ratio=min_area, profile=profile
        )
        return [format_panel_response(p, project_id) for p in panels]
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/panels", response_model=list[PanelResponse])
def list_panels(
    project_id: str,
    page_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    panels = project_service.list_panels(db, project_id, page_id=page_id)
    return [format_panel_response(p, project_id) for p in panels]

@router.post("/panels", response_model=PanelResponse, status_code=status.HTTP_201_CREATED)
def add_panel(
    project_id: str,
    req: PanelCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        p = project_service.add_panel(
            db, project_id, req.page_id, req.x, req.y, req.width, req.height,
            panel_type=req.panel_type or "STANDARD"
        )
        return format_panel_response(p, project_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/panels/{panel_id}", response_model=PanelResponse)
@router.patch("/panels/{panel_id}", response_model=PanelResponse)
def update_panel(
    project_id: str,
    panel_id: str,
    req: PanelUpdateRequest,
    db: Session = Depends(get_db),
):
    try:
        p = project_service.update_panel(
            db, project_id, panel_id, req.x, req.y, req.width, req.height,
            status=req.status, panel_type=req.panel_type
        )
        return format_panel_response(p, project_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/panels/{panel_id}/split", response_model=list[PanelResponse])
def split_panel(
    project_id: str,
    panel_id: str,
    req: PanelSplitRequest,
    db: Session = Depends(get_db),
):
    try:
        updated = project_service.split_panel(
            db, project_id, panel_id, split_type=req.split_type, ratio=req.ratio
        )
        return [format_panel_response(p, project_id) for p in updated]
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/panels/merge", response_model=PanelResponse)
def merge_panels(
    project_id: str,
    req: PanelMergeRequest,
    db: Session = Depends(get_db),
):
    try:
        merged = project_service.merge_panels(db, project_id, req.panel_ids)
        return format_panel_response(merged, project_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/panels/{panel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_panel(
    project_id: str,
    panel_id: str,
    db: Session = Depends(get_db),
):
    try:
        project_service.delete_panel(db, project_id, panel_id)
        return None
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.post("/panels/reorder", response_model=list[PanelResponse])
@router.post("/panel-order", response_model=list[PanelResponse])
def reorder_panels(
    project_id: str,
    req: PanelReorderRequest,
    db: Session = Depends(get_db),
):
    try:
        updated = project_service.reorder_panels(db, project_id, req.panel_ids)
        return [format_panel_response(p, project_id) for p in updated]
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/panels/confirm")
@router.post("/confirm-panels")
def confirm_panels(
    project_id: str,
    db: Session = Depends(get_db),
):
    try:
        proj = project_service.confirm_panels(db, project_id)
        return {"current_stage": proj.current_stage, "message": "Panels confirmed"}
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/panels/{panel_id}/file")
def get_panel_crop_file(
    project_id: str,
    panel_id: str,
    db: Session = Depends(get_db),
):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
    if not panel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panel not found")

    crop_path = Path(proj.workspace_path) / "panels" / panel.crop_filename
    if not crop_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panel crop file not found on disk")

    return FileResponse(crop_path, media_type="image/jpeg")

@router.get("/pages/{page_id}/normalized-file")
@router.get("/pages/{page_id}/normalized")
def get_normalized_page_file(
    project_id: str,
    page_id: str,
    db: Session = Depends(get_db),
):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    page = db.query(PageRecord).filter(PageRecord.id == page_id, PageRecord.project_id == project_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    norm_path = Path(proj.workspace_path) / "normalized" / f"page_{page.sequence:04d}.jpg"
    if not norm_path.exists():
        norm_path = Path(proj.workspace_path) / "source" / page.filename

    if not norm_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page image not found on disk")

    return FileResponse(norm_path, media_type="image/jpeg")
