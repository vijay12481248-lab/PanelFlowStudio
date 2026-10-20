"""PanelFlow-owned ComfyUI image generation operation."""

from __future__ import annotations

import hashlib
import io
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from engine.comfyui import ComfyUIClient, ComfyUIError, ComfyWorkflowRegistry, WorkflowRegistryError
from engine.database.models import AssetRecord, ProjectRecord
from engine.jobs.workflow import register_operation_factory
from engine.security.paths import open_contained_output, resolve_contained_path


class ComfyImageGenerationError(RuntimeError):
    """Raised when a generated ComfyUI image cannot be verified or persisted."""


def _patch_workflow(
    workflow: dict[str, Any],
    patch_slots: dict[str, dict[str, str]],
    prompt: str,
    negative_prompt: str | None,
    width: int,
    height: int,
    seed: int,
    prefix: str,
) -> dict[str, Any]:
    patched = deepcopy(workflow)
    values: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "width": width,
        "height": height,
        "seed": seed,
        "filename_prefix": prefix,
    }
    if set(patch_slots) != set(values):
        raise ComfyImageGenerationError("Approved workflow does not declare every required patch slot")
    for slot_name, value in values.items():
        slot = patch_slots[slot_name]
        node = patched.get(str(slot.get("node_id")))
        if not isinstance(node, dict):
            raise ComfyImageGenerationError(f"Approved {slot_name} patch slot node is missing")
        if node.get("class_type") != slot.get("class_type"):
            raise ComfyImageGenerationError(f"Approved {slot_name} patch slot class_type does not match workflow")
        input_name = slot.get("input")
        inputs = node.get("inputs")
        if not isinstance(input_name, str) or not isinstance(inputs, dict) or input_name not in inputs:
            raise ComfyImageGenerationError(f"Approved {slot_name} patch slot input is unavailable")
        inputs[input_name] = value
    return patched


def _validate_output_dimensions(
    *,
    actual_width: int,
    actual_height: int,
    requested_width: int,
    requested_height: int,
    dimension_policy: dict[str, Any],
) -> None:
    minimum = int(dimension_policy.get("min", 1))
    maximum = int(dimension_policy.get("max", 2**31 - 1))
    multiple_of = int(dimension_policy.get("multiple_of", 1))
    if dimension_policy.get("mode") != "exact":
        raise ComfyImageGenerationError("Approved workflow has an unsupported dimension policy")
    if not (minimum <= requested_width <= maximum and minimum <= requested_height <= maximum):
        raise ComfyImageGenerationError("Requested dimensions violate the approved workflow policy")
    if requested_width % multiple_of or requested_height % multiple_of:
        raise ComfyImageGenerationError("Requested dimensions violate the approved workflow alignment policy")
    if (actual_width, actual_height) != (requested_width, requested_height):
        raise ComfyImageGenerationError(
            f"ComfyUI output dimensions {actual_width}x{actual_height} do not match requested dimensions "
            f"{requested_width}x{requested_height}"
        )


def _history_images(history: dict[str, Any], prompt_id: str) -> list[dict[str, str]]:
    record = history.get(prompt_id, history)
    outputs = record.get("outputs", {}) if isinstance(record, dict) else {}
    images: list[dict[str, str]] = []
    for output in outputs.values() if isinstance(outputs, dict) else []:
        for image in output.get("images", []) if isinstance(output, dict) else []:
            if isinstance(image, dict) and isinstance(image.get("filename"), str):
                images.append({
                    "filename": image["filename"],
                    "subfolder": str(image.get("subfolder", "")),
                    "type": str(image.get("type", "output")),
                })
    return images


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
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise ComfyImageGenerationError("Project not found")
    workspace = Path(str(project.workspace_path))
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ComfyImageGenerationError("ComfyUI output directory is not a safe directory")

    client = ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)
    try:
        workflow, workflow_sha256 = registry.load(workflow_id)
        metadata = registry.metadata(workflow_id)
        preflight = registry.preflight(workflow_id)
        if not preflight["ready"]:
            raise ComfyImageGenerationError(
                f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, missing models={preflight['missing_models']}"
            )
    except (ComfyUIError, WorkflowRegistryError, ValueError) as exc:
        raise ComfyImageGenerationError(str(exc)) from exc

    patched = _patch_workflow(
        workflow,
        metadata["patch_slots"],
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        seed=seed,
        prefix=f"panelflow/{project_id}/{workflow_id}",
    )
    _validate_output_dimensions(
        actual_width=width,
        actual_height=height,
        requested_width=width,
        requested_height=height,
        dimension_policy=metadata["dimension_policy"],
    )
    progress(0.05, f"Verified workflow {workflow_id}")
    prompt_id = client.submit_prompt(patched, client_id=f"panelflow-{project_id}")
    progress(0.12, f"Submitted ComfyUI prompt {prompt_id}")

    deadline = time.monotonic() + timeout_s
    images: list[dict[str, str]] = []
    while time.monotonic() < deadline:
        if is_cancelled():
            raise ComfyImageGenerationError("Image generation cancelled; ComfyUI execution may still finish")
        images = _history_images(client.history(prompt_id), prompt_id)
        if images:
            break
        progress(min(0.9, 0.12 + (timeout_s - max(0.0, deadline - time.monotonic())) / timeout_s * 0.75), "Waiting for ComfyUI output")
        time.sleep(2.0)
    if not images:
        raise ComfyImageGenerationError(f"ComfyUI did not produce an image within {timeout_s:.0f}s")

    image_ref = images[0]
    raw = client.download_output(image_ref["filename"], image_ref["subfolder"], image_ref["type"])
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            actual_width, actual_height = image.size
            content_type = Image.MIME.get(image.format, "image/png")
    except Exception as exc:
        raise ComfyImageGenerationError("ComfyUI returned an invalid image artifact") from exc

    _validate_output_dimensions(
        actual_width=actual_width,
        actual_height=actual_height,
        requested_width=width,
        requested_height=height,
        dimension_policy=metadata["dimension_policy"],
    )

    asset_id = str(uuid.uuid4())
    suffix = Path(image_ref["filename"]).suffix.lower() or ".png"
    filename = f"{asset_id}{suffix}"
    target = _write_project_image(workspace, Path("generated") / "comfyui" / filename, raw)
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
        "source_output": image_ref,
    }
    asset = AssetRecord(
        id=asset_id,
        project_id=project_id,
        asset_type="COMFYUI_GENERATED_IMAGE",
        filename=filename,
        relative_path=relative_path,
        content_type=content_type,
        width=actual_width,
        height=actual_height,
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
        "content_type": content_type,
        "width": actual_width,
        "height": actual_height,
        "byte_size": len(raw),
        "sha256": sha256,
        "prompt_id": prompt_id,
        "workflow_id": workflow_id,
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
