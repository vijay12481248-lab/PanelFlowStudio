from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.database.models import (
    ProjectRecord,
    PageRecord,
    AudioTimelineRecord,
    VisualTimelineRecord,
    RenderJobRecord,
)
from engine.projects.service import project_service, reconcile_story_editor_state_with_panels
from engine.acquisition.adapters.registry import get_default_registry
from engine.api.schemas import (
    ProjectCreateRequest,
    ProjectResponse,
    JobResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])
adapter_registry = get_default_registry()

def format_project_response(p: ProjectRecord, db: Session) -> ProjectResponse:
    total_pages = db.query(PageRecord).filter(PageRecord.project_id == p.id).count()
    ready_pages = db.query(PageRecord).filter(PageRecord.project_id == p.id, PageRecord.status == "READY").count()
    failed_pages = db.query(PageRecord).filter(PageRecord.project_id == p.id, PageRecord.status == "FAILED").count()

    stale_stages = []
    audio_rec = (
        db.query(AudioTimelineRecord)
        .filter(AudioTimelineRecord.project_id == p.id)
        .order_by(AudioTimelineRecord.created_at.desc())
        .first()
    )
    if audio_rec and audio_rec.status == "STALE":
        stale_stages.append("audio")

    motion_rec = (
        db.query(VisualTimelineRecord)
        .filter(VisualTimelineRecord.project_id == p.id)
        .order_by(VisualTimelineRecord.created_at.desc())
        .first()
    )
    if motion_rec and motion_rec.status == "STALE":
        stale_stages.append("motion")

    has_stale_render = (
        db.query(RenderJobRecord)
        .filter(RenderJobRecord.project_id == p.id, RenderJobRecord.status == "STALE")
        .first()
    )
    if has_stale_render or (("audio" in stale_stages or "motion" in stale_stages) and db.query(RenderJobRecord).filter(RenderJobRecord.project_id == p.id).count() > 0):
        stale_stages.append("render")

    return ProjectResponse(
        id=p.id,
        title=p.title,
        source_type=p.source_type,
        source_url=p.source_url,
        source_metadata=p.source_metadata or {},
        rights_status=p.rights_status,
        license_info=p.license_info,
        workspace_path=p.workspace_path,
        current_stage=p.current_stage,
        settings=p.settings or {},
        created_at=p.created_at.isoformat() if p.created_at else "",
        updated_at=p.updated_at.isoformat() if p.updated_at else "",
        total_pages=total_pages,
        ready_pages=ready_pages,
        failed_pages=failed_pages,
        stale_stages=stale_stages,
    )

@router.get("", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    projects = project_service.list_projects(db)
    return [format_project_response(p, db) for p in projects]

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(req: ProjectCreateRequest, db: Session = Depends(get_db)):
    try:
        p = project_service.create_project(
            db=db,
            title=req.title,
            source_type=req.source_type,
            rights_status=req.rights_status,
            source_url=req.source_url,
            source_metadata=req.source_metadata,
            license_info=req.license_info,
            project_settings=req.settings,
        )
        return format_project_response(p, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    p = project_service.get_project(db, project_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return format_project_response(p, db)


@router.get("/{project_id}/story-editor")
def get_story_editor_state(project_id: str, db: Session = Depends(get_db)):
    """Return the persisted Story Editor state for a project, when one exists."""
    p = project_service.get_project(db, project_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    state = reconcile_story_editor_state_with_panels(
        db,
        project_id,
        (p.settings or {}).get("story_editor_state"),
    )
    return {"state": state}


@router.put("/{project_id}/story-editor")
def save_story_editor_state(project_id: str, payload: dict, db: Session = Depends(get_db)):
    """Persist the complete Story Editor state in the project's settings JSON."""
    p = project_service.get_project(db, project_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="state must be an object")
    if state.get("project_id") not in (None, project_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="state project_id does not match the requested project")
    settings = dict(p.settings or {})
    if payload.get("align_panels"):
        from engine.projects.service import align_panel_scenes
        try:
            state = align_panel_scenes(db, project_id, state)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error))
    state = reconcile_story_editor_state_with_panels(db, project_id, state) or state
    settings["story_editor_state"] = {**state, "project_id": project_id}
    p.settings = settings
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"state": settings["story_editor_state"], "updated_at": p.updated_at.isoformat() if p.updated_at else ""}

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    deleted = project_service.delete_project(db, project_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return None

@router.post("/{project_id}/acquire")
def start_acquisition(project_id: str, db: Session = Depends(get_db)):
    try:
        job_id = project_service.start_acquisition_job(db, project_id, adapter_registry)
        return {"job_id": job_id, "message": "Acquisition job started"}
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/{project_id}/retry")
def retry_failed_pages(project_id: str, db: Session = Depends(get_db)):
    try:
        job_id = project_service.retry_failed_pages(db, project_id, adapter_registry)
        return {"job_id": job_id, "message": "Retry job started"}
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{project_id}/confirm", response_model=ProjectResponse)
def confirm_acquisition(project_id: str, db: Session = Depends(get_db)):
    try:
        p = project_service.confirm_acquisition(db, project_id)
        return format_project_response(p, db)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/{project_id}/manifest")
def get_manifest(project_id: str, db: Session = Depends(get_db)):
    try:
        manifest = project_service.sync_manifest_with_db(db, project_id)
        return manifest.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
