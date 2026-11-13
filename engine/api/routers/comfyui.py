"""ComfyUI discovery and PanelFlow-owned image job endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.comfyui import ComfyUIClient, ComfyUIError, ComfyWorkflowRegistry, WorkflowRegistryError
from engine.comfyui.art import ART_WORKFLOW_ID
from engine.comfyui.service import INPAINT_WORKFLOW_ID, generate_image_operation, inpaint_image_operation
from engine.database.models import AssetRecord, ProjectRecord
from engine.database.session import get_db
from engine.jobs.workflow import enqueue_project_operation
from engine.security.paths import contained_file_response

router = APIRouter(prefix="/api/comfyui", tags=["comfyui"])
project_router = APIRouter(prefix="/api/projects", tags=["project-assets"])


class ComfyImageRequest(BaseModel):
    workflow_id: str = Field(default=ART_WORKFLOW_ID, min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9_-]+$")
    prompt: str = Field(..., min_length=10, max_length=12000)
    negative_prompt: str | None = Field(default=None, max_length=12000)
    width: int = Field(default=768, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    seed: int = Field(default=20261019, ge=0, le=2**63 - 1)
    timeout_s: float = Field(default=900.0, ge=30.0, le=3600.0)
    refine: bool = Field(default=False, description="Review the picture, then repair or redraw it (slower: needs the local vision model); every candidate is kept")
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=4, description="Existing assets of this project the picture should match (character lock); not combinable with refine")


class ComfyInpaintRequest(BaseModel):
    asset_id: str | None = None
    image_data: str | None = None
    mask_data: str = Field(..., description="Base64 encoded PNG or data URL containing the binary mask (white=inpaint, black=keep)")
    prompt: str = Field(..., min_length=1, max_length=12000)
    negative_prompt: str | None = Field(default=None, max_length=12000)
    seed: int = Field(default=20261019, ge=0, le=2**63 - 1)
    timeout_s: float = Field(default=900.0, ge=30.0, le=3600.0)


@router.get("/capabilities")
def get_comfyui_capabilities() -> dict:
    """Return server health plus installed, discoverable capability metadata."""
    try:
        return ComfyUIClient().capabilities()
    except ComfyUIError as exc:
        return {"available": False, "endpoint": None, "workflow_dir": None, "workflow_files": [], "models": {}, "errors": [str(exc)]}


@router.get("/workflows")
def list_comfyui_workflows() -> dict:
    """List workflow JSON files without executing arbitrary workflow content."""
    try:
        client = ComfyUIClient()
    except ComfyUIError as exc:
        return {"workflow_dir": None, "workflows": [], "errors": [str(exc)]}
    return {
        "workflow_dir": str(client._workflow_root()) if client._workflow_root() else None,
        "workflows": client.discover_workflows(),
        "errors": [],
    }


@router.get("/workflow-registry")
def list_approved_workflows() -> dict:
    try:
        registry = ComfyWorkflowRegistry()
        return {"workflows": registry.list(), "errors": []}
    except (ComfyUIError, WorkflowRegistryError) as exc:
        return {"workflows": [], "errors": [str(exc)]}


@project_router.post("/{project_id}/comfyui/image")
def submit_comfyui_image_job(project_id: str, request: ComfyImageRequest, db: Session = Depends(get_db)) -> dict:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if request.reference_asset_ids:
        if request.refine:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="refine does not support reference images; use one or the other")
        found = {a.id for a in db.query(AssetRecord.id).filter(AssetRecord.project_id == project_id, AssetRecord.id.in_(request.reference_asset_ids))}
        missing = [i for i in request.reference_asset_ids if i not in found]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Reference assets not found in this project: {', '.join(missing)}")
    try:
        if request.workflow_id != ART_WORKFLOW_ID:
            raise WorkflowRegistryError(f"The only image workflow is {ART_WORKFLOW_ID!r}; got {request.workflow_id!r}")
        registry = ComfyWorkflowRegistry()
        metadata = registry.metadata(request.workflow_id)
        registry.load(request.workflow_id)
        preflight = registry.preflight(request.workflow_id)
        if not preflight["ready"]:
            if not preflight.get("comfy_online", True):
                try:
                    from engine.system.setup import comfyui_manager
                    if comfyui_manager.is_installed():
                        res = comfyui_manager.ensure_running(timeout_s=15.0)
                        if res.get("running"):
                            preflight = registry.preflight(request.workflow_id)
                except Exception:
                    pass
            if not preflight["ready"]:
                if not preflight.get("comfy_online", True):
                    raise WorkflowRegistryError("ComfyUI is offline or unreachable at 127.0.0.1:8188. Please start ComfyUI to generate images.")
                raise WorkflowRegistryError(
                    f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, missing models={preflight['missing_models']}"
                )
    except (ComfyUIError, WorkflowRegistryError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    def operation(operation_db, progress, is_cancelled):
        return generate_image_operation(
            operation_db,
            progress,
            is_cancelled,
            project_id=project_id,
            workflow_id=request.workflow_id,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            seed=request.seed,
            timeout_s=request.timeout_s,
            refine=request.refine,
            reference_asset_ids=request.reference_asset_ids,
        )

    job_id = enqueue_project_operation(
        project_id=project_id,
        job_type="COMFYUI_IMAGE_GENERATION",
        operation=operation,
        priority=20,
        requires_gpu=bool(metadata.get("requires_gpu", True)),
        gpu_vram_mb=int(metadata.get("gpu_vram_mb", 0) or 0),
        max_retries=1,
        job_input={
            "workflow_id": request.workflow_id,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "seed": request.seed,
            "timeout_s": request.timeout_s,
            "refine": request.refine,
            "reference_asset_ids": request.reference_asset_ids,
        },
    )
    return {"job_id": job_id, "status": "QUEUED", "workflow_id": request.workflow_id}


@project_router.post("/{project_id}/comfyui/inpaint")
def submit_comfyui_inpaint_job(project_id: str, request: ComfyInpaintRequest, db: Session = Depends(get_db)) -> dict:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not request.asset_id and not request.image_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either asset_id or image_data is required")

    try:
        registry = ComfyWorkflowRegistry()
        metadata = registry.metadata(INPAINT_WORKFLOW_ID)
        registry.load(INPAINT_WORKFLOW_ID)
        preflight = registry.preflight(INPAINT_WORKFLOW_ID)
        if not preflight["ready"]:
            if not preflight.get("comfy_online", True):
                try:
                    from engine.system.setup import comfyui_manager
                    if comfyui_manager.is_installed():
                        res = comfyui_manager.ensure_running(timeout_s=15.0)
                        if res.get("running"):
                            preflight = registry.preflight(INPAINT_WORKFLOW_ID)
                except Exception:
                    pass
            if not preflight["ready"]:
                if not preflight.get("comfy_online", True):
                    raise WorkflowRegistryError("ComfyUI is offline or unreachable at 127.0.0.1:8188. Please start ComfyUI to inpaint images.")
                raise WorkflowRegistryError(
                    f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, missing models={preflight['missing_models']}"
                )
    except (ComfyUIError, WorkflowRegistryError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    def operation(operation_db, progress, is_cancelled):
        return inpaint_image_operation(
            operation_db,
            progress,
            is_cancelled,
            project_id=project_id,
            base_asset_id=request.asset_id,
            image_data=request.image_data,
            mask_data=request.mask_data,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            timeout_s=request.timeout_s,
        )

    job_id = enqueue_project_operation(
        project_id=project_id,
        job_type="COMFYUI_IMAGE_GENERATION",
        operation=operation,
        priority=20,
        requires_gpu=bool(metadata.get("requires_gpu", True)),
        gpu_vram_mb=int(metadata.get("gpu_vram_mb", 0) or 0),
        max_retries=1,
        job_input={
            "operation": "inpaint",
            "workflow_id": INPAINT_WORKFLOW_ID,
            "base_asset_id": request.asset_id,
            "mask_data": request.mask_data,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "seed": request.seed,
            "timeout_s": request.timeout_s,
        },
    )
    return {"job_id": job_id, "status": "QUEUED", "workflow_id": INPAINT_WORKFLOW_ID}


@project_router.get("/{project_id}/assets")
def list_project_assets(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    assets = (
        db.query(AssetRecord)
        .filter(AssetRecord.project_id == project_id)
        .order_by(AssetRecord.created_at.desc())
        .all()
    )
    return {
        "assets": [
            {
                "id": asset.id,
                "asset_type": asset.asset_type,
                "filename": asset.filename,
                "relative_path": asset.relative_path,
                "content_type": asset.content_type,
                "width": asset.width,
                "height": asset.height,
                "byte_size": asset.byte_size,
                "sha256": asset.sha256,
                "status": asset.status,
                "provenance": asset.provenance or {},
                "created_at": asset.created_at.isoformat() if asset.created_at else None,
            }
            for asset in assets
        ]
    }


@project_router.get("/{project_id}/assets/{asset_id}/file")
def get_project_asset_file(project_id: str, asset_id: str, db: Session = Depends(get_db)):
    asset = (
        db.query(AssetRecord)
        .filter(AssetRecord.id == asset_id, AssetRecord.project_id == project_id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        return contained_file_response(
            Path(str(project.workspace_path)),
            str(asset.relative_path),
            media_type=str(asset.content_type or "application/octet-stream"),
            filename=str(asset.filename),
        )
    except (FileNotFoundError, ValueError, OSError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset file is unavailable")
