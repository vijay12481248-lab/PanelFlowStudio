from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.database.models import OCRRecord, TextRegionRecord
from engine.projects.service import project_service
from engine.ocr.providers.registry import get_default_ocr_registry
from engine.api.schemas import (
    OCREngineInfo,
    OCRExtractRequest,
    AdaptedBlockUpdateRequest,
    OCRResponse,
    TextRegionCreateRequest,
    TextRegionUpdateRequest,
    TextRegionResponse,
)

router = APIRouter(prefix="/api", tags=["ocr"])
ocr_registry = get_default_ocr_registry()


def format_ocr_response(r: OCRRecord) -> OCRResponse:
    return OCRResponse(
        id=r.id,
        project_id=r.project_id,
        panel_id=r.panel_id,
        engine_name=r.engine_name,
        engine_version=r.engine_version,
        raw_blocks=r.raw_blocks or [],
        adapted_blocks=r.adapted_blocks or [],
        full_text=r.full_text or "",
        confidence_avg=r.confidence_avg,
        status=r.status,
    )


def format_text_region_response(tr: TextRegionRecord) -> TextRegionResponse:
    return TextRegionResponse(
        id=tr.id,
        project_id=tr.project_id,
        page_id=tr.page_id,
        panel_id=tr.panel_id,
        sequence_in_panel=tr.sequence_in_panel,
        sequence_global=tr.sequence_global,
        x=tr.x,
        y=tr.y,
        width=tr.width,
        height=tr.height,
        normalized_x=tr.normalized_x,
        normalized_y=tr.normalized_y,
        normalized_width=tr.normalized_width,
        normalized_height=tr.normalized_height,
        page_x=tr.page_x,
        page_y=tr.page_y,
        page_width=tr.page_width,
        page_height=tr.page_height,
        region_type=tr.region_type,
        confidence=tr.confidence,
        status=tr.status,
        detection_method=tr.detection_method,
        crop_filename=tr.crop_filename,
        crop_sha256=tr.crop_sha256,
        raw_text=tr.raw_text,
        raw_confidence=tr.raw_confidence,
        raw_polygon=tr.raw_polygon or [],
        ocr_engine=tr.ocr_engine,
        ocr_engine_version=tr.ocr_engine_version,
        corrected_text=tr.corrected_text,
        corrected_by=tr.corrected_by,
        correction_status=tr.correction_status,
        speaker_character_id=tr.speaker_character_id,
        speaker_confidence=tr.speaker_confidence,
        speaker_assignment_method=tr.speaker_assignment_method,
        image_url=f"/api/projects/{tr.project_id}/text-regions/{tr.id}/file" if tr.crop_filename else "",
    )


# -------------------------------------------------------------
# OCR Engines
# -------------------------------------------------------------
@router.get("/ocr/engines", response_model=list[OCREngineInfo])
def list_ocr_engines():
    return ocr_registry.list_engines()


# -------------------------------------------------------------
# Text Region Detection & CRUD (Parts 5, 6, 7, 8, 13)
# -------------------------------------------------------------
@router.post("/projects/{project_id}/detect-text-regions", response_model=list[TextRegionResponse])
def detect_text_regions(
    project_id: str,
    page_id: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        created = project_service.detect_text_regions_project(db, project_id, page_id=page_id)
        return [format_text_region_response(r) for r in created]
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/projects/{project_id}/text-regions", response_model=list[TextRegionResponse])
def list_text_regions(
    project_id: str,
    page_id: str | None = None,
    panel_id: str | None = None,
    db: Session = Depends(get_db),
):
    records = project_service.list_text_regions(db, project_id, page_id=page_id, panel_id=panel_id)
    return [format_text_region_response(r) for r in records]


@router.post("/projects/{project_id}/panels/{panel_id}/text-regions", response_model=TextRegionResponse, status_code=status.HTTP_201_CREATED)
def create_manual_text_region(
    project_id: str,
    panel_id: str,
    req: TextRegionCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        tr = project_service.create_manual_text_region(
            db=db,
            project_id=project_id,
            panel_id=panel_id,
            x=req.x,
            y=req.y,
            width=req.width,
            height=req.height,
            region_type=req.region_type,
        )
        return format_text_region_response(tr)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/projects/{project_id}/text-regions/{region_id}", response_model=TextRegionResponse)
def update_text_region(
    project_id: str,
    region_id: str,
    req: TextRegionUpdateRequest,
    db: Session = Depends(get_db),
):
    try:
        updated = project_service.update_text_region(
            db=db,
            project_id=project_id,
            region_id=region_id,
            x=req.x,
            y=req.y,
            width=req.width,
            height=req.height,
            region_type=req.region_type,
            status=req.status,
            corrected_text=req.corrected_text,
            corrected_by=req.corrected_by,
            correction_status=req.correction_status,
            speaker_character_id=req.speaker_character_id,
            speaker_confidence=req.speaker_confidence,
            speaker_assignment_method=req.speaker_assignment_method,
        )
        return format_text_region_response(updated)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/projects/{project_id}/text-regions/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_text_region(
    project_id: str,
    region_id: str,
    db: Session = Depends(get_db),
):
    try:
        project_service.delete_text_region(db, project_id, region_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/projects/{project_id}/text-regions/{region_id}/file")
def get_text_region_file(
    project_id: str,
    region_id: str,
    db: Session = Depends(get_db),
):
    tr = project_service.get_text_region(db, project_id, region_id)
    if not tr or not tr.crop_filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text region crop not found")

    proj = project_service.get_project(db, project_id)
    crop_path = Path(proj.workspace_path) / "text_regions" / tr.crop_filename
    if not crop_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crop file does not exist on disk")

    return FileResponse(crop_path, media_type="image/jpeg")


# -------------------------------------------------------------
# Granular OCR Extraction (Part 12) with Deterministic Cache (Part 9)
# -------------------------------------------------------------
@router.post("/projects/{project_id}/text-regions/{region_id}/ocr", response_model=TextRegionResponse)
def ocr_single_region(
    project_id: str,
    region_id: str,
    req: OCRExtractRequest,
    db: Session = Depends(get_db),
):
    try:
        updated = project_service.extract_ocr_region(
            db=db,
            project_id=project_id,
            region_id=region_id,
            engine_id=req.engine_id,
            language=req.language,
        )
        return format_text_region_response(updated)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/projects/{project_id}/ocr/extract")
def extract_ocr_project(
    project_id: str,
    req: OCRExtractRequest,
    db: Session = Depends(get_db),
):
    try:
        job_id = project_service.extract_ocr_project(
            db=db,
            project_id=project_id,
            engine_id=req.engine_id,
            language=req.language,
        )
        return {
            "job_id": job_id,
            "message": f"Queued OCR extraction using engine '{req.engine_id}'",
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/projects/{project_id}/ocr", response_model=list[OCRResponse])
def list_project_ocr(project_id: str, db: Session = Depends(get_db)):
    records = project_service.list_project_ocr(db, project_id)
    return [format_ocr_response(r) for r in records]


@router.get("/projects/{project_id}/panels/{panel_id}/ocr", response_model=OCRResponse)
def get_panel_ocr(project_id: str, panel_id: str, db: Session = Depends(get_db)):
    rec = project_service.get_panel_ocr(db, project_id, panel_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No OCR record found for panel {panel_id}",
        )
    return format_ocr_response(rec)


@router.put("/projects/{project_id}/panels/{panel_id}/ocr/blocks/{block_id}", response_model=OCRResponse)
def update_adapted_block(
    project_id: str,
    panel_id: str,
    block_id: str,
    req: AdaptedBlockUpdateRequest,
    db: Session = Depends(get_db),
):
    try:
        updated = project_service.update_adapted_block(
            db=db,
            project_id=project_id,
            panel_id=panel_id,
            block_id=block_id,
            speaker=req.speaker,
            text=req.text,
            classification=req.classification,
            notes=req.notes,
        )
        return format_ocr_response(updated)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# -------------------------------------------------------------
# Strict OCR Approval Gate (Part 11)
# -------------------------------------------------------------
@router.post("/projects/{project_id}/ocr/confirm")
def confirm_ocr(project_id: str, db: Session = Depends(get_db)):
    try:
        proj = project_service.confirm_ocr(db, project_id)
        return {
            "project_id": proj.id,
            "current_stage": proj.current_stage,
            "message": "OCR approved successfully.",
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -------------------------------------------------------------
# Canonical M4 Export Contract (Part 14)
# -------------------------------------------------------------
@router.get("/projects/{project_id}/export/contract")
def get_canonical_export_contract(project_id: str, db: Session = Depends(get_db)):
    try:
        return project_service.get_canonical_export(db, project_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
