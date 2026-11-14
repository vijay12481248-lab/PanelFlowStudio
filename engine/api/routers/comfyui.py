"""ComfyUI discovery and PanelFlow-owned image job endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from engine.comfyui import ComfyUIClient, ComfyUIError, ComfyWorkflowRegistry, WorkflowRegistryError
from engine.comfyui.art import ART_WORKFLOW_ID, EDIT_WORKFLOW_ID, IMAGE_WORKFLOW_IDS, ComfyImageGenerationError
from engine.comfyui.service import (
    H3_CLIP_JOB_TYPE, INPAINT_WORKFLOW_ID, edit_image_operation, generate_clip_operation, generate_image_operation,
    inpaint_image_operation, save_pose_reference, save_project_image,
)
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


class ComfyClipRequest(BaseModel):
    action: str = Field(..., min_length=10, max_length=2000, description="What changes, in plain words; the H3 prompt skeleton and the static-camera sentence are added by the engine")
    first_asset_id: str = Field(..., min_length=1, description="Project asset used as the first frame")
    last_asset_id: str | None = Field(default=None, description="Project asset used as the last frame (FL2VA); the same asset as the first frame makes a clip that loops")
    seconds: float = Field(default=2.3, ge=1.0, le=8.0, description="Snapped by H3 to its frame grid (17k+5 frames at 24 fps)")
    seed: int = Field(default=2026, ge=0, le=2**63 - 1)
    timeout_s: float = Field(default=1500.0, ge=60.0, le=3600.0)


class ComfyInpaintRequest(BaseModel):
    asset_id: str | None = None
    image_data: str | None = None
    mask_data: str = Field(..., description="Base64 encoded PNG or data URL containing the binary mask (white=inpaint, black=keep)")
    prompt: str = Field(..., min_length=1, max_length=12000)
    negative_prompt: str | None = Field(default=None, max_length=12000)
    seed: int = Field(default=20261019, ge=0, le=2**63 - 1)
    timeout_s: float = Field(default=900.0, ge=30.0, le=3600.0)


class ComfyEditRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, description="The picture to edit (in a pose transfer: the artwork whose characters and style are kept)")
    prompt: str = Field(default="", max_length=12000, description="What the picture should become, in plain words (in a pose transfer: an optional note on who plays whom)")
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=3, description="Other project assets the instruction may refer to")
    pose_asset_id: str | None = Field(default=None, description="Pose and camera transfer: a project picture whose poses, camera angle and framing the artwork should take")
    pose_image_data: str | None = Field(default=None, max_length=30_000_000, description="Pose and camera transfer: the pose picture uploaded as base64 or a data URL (stored as a project asset)")
    seed: int = Field(default=20261019, ge=0, le=2**63 - 1)
    timeout_s: float = Field(default=1800.0, ge=30.0, le=3600.0)

    @model_validator(mode="after")
    def _needs_an_instruction_or_a_pose(self):
        if self.pose_asset_id and self.pose_image_data:
            raise ValueError("Give the pose picture as pose_asset_id or pose_image_data, not both")
        if not (self.pose_asset_id or self.pose_image_data) and len(self.prompt.strip()) < 3:
            raise ValueError("prompt must say what the picture should become (at least 3 characters)")
        return self


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
        if request.workflow_id not in IMAGE_WORKFLOW_IDS:
            raise WorkflowRegistryError(f"Image workflows are {IMAGE_WORKFLOW_IDS}; got {request.workflow_id!r}")
        if request.refine and request.workflow_id != ART_WORKFLOW_ID:
            raise WorkflowRegistryError(f"refine only runs on {ART_WORKFLOW_ID!r}")
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


@project_router.post("/{project_id}/comfyui/clip")
def submit_comfyui_clip_job(project_id: str, request: ComfyClipRequest, db: Session = Depends(get_db)) -> dict:
    """Queue one MiniMax H3 clip made from project pictures (image-to-video, or first + last frame)."""
    from engine.original.h3_modes import WORKFLOWS

    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    wanted = [request.first_asset_id] + ([request.last_asset_id] if request.last_asset_id else [])
    found = {a.id for a in db.query(AssetRecord.id).filter(AssetRecord.project_id == project_id, AssetRecord.id.in_(wanted))}
    missing = [i for i in wanted if i not in found]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Assets not found in this project: {', '.join(missing)}")
    workflow_id = WORKFLOWS["fl2va" if request.last_asset_id else "i2va"]
    try:
        registry = ComfyWorkflowRegistry()
        metadata = registry.metadata(workflow_id)
        registry.load(workflow_id)
        preflight = registry.preflight(workflow_id)
        if not preflight["ready"]:
            if not preflight.get("comfy_online", True):
                raise WorkflowRegistryError("ComfyUI is offline or unreachable at 127.0.0.1:8188. Please start ComfyUI to generate clips.")
            raise WorkflowRegistryError(f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, missing models={preflight['missing_models']}")
    except (ComfyUIError, WorkflowRegistryError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    def operation(operation_db, progress, is_cancelled):
        return generate_clip_operation(operation_db, progress, is_cancelled, project_id=project_id, action=request.action, seconds=request.seconds,
                                       seed=request.seed, first_asset_id=request.first_asset_id, last_asset_id=request.last_asset_id,
                                       timeout_s=request.timeout_s)

    job_id = enqueue_project_operation(
        project_id=project_id,
        job_type=H3_CLIP_JOB_TYPE,
        operation=operation,
        priority=20,
        requires_gpu=bool(metadata.get("requires_gpu", True)),
        gpu_vram_mb=int(metadata.get("gpu_vram_mb", 0) or 0),
        max_retries=0,  # a failed render costs minutes of GPU; the caller decides whether to try again
        job_input=request.model_dump(),
    )
    return {"job_id": job_id, "status": "QUEUED", "workflow_id": workflow_id}


@project_router.post("/{project_id}/comfyui/edit")
def submit_comfyui_edit_job(project_id: str, request: ComfyEditRequest, db: Session = Depends(get_db)):
    """Queue one picture edited from a written instruction, with the MiniMax-H3-Image workflow."""
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    wanted = [request.asset_id, *request.reference_asset_ids, *([request.pose_asset_id] if request.pose_asset_id else [])]
    found = {a.id for a in db.query(AssetRecord.id).filter(AssetRecord.project_id == project_id, AssetRecord.id.in_(wanted))}
    missing = [i for i in wanted if i not in found]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Assets not found in this project: {', '.join(missing)}")

    pose_asset_id = request.pose_asset_id
    if request.pose_image_data:  # an uploaded picture becomes a project asset, so the job input stays small
        try:
            pose_asset_id = save_pose_reference(db, project_id, request.pose_image_data)
        except ComfyImageGenerationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        registry = ComfyWorkflowRegistry()
        metadata = registry.metadata(EDIT_WORKFLOW_ID)
        registry.load(EDIT_WORKFLOW_ID)
        preflight = registry.preflight(EDIT_WORKFLOW_ID)
        if not preflight["ready"]:
            if not preflight.get("comfy_online", True):
                try:
                    from engine.system.setup import comfyui_manager
                    if comfyui_manager.is_installed():
                        res = comfyui_manager.ensure_running(timeout_s=15.0)
                        if res.get("running"):
                            preflight = registry.preflight(EDIT_WORKFLOW_ID)
                except Exception:
                    pass
            if not preflight["ready"]:
                if not preflight.get("comfy_online", True):
                    raise WorkflowRegistryError("ComfyUI is offline or unreachable at 127.0.0.1:8188. Please start ComfyUI to edit images.")
                raise WorkflowRegistryError(
                    f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, missing models={preflight['missing_models']}"
                )
    except (ComfyUIError, WorkflowRegistryError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    def operation(operation_db, progress, is_cancelled):
        return edit_image_operation(
            operation_db,
            progress,
            is_cancelled,
            project_id=project_id,
            base_asset_id=request.asset_id,
            prompt=request.prompt,
            reference_asset_ids=request.reference_asset_ids,
            pose_asset_id=pose_asset_id,
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
        job_input={**request.model_dump(exclude={"pose_image_data"}), "pose_asset_id": pose_asset_id},
    )
    return {"job_id": job_id, "status": "QUEUED", "workflow_id": EDIT_WORKFLOW_ID, "pose_asset_id": pose_asset_id}


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
    return {"assets": [_asset_dict(asset) for asset in assets]}


def _asset_dict(asset: AssetRecord) -> dict:
    return {
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


class GradedImageRequest(BaseModel):
    image_data: str = Field(..., min_length=16, max_length=30_000_000, description="The graded picture as base64 or a data URL")
    source_asset_id: str = Field(..., min_length=1, description="The project picture the grade was made on")
    grade: dict = Field(default_factory=dict, description="The colour node stack that was baked in, kept as provenance")
    cut: dict = Field(default_factory=dict, description="The cut (crop, straighten, turns, flips, resize) that was baked in, kept as provenance")
    fusion: dict = Field(default_factory=dict, description="The Fusion effect stack (glow, vignette, grain, blur, text) that was baked in, kept as provenance")

    @model_validator(mode="after")
    def _says_what_was_done(self):
        if not self.grade and not self.cut and not self.fusion:
            raise ValueError("give the grade, the cut and/or the Fusion effects that were baked into the picture")
        if len(json.dumps(self.grade)) > 400_000 or len(json.dumps(self.cut)) > 20_000 or len(json.dumps(self.fusion)) > 100_000:
            raise ValueError("grade, cut or fusion is too large to keep as provenance")
        return self


@project_router.post("/{project_id}/assets/graded")
def save_graded_image(project_id: str, request: GradedImageRequest, db: Session = Depends(get_db)) -> dict:
    """Keep a picture edited by hand in the image studio (colour grade, cut and/or Fusion effects, rendered there) as a new project asset."""
    source = db.query(AssetRecord).filter(AssetRecord.id == request.source_asset_id, AssetRecord.project_id == project_id).first()
    if not db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not source:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Asset not found in this project: {request.source_asset_id}")
    try:
        # what the asset is called follows the first thing in it: grade, then cut, then effects
        role, asset_type, prefix = next(
            (r for r, on in (
                (("color_grade", "GRADED_IMAGE", "graded"), bool(request.grade)),
                (("cut", "CUT_IMAGE", "cut"), bool(request.cut)),
                (("fusion", "FUSION_IMAGE", "fusion"), bool(request.fusion)),
            ) if on),
        )
        asset = save_project_image(
            db, project_id, request.image_data, asset_type=asset_type, prefix=prefix, what="edited picture",
            provenance={
                "role": role, "source_asset_id": source.id, "source_filename": source.filename,
                **({"grade": request.grade} if request.grade else {}),
                **({"cut": request.cut} if request.cut else {}),
                **({"fusion": request.fusion} if request.fusion else {}),
            },
        )
    except ComfyImageGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _asset_dict(asset)


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
