"""PanelFlow-owned ComfyUI image generation operation."""

from __future__ import annotations

import hashlib
import time
import uuid
import base64
import io
from pathlib import Path
from typing import Any
from PIL import Image

from sqlalchemy.orm import Session

from engine.comfyui import ComfyUIClient, ComfyUIError, ComfyWorkflowRegistry, WorkflowRegistryError
from engine.comfyui.art import (  # noqa: F401  (re-exported: callers and tests import these names from here)
    ART_WORKFLOW_ID,
    ArtEngine,
    ComfyImageGenerationError,
    _history_images,
    _patch_workflow,
    _validate_output_dimensions,
)
from engine.database.models import AssetRecord, ProjectRecord
from engine.jobs.workflow import register_operation_factory
from engine.security.paths import open_contained_output, resolve_contained_path


def _history_videos(history: dict[str, Any], prompt_id: str) -> list[dict[str, str]]:
    record = history.get(prompt_id, history)
    outputs = record.get("outputs", {}) if isinstance(record, dict) else {}
    videos: list[dict[str, str]] = []
    for output in outputs.values() if isinstance(outputs, dict) else []:
        items: list[Any] = []
        if isinstance(output, dict):
            for key in ("videos", "images", "gifs"):
                val = output.get(key)
                if isinstance(val, list):
                    items.extend(val)
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("filename"), str):
                fn = item["filename"]
                if fn.lower().endswith((".mp4", ".webm", ".mov", ".mkv")):
                    videos.append({
                        "filename": fn,
                        "subfolder": str(item.get("subfolder", "")),
                        "type": str(item.get("type", "output")),
                    })
    return videos


def _write_project_image(workspace: Path, relative_path: Path | str, raw: bytes) -> Path:
    """Exclusively create an image through a held, verified parent directory."""
    target = resolve_contained_path(workspace, relative_path)
    try:
        with open_contained_output(workspace, relative_path, exclusive=True) as output_file:
            output_file.write(raw)
    except FileExistsError as exc:
        raise ComfyImageGenerationError("Generated asset target already exists") from exc
    return target


def generate_image_operation(
    db: Session,
    progress,
    is_cancelled,
    *,
    project_id: str,
    workflow_id: str,
    prompt: str,
    negative_prompt: str | None,
    width: int,
    height: int,
    seed: int,
    timeout_s: float = 900.0,
    refine: bool = False,
    reference_asset_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Generate one image with the central ArtEngine and persist it as a project asset.

    refine=True runs the review -> plan -> repair/redraw loop (engine/original/refine.py) and keeps every candidate under generated/comfyui_candidates/;
    the stored image is the selected one and its provenance lists the iterations. Default off: behaviour is unchanged."""
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise ComfyImageGenerationError("Project not found")
    if workflow_id != ART_WORKFLOW_ID:
        raise ComfyImageGenerationError(f"The only image workflow is {ART_WORKFLOW_ID!r}; got {workflow_id!r}")
    workspace = Path(str(project.workspace_path))
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ComfyImageGenerationError("ComfyUI output directory is not a safe directory")

    references: list[Path] = []
    for ref_id in reference_asset_ids or []:
        ref_asset = db.query(AssetRecord).filter(AssetRecord.id == ref_id, AssetRecord.project_id == project_id).first()
        if ref_asset is None:
            raise ComfyImageGenerationError(f"Reference asset {ref_id} not found in this project")
        ref_path = resolve_contained_path(workspace, ref_asset.relative_path)
        if not ref_path.is_file():
            raise ComfyImageGenerationError(f"Reference asset {ref_id} has no file on disk")
        references.append(ref_path)
    if references and refine:
        raise ComfyImageGenerationError("refine does not support reference images; use one or the other")

    client = ComfyUIClient()
    refined = None
    try:
        if refine:
            from engine.original.refine import refine_art_image

            art, refined = refine_art_image(prompt, negative_prompt, width, height, seed, ws=workspace / "generated" / "comfyui_candidates",
                                            key=f"{project_id}_{uuid.uuid4().hex[:8]}", client=client, timeout=timeout_s, is_cancelled=is_cancelled)
        else:
            art = ArtEngine(client, ComfyWorkflowRegistry(client)).generate(
                prompt, negative_prompt, width, height, seed, f"panelflow/{project_id}/{ART_WORKFLOW_ID}",
                reference_images=references or None,
                timeout=timeout_s, is_cancelled=is_cancelled, progress=progress, client_id=f"panelflow-{project_id}",
            )
    except (ComfyUIError, WorkflowRegistryError, ValueError) as exc:
        raise ComfyImageGenerationError(str(exc)) from exc

    raw = art.png
    asset_id = str(uuid.uuid4())
    suffix = Path(art.source_output["filename"]).suffix.lower() or ".png"
    filename = f"{asset_id}{suffix}"
    target = _write_project_image(workspace, Path("generated") / "comfyui" / filename, raw)
    sha256 = hashlib.sha256(raw).hexdigest()
    relative_path = target.relative_to(workspace).as_posix()
    provenance = {
        "provider": "comfyui",
        "endpoint": client.base_url.rstrip("/"),
        "prompt_id": art.prompt_id,
        "workflow_id": art.workflow_id,
        "workflow_sha256": art.workflow_sha256,
        "model_files": art.model_files,
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "seed": seed,
        "requested_width": width,
        "requested_height": height,
        "source_output": art.source_output,
    }
    if reference_asset_ids:
        provenance["reference_asset_ids"] = list(reference_asset_ids)
    if refined is not None:
        from engine.original.refine import summary

        provenance["refine"] = summary(refined)
    asset = AssetRecord(
        id=asset_id,
        project_id=project_id,
        asset_type="COMFYUI_GENERATED_IMAGE",
        filename=filename,
        relative_path=relative_path,
        content_type="image/png",
        width=art.width,
        height=art.height,
        byte_size=len(raw),
        sha256=sha256,
        status="READY",
        provenance=provenance,
    )
    db.add(asset)
    db.commit()
    progress(1.0, "ComfyUI image verified and persisted")
    return {
        "asset_id": asset_id,
        "relative_path": relative_path,
        "filename": filename,
        "content_type": "image/png",
        "width": art.width,
        "height": art.height,
        "byte_size": len(raw),
        "sha256": sha256,
        "prompt_id": art.prompt_id,
        "workflow_id": art.workflow_id,
    }


INPAINT_WORKFLOW_ID = "qwen_image_21_inpaint"


def inpaint_image_operation(
    db: Session,
    progress,
    is_cancelled,
    *,
    project_id: str,
    base_asset_id: str | None = None,
    image_data: str | None = None,
    mask_data: str,
    prompt: str,
    negative_prompt: str | None = None,
    seed: int = 20261019,
    timeout_s: float = 900.0,
) -> dict[str, Any]:
    """Inpaint a masked region of an existing asset using the approved Qwen inpaint workflow."""
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise ComfyImageGenerationError("Project not found")

    workspace = Path(str(project.workspace_path))
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    output_dir.mkdir(parents=True, exist_ok=True)

    base_bytes: bytes
    if base_asset_id:
        asset = db.query(AssetRecord).filter(AssetRecord.id == base_asset_id, AssetRecord.project_id == project_id).first()
        if not asset:
            raise ComfyImageGenerationError(f"Base asset {base_asset_id} not found in project")
        base_path = resolve_contained_path(workspace, asset.relative_path)
        base_bytes = base_path.read_bytes()
    elif image_data:
        raw_b64 = image_data.split(",", 1)[1] if "," in image_data else image_data
        base_bytes = base64.b64decode(raw_b64)
    else:
        raise ComfyImageGenerationError("Either base_asset_id or image_data must be provided for inpainting")

    raw_mask_b64 = mask_data.split(",", 1)[1] if "," in mask_data else mask_data
    mask_bytes = base64.b64decode(raw_mask_b64)

    # Ensure mask dimensions match base image
    try:
        with Image.open(io.BytesIO(base_bytes)) as pil_base:
            base_w, base_h = pil_base.size
        with Image.open(io.BytesIO(mask_bytes)) as pil_mask:
            if pil_mask.size != (base_w, base_h):
                pil_mask_resized = pil_mask.resize((base_w, base_h), Image.Resampling.NEAREST)
                buf = io.BytesIO()
                pil_mask_resized.save(buf, format="PNG")
                mask_bytes = buf.getvalue()
    except Exception as exc:
        raise ComfyImageGenerationError(f"Invalid image or mask data for inpainting: {exc}") from exc

    client = ComfyUIClient()
    ref_name = client.upload_image_bytes(base_bytes)
    mask_name = client.upload_image_bytes(mask_bytes)

    reg = ComfyWorkflowRegistry(client)
    wf, wf_sha256 = reg.load(INPAINT_WORKFLOW_ID)
    meta = reg.metadata(INPAINT_WORKFLOW_ID)

    patched = _patch_workflow(
        wf,
        meta["patch_slots"],
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=base_w,
        height=base_h,
        seed=seed,
        prefix=f"panelflow/{project_id}/inpaint",
        reference_image=ref_name,
        mask_image=mask_name,
    )

    progress(0.1, "Submitting inpaint request to ComfyUI")
    raw, prompt_id, ref = ArtEngine(client, reg).run(patched, timeout=timeout_s, is_cancelled=is_cancelled, progress=progress)

    asset_id = str(uuid.uuid4())
    suffix = Path(ref["filename"]).suffix.lower() or ".png"
    filename = f"{asset_id}{suffix}"
    target = _write_project_image(workspace, Path("generated") / "comfyui" / filename, raw)
    sha256 = hashlib.sha256(raw).hexdigest()
    relative_path = target.relative_to(workspace).as_posix()

    provenance = {
        "provider": "comfyui",
        "endpoint": client.base_url.rstrip("/"),
        "prompt_id": prompt_id,
        "workflow_id": INPAINT_WORKFLOW_ID,
        "workflow_sha256": wf_sha256,
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "seed": seed,
        "base_asset_id": base_asset_id,
        "source_output": ref,
        "operation": "inpaint",
    }
    asset = AssetRecord(
        id=asset_id,
        project_id=project_id,
        asset_type="COMFYUI_GENERATED_IMAGE",
        filename=filename,
        relative_path=relative_path,
        content_type="image/png",
        width=base_w,
        height=base_h,
        byte_size=len(raw),
        sha256=sha256,
        status="READY",
        provenance=provenance,
    )
    db.add(asset)
    db.commit()
    progress(1.0, "Inpainted image verified and saved")
    return {
        "asset_id": asset_id,
        "relative_path": relative_path,
        "filename": filename,
        "content_type": "image/png",
        "width": base_w,
        "height": base_h,
        "byte_size": len(raw),
        "sha256": sha256,
        "prompt_id": prompt_id,
        "workflow_id": INPAINT_WORKFLOW_ID,
    }


def build_comfy_image_operation(project_id: str, payload: dict[str, Any]):
    """Rehydrate a ComfyUI operation from its persisted validated input."""
    if payload.get("workflow_id") == INPAINT_WORKFLOW_ID or payload.get("operation") == "inpaint":
        return lambda db, progress, is_cancelled: inpaint_image_operation(
            db,
            progress,
            is_cancelled,
            project_id=project_id,
            base_asset_id=payload.get("base_asset_id"),
            image_data=payload.get("image_data"),
            mask_data=payload["mask_data"],
            prompt=payload["prompt"],
            negative_prompt=payload.get("negative_prompt"),
            seed=payload.get("seed", 20261019),
            timeout_s=payload.get("timeout_s", 900.0),
        )
    return lambda db, progress, is_cancelled: generate_image_operation(
        db,
        progress,
        is_cancelled,
        project_id=project_id,
        workflow_id=payload["workflow_id"],
        prompt=payload["prompt"],
        negative_prompt=payload.get("negative_prompt"),
        width=payload["width"],
        height=payload["height"],
        seed=payload["seed"],
        timeout_s=payload.get("timeout_s", 900.0),
        refine=bool(payload.get("refine", False)),
        reference_asset_ids=payload.get("reference_asset_ids") or None,
    )


register_operation_factory("COMFYUI_IMAGE_GENERATION", build_comfy_image_operation)


class ComfyVideoGenerationError(RuntimeError):
    """Raised when a generated ComfyUI video cannot be verified or persisted."""


def generate_video_operation(
    db: Session,
    progress,
    is_cancelled,
    *,
    project_id: str,
    workflow_id: str = "minimax_h3_turbo_i2v",
    prompt: str,
    negative_prompt: str | None = None,
    reference_image_path: str | Path | None = None,
    width: int = 1344,
    height: int = 768,
    seed: int = 0,
    timeout_s: float = 900.0,
) -> dict[str, Any]:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise ComfyVideoGenerationError("Project not found")
    workspace = Path(str(project.workspace_path))
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    output_dir.mkdir(parents=True, exist_ok=True)

    client = ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)
    try:
        workflow, workflow_sha256 = registry.load(workflow_id)
        metadata = registry.metadata(workflow_id)
        preflight = registry.preflight(workflow_id)
        if not preflight["ready"]:
            if not preflight.get("comfy_online", True):
                try:
                    from engine.system.setup import comfyui_manager
                    if comfyui_manager.is_installed():
                        res = comfyui_manager.ensure_running(timeout_s=15.0)
                        if res.get("running"):
                            preflight = registry.preflight(workflow_id)
                except Exception:
                    pass
            if not preflight["ready"]:
                if not preflight.get("comfy_online", True):
                    raise ComfyVideoGenerationError(
                        f"ComfyUI is offline or unreachable at {client.base_url}. Please launch ComfyUI to generate video."
                    )
                raise ComfyVideoGenerationError(
                    f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, missing models={preflight['missing_models']}"
                )
    except (ComfyUIError, WorkflowRegistryError, ValueError) as exc:
        raise ComfyVideoGenerationError(str(exc)) from exc

    ref_img_name = None
    if reference_image_path:
        ref_path = Path(reference_image_path)
        if not ref_path.is_absolute():
            ref_path = resolve_contained_path(workspace, ref_path)
        if ref_path.exists():
            ref_img_name = client.upload_image(ref_path)

    patched = _patch_workflow(
        workflow,
        metadata["patch_slots"],
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        seed=seed,
        prefix=f"panelflow/{project_id}/{workflow_id}",
        reference_image=ref_img_name,
    )
    progress(0.05, f"Verified workflow {workflow_id}")
    prompt_id = client.submit_prompt(patched, client_id=f"panelflow-{project_id}")
    progress(0.12, f"Submitted ComfyUI video prompt {prompt_id}")

    deadline = time.monotonic() + timeout_s
    videos: list[dict[str, str]] = []
    while time.monotonic() < deadline:
        if is_cancelled():
            raise ComfyVideoGenerationError("Video generation cancelled; ComfyUI execution may still finish")
        videos = _history_videos(client.history(prompt_id), prompt_id)
        if videos:
            break
        progress(min(0.9, 0.12 + (timeout_s - max(0.0, deadline - time.monotonic())) / timeout_s * 0.75), "Waiting for ComfyUI video output")
        time.sleep(2.0)
    if not videos:
        raise ComfyVideoGenerationError(f"ComfyUI did not produce a video within {timeout_s:.0f}s")

    video_ref = videos[0]
    raw = client.download_output(video_ref["filename"], video_ref["subfolder"], video_ref["type"])

    asset_id = str(uuid.uuid4())
    suffix = Path(video_ref["filename"]).suffix.lower() or ".mp4"
    filename = f"{asset_id}{suffix}"
    target = resolve_contained_path(workspace, Path("generated") / "comfyui" / filename)
    with open_contained_output(workspace, Path("generated") / "comfyui" / filename, exclusive=True) as output_file:
        output_file.write(raw)

    sha256 = hashlib.sha256(raw).hexdigest()
    relative_path = target.relative_to(workspace).as_posix()
    provenance = {
        "provider": "comfyui",
        "endpoint": client.base_url.rstrip("/"),
        "prompt_id": prompt_id,
        "workflow_id": workflow_id,
        "workflow_sha256": workflow_sha256,
        "model_files": metadata.get("model_files", []),
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "seed": seed,
        "requested_width": width,
        "requested_height": height,
        "source_output": video_ref,
    }
    asset = AssetRecord(
        id=asset_id,
        project_id=project_id,
        asset_type="COMFYUI_GENERATED_VIDEO",
        filename=filename,
        relative_path=relative_path,
        content_type="video/mp4",
        width=width,
        height=height,
        byte_size=len(raw),
        sha256=sha256,
        status="READY",
        provenance=provenance,
    )
    db.add(asset)
    db.commit()
    progress(1.0, "ComfyUI video verified and persisted")
    return {
        "asset_id": asset_id,
        "relative_path": relative_path,
        "filename": filename,
        "content_type": "video/mp4",
        "width": width,
        "height": height,
        "byte_size": len(raw),
        "sha256": sha256,
        "prompt_id": prompt_id,
        "workflow_id": workflow_id,
    }


def build_comfy_video_operation(project_id: str, payload: dict[str, Any]):
    """Rehydrate a ComfyUI video operation from its persisted validated input."""
    return lambda db, progress, is_cancelled: generate_video_operation(
        db,
        progress,
        is_cancelled,
        project_id=project_id,
        workflow_id=payload.get("workflow_id", "minimax_h3_turbo_i2v"),
        prompt=payload["prompt"],
        negative_prompt=payload.get("negative_prompt"),
        reference_image_path=payload.get("reference_image_path"),
        width=payload.get("width", 1344),
        height=payload.get("height", 768),
        seed=payload.get("seed", 0),
        timeout_s=payload.get("timeout_s", 900.0),
    )


register_operation_factory("COMFYUI_VIDEO_GENERATION", build_comfy_video_operation)
