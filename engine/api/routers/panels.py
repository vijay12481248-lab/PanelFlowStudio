from pathlib import Path
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.database.models import PanelRecord, PageRecord, ProjectRecord
from engine.projects.service import project_service
from engine.security.paths import resolve_contained_path
from engine.api.schemas import (
    NormalizeProjectRequest,
    DetectPanelsRequest,
    PanelCreateRequest,
    PanelUpdateRequest,
    PanelSplitRequest,
    PanelMergeRequest,
    PanelReorderRequest,
    PanelResponse,
    BlurRegionRequest,
    BlurTextRequest,
    BlurPanelRequest,
    BlurStatusResponse,
    BatchBlurRequest,
    BatchResetRequest,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["panels"])
logger = logging.getLogger("panelflow.api.panels")


@router.get("/panels/{panel_id}/text-blur-preview")
def preview_text_blur(project_id: str, panel_id: str, region_id: str,
                      db: Session = Depends(get_db)):
    import io
    from PIL import Image
    from fastapi.responses import Response
    from engine.database.models import TextRegionRecord
    from engine.security.paths import read_contained_bytes
    from engine.imaging.redaction import preview_blur_box
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
    region = db.query(TextRegionRecord).filter(TextRegionRecord.id == region_id,
        TextRegionRecord.project_id == project_id, TextRegionRecord.panel_id == panel_id).first()
    if not project or not panel or not region:
        raise HTTPException(status_code=404, detail="Panel or text region not found")
    try:
        path = resolve_contained_path(project.workspace_path, Path("panels") / panel.crop_filename, must_be_file=True)
        with Image.open(io.BytesIO(read_contained_bytes(project.workspace_path, path))) as image:
            preview = preview_blur_box(image, region.x, region.y, region.width, region.height)
            buffer = io.BytesIO()
            preview.save(buffer, format="JPEG", quality=95)
        return Response(buffer.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except (FileNotFoundError, ValueError, OSError):
        raise HTTPException(status_code=404, detail="Panel image unavailable")


@router.get("/panel-content-suggestions")
def panel_content_suggestions(project_id: str, db: Session = Depends(get_db)):
    """Localize promotional text using existing OCR; never alter source images."""
    from engine.database.models import TextRegionRecord
    from engine.imaging.panels.classification import PROMO_PATTERNS
    if not db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    regions = db.query(TextRegionRecord).filter(
        TextRegionRecord.project_id == project_id,
        TextRegionRecord.status != "IGNORED",
    ).order_by(TextRegionRecord.sequence_global).all()
    suggestions = []
    for region in regions:
        text = region.corrected_text.strip() or region.raw_text.strip()
        match = next((pattern for pattern in PROMO_PATTERNS if pattern.search(text)), None)
        if match:
            suggestions.append({
                "region_id": region.id, "panel_id": region.panel_id,
                "page_id": region.page_id, "text": text,
                "bbox": [region.x, region.y, region.width, region.height],
                "reason": "Website, credits, or promotional wording detected in OCR",
            })
    return {"suggestions": suggestions, "regions_checked": len(regions),
            "ocr_required": not any(r.raw_text.strip() or r.corrected_text.strip() for r in regions)}

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
        polygon_json=p.polygon_json if isinstance(p.polygon_json, str) else None,
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
@router.get("/panels/{panel_id}/image")
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

    workspace = Path(str(proj.workspace_path))
    crop_name = panel.crop_filename or f"panel_{panel.sequence:04d}.jpg"
    try:
        crop_path = resolve_contained_path(workspace / "panels", str(crop_name))
    except (ValueError, OSError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Panel crop path is outside the project workspace")
    if not crop_path.is_file():
        # Fallback: dynamically extract crop from normalized or source page image
        page = db.query(PageRecord).filter(PageRecord.id == panel.page_id).first()
        if page:
            try:
                norm_path = resolve_contained_path(workspace, Path("normalized") / f"page_{page.sequence:04d}.jpg", must_be_file=True)
            except (FileNotFoundError, ValueError, OSError):
                try:
                    norm_path = resolve_contained_path(workspace, Path("source") / str(page.filename), must_be_file=True)
                except (FileNotFoundError, ValueError, OSError):
                    norm_path = None
            if norm_path is not None:
                try:
                    from PIL import Image
                    with Image.open(norm_path) as im:
                        crop_box = (
                            max(0, int(panel.x)),
                            max(0, int(panel.y)),
                            min(im.width, int(panel.x + panel.width)),
                            min(im.height, int(panel.y + panel.height)),
                        )
                        if crop_box[2] > crop_box[0] and crop_box[3] > crop_box[1]:
                            cropped = im.crop(crop_box)
                            crop_path.parent.mkdir(parents=True, exist_ok=True)
                            cropped.convert("RGB").save(crop_path, format="JPEG", quality=90)
                except Exception as ex:
                    logger.warning(f"On-the-fly panel crop extraction failed for panel {panel_id}: {ex}")

    if not crop_path.is_file():
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

    workspace = Path(str(proj.workspace_path))
    try:
        norm_path = resolve_contained_path(workspace, Path("normalized") / f"page_{page.sequence:04d}.jpg", must_be_file=True)
    except (FileNotFoundError, ValueError, OSError):
        try:
            norm_path = resolve_contained_path(workspace, Path("source") / str(page.filename), must_be_file=True)
        except (FileNotFoundError, ValueError, OSError):
            norm_path = None

    if norm_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page image not found on disk")

    return FileResponse(norm_path, media_type="image/jpeg")


@router.post("/panels/{panel_id}/blur-region")
def blur_panel_region(
    project_id: str,
    panel_id: str,
    req: BlurRegionRequest,
    db: Session = Depends(get_db),
):
    try:
        res = project_service.blur_panel_box(
            db=db,
            project_id=project_id,
            panel_id=panel_id,
            x=req.x,
            y=req.y,
            width=req.width,
            height=req.height,
            blur_radius=req.blur_radius,
            feather=req.feather,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/panels/{panel_id}/blur-text")
def blur_panel_text(
    project_id: str,
    panel_id: str,
    req: BlurTextRequest = BlurTextRequest(),
    db: Session = Depends(get_db),
):
    try:
        res = project_service.blur_panel_text(
            db=db,
            project_id=project_id,
            panel_id=panel_id,
            region_ids=req.region_ids,
            blur_radius=req.blur_radius,
            feather=req.feather,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/panels/{panel_id}/blur-panel")
def blur_entire_panel(
    project_id: str,
    panel_id: str,
    req: BlurPanelRequest = BlurPanelRequest(),
    db: Session = Depends(get_db),
):
    try:
        res = project_service.blur_entire_panel(
            db=db,
            project_id=project_id,
            panel_id=panel_id,
            blur_radius=req.blur_radius,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/panels/{panel_id}/reset-image")
def reset_panel_image(
    project_id: str,
    panel_id: str,
    db: Session = Depends(get_db),
):
    try:
        res = project_service.reset_panel_image(
            db=db,
            project_id=project_id,
            panel_id=panel_id,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/panels/{panel_id}/blur-status", response_model=BlurStatusResponse)
def get_panel_blur_status(
    project_id: str,
    panel_id: str,
    db: Session = Depends(get_db),
):
    try:
        res = project_service.get_panel_blur_status(
            db=db,
            project_id=project_id,
            panel_id=panel_id,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/panels/batch-blur")
def batch_blur_panels(
    project_id: str,
    payload: BatchBlurRequest,
    db: Session = Depends(get_db),
):
    try:
        res = project_service.batch_blur_panels(
            db=db,
            project_id=project_id,
            preset=payload.preset,
            height_px=payload.height_px,
            blur_radius=payload.blur_radius,
            feather=payload.feather,
            panel_ids=payload.panel_ids,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/panels/batch-reset")
def batch_reset_panels(
    project_id: str,
    payload: BatchResetRequest,
    db: Session = Depends(get_db),
):
    try:
        res = project_service.batch_reset_panels(
            db=db,
            project_id=project_id,
            panel_ids=payload.panel_ids,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


