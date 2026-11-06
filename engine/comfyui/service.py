"""PanelFlow-owned ComfyUI image generation operation."""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

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
) -> dict[str, Any]:
    """Generate one image with the central ArtEngine and persist it as a project asset."""
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

    client = ComfyUIClient()
    try:
        art = ArtEngine(client, ComfyWorkflowRegistry(client)).generate(
            prompt, negative_prompt, width, height, seed, f"panelflow/{project_id}/{ART_WORKFLOW_ID}",
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


def build_comfy_image_operation(project_id: str, payload: dict[str, Any]):
    """Rehydrate a ComfyUI operation from its persisted validated input."""
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
