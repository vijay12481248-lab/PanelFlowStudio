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
    EDIT_WORKFLOW_ID,
    IMAGE_WORKFLOW_IDS,
    ArtEngine,
    ComfyImageGenerationError,
    _history_images,
    _patch_workflow,
    _validate_output_dimensions,
)
from engine.comfyui.edit_prompt import compose_edit_prompt, compose_transfer_prompt, release_local_model
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


def _project_asset_file(db: Session, project_id: str, workspace: Path, asset_id: str, label: str, error: type[RuntimeError]) -> Path:
    """The file of an asset that belongs to this project, contained in its workspace. Raises `error` if there is none."""
    asset = db.query(AssetRecord).filter(AssetRecord.id == asset_id, AssetRecord.project_id == project_id).first()
    if asset is None:
        raise error(f"{label} {asset_id} not found in this project")
    path = resolve_contained_path(workspace, asset.relative_path)
    if not path.is_file():
        raise error(f"{label} {asset_id} has no file on disk")
    return path


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
    if workflow_id not in IMAGE_WORKFLOW_IDS:
        raise ComfyImageGenerationError(f"Image workflows are {IMAGE_WORKFLOW_IDS}; got {workflow_id!r}")
    if refine and workflow_id != ART_WORKFLOW_ID:
        raise ComfyImageGenerationError(f"refine only runs on {ART_WORKFLOW_ID!r}")
    workspace = Path(str(project.workspace_path))
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ComfyImageGenerationError("ComfyUI output directory is not a safe directory")

    references = [_project_asset_file(db, project_id, workspace, ref_id, "Reference asset", ComfyImageGenerationError)
                  for ref_id in reference_asset_ids or []]
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
            draw_width, draw_height = width, height
            if workflow_id == EDIT_WORKFLOW_ID:
                # H3-Image draws soft below its working area, so it draws there in the same shape and the
                # picture is resized back to what was asked for (what MiniMax's own API does).
                draw_width, draw_height = h3_edit_size(width, height)
                release_local_model()  # the local model and the H3 checkpoint do not fit in the VRAM together
            art = ArtEngine(client, ComfyWorkflowRegistry(client)).generate(
                prompt, negative_prompt, draw_width, draw_height, seed, f"panelflow/{project_id}/{workflow_id}",
                reference_images=references or None,
                timeout=timeout_s, is_cancelled=is_cancelled, progress=progress, client_id=f"panelflow-{project_id}",
                workflow_id=workflow_id,
            )
    except (ComfyUIError, WorkflowRegistryError, ValueError) as exc:
        raise ComfyImageGenerationError(str(exc)) from exc

    raw = art.png
    drawn_size = (art.width, art.height)
    if drawn_size != (width, height):  # drawn at the model's working size: back to the size that was asked for
        with Image.open(io.BytesIO(raw)) as picture:
            resized = io.BytesIO()
            picture.convert("RGB").resize((width, height), Image.Resampling.LANCZOS).save(resized, format="PNG")
        raw = resized.getvalue()
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
        "drawn_width": drawn_size[0],
        "drawn_height": drawn_size[1],
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
        width=width,
        height=height,
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
        "width": width,
        "height": height,
        "byte_size": len(raw),
        "sha256": sha256,
        "prompt_id": art.prompt_id,
        "workflow_id": art.workflow_id,
    }


INPAINT_WORKFLOW_ID = "qwen_image_21_inpaint"

# MiniMax-H3-Image needs a picture of about 4 megapixels or more: below that the edit comes
# out soft. Comfy-Org's own edit template scales the input picture to 4 MP before it starts,
# and keeps the picture's shape; the result is the size the edit is made at.
H3_EDIT_AREA_PIXELS = 4 * 1024 * 1024
H3_EDIT_GRID = 32
H3_EDIT_MAX_SIDE = 4096
H3_EDIT_MIN_SIDE = 256


def h3_edit_size(width: int, height: int) -> tuple[int, int]:
    """The size a MiniMax-H3-Image edit runs at: the picture's shape at the model's working area.

    The picture's aspect is kept, the area is the working area of the model, and both sides
    land on the 32-pixel grid the canvas uses. A picture larger than the working area is
    scaled down rather than kept: the edit is made at one size, and the model's own range
    ends at 20 megapixels.
    """
    if width <= 0 or height <= 0:
        raise ComfyImageGenerationError("The picture to edit has no readable size")
    scale = (H3_EDIT_AREA_PIXELS / float(width * height)) ** 0.5
    target_w = max(H3_EDIT_GRID, int(round(width * scale / H3_EDIT_GRID)) * H3_EDIT_GRID)
    target_h = max(H3_EDIT_GRID, int(round(height * scale / H3_EDIT_GRID)) * H3_EDIT_GRID)
    if target_w > H3_EDIT_MAX_SIDE or target_h > H3_EDIT_MAX_SIDE:
        shrink = H3_EDIT_MAX_SIDE / float(max(target_w, target_h))
        target_w = int(target_w * shrink / H3_EDIT_GRID) * H3_EDIT_GRID
        target_h = int(target_h * shrink / H3_EDIT_GRID) * H3_EDIT_GRID
    target_w = max(target_w, H3_EDIT_GRID)
    target_h = max(target_h, H3_EDIT_GRID)
    if min(target_w, target_h) < H3_EDIT_MIN_SIDE:
        raise ComfyImageGenerationError(
            f"The picture is too wide or too tall to edit: the model works between {H3_EDIT_MIN_SIDE} "
            f"and {H3_EDIT_MAX_SIDE} pixels on each side, and this shape needs "
            f"{target_w}x{target_h}"
        )
    return target_w, target_h


POSE_REFERENCE_MAX_BYTES = 20 * 1024 * 1024


def save_project_image(
    db: Session, project_id: str, image_data: str, *, asset_type: str, prefix: str, provenance: dict[str, Any],
    what: str = "picture", check_edit_size: bool = False,
) -> AssetRecord:
    """Store an uploaded picture (base64 or a data URL) as a PNG project asset."""
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise ComfyImageGenerationError("Project not found")
    try:
        raw = base64.b64decode(image_data.split(",", 1)[1] if "," in image_data else image_data, validate=True)
        if len(raw) > POSE_REFERENCE_MAX_BYTES:
            raise ValueError(f"larger than {POSE_REFERENCE_MAX_BYTES // (1024 * 1024)} MB")
        with Image.open(io.BytesIO(raw)) as picture:
            picture = picture.convert("RGB")
            width, height = picture.size
            if check_edit_size:
                h3_edit_size(width, height)  # refuses a shape the model cannot work at, before any GPU time is spent
            out = io.BytesIO()
            picture.save(out, format="PNG")
    except ComfyImageGenerationError:
        raise
    except Exception as exc:
        raise ComfyImageGenerationError(f"The {what} is not a usable image: {exc}") from exc
    png = out.getvalue()
    asset_id = str(uuid.uuid4())
    filename = f"{prefix}-{asset_id}.png"
    workspace = Path(str(project.workspace_path))
    target = _write_project_image(workspace, Path("generated") / "comfyui" / filename, png)
    asset = AssetRecord(
        id=asset_id, project_id=project_id, asset_type=asset_type, filename=filename,
        relative_path=target.relative_to(workspace).as_posix(), content_type="image/png",
        width=width, height=height, byte_size=len(png), sha256=hashlib.sha256(png).hexdigest(), status="READY",
        provenance=provenance,
    )
    db.add(asset)
    db.commit()
    return asset


def save_pose_reference(db: Session, project_id: str, image_data: str) -> str:
    """Store an uploaded pose picture as a project asset and return its id."""
    return save_project_image(
        db, project_id, image_data, asset_type="POSE_REFERENCE", prefix="pose", provenance={"role": "pose_camera_reference"},
        what="pose picture", check_edit_size=True,
    ).id


def edit_image_operation(
    db: Session,
    progress,
    is_cancelled,
    *,
    project_id: str,
    base_asset_id: str,
    prompt: str,
    reference_asset_ids: list[str] | None = None,
    pose_asset_id: str | None = None,
    seed: int = 20261019,
    timeout_s: float = 1800.0,
) -> dict[str, Any]:
    """Edit an existing picture from a written instruction, with the approved MiniMax-H3-Image workflow.

    The picture being edited is `base_asset_id`; any extra assets are references the
    instruction may refer to. The result is persisted as a new project asset.

    With `pose_asset_id` it is a pose and camera transfer: `base_asset_id` is the artwork whose
    characters, scene and style are kept (<Picture 1>), the pose picture (often a photograph) gives
    the poses, camera angle and framing (<Picture 2>), and `prompt` is an optional note on who plays whom.
    The result has the pose picture's shape.
    """
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise ComfyImageGenerationError("Project not found")
    workspace = Path(str(project.workspace_path))

    base = db.query(AssetRecord).filter(
        AssetRecord.id == base_asset_id, AssetRecord.project_id == project_id).first()
    if not base:
        raise ComfyImageGenerationError(f"Base asset {base_asset_id} not found in project")
    base_bytes = resolve_contained_path(workspace, base.relative_path).read_bytes()

    # The picture that sets the canvas: the one being edited, or in a transfer the pose picture.
    canvas_bytes = base_bytes
    if pose_asset_id:
        pose = db.query(AssetRecord).filter(
            AssetRecord.id == pose_asset_id, AssetRecord.project_id == project_id).first()
        if not pose:
            raise ComfyImageGenerationError(f"Pose asset {pose_asset_id} not found in project")
        canvas_bytes = resolve_contained_path(workspace, pose.relative_path).read_bytes()

    references = [canvas_bytes]
    for ref_id in reference_asset_ids or []:
        asset = db.query(AssetRecord).filter(
            AssetRecord.id == ref_id, AssetRecord.project_id == project_id).first()
        if not asset:
            raise ComfyImageGenerationError(f"Reference asset {ref_id} not found in project")
        references.append(resolve_contained_path(workspace, asset.relative_path).read_bytes())

    # The edit is made at the model's working size, so the picture that sets the canvas is scaled to it
    # first: the reference the model sees then carries the same detail as the result.
    try:
        with Image.open(io.BytesIO(canvas_bytes)) as picture:
            picture = picture.convert("RGB")
            source_width, source_height = picture.size
            width, height = h3_edit_size(source_width, source_height)
            if (width, height) != (source_width, source_height):
                picture = picture.resize((width, height), Image.Resampling.LANCZOS)
            scaled = io.BytesIO()
            picture.save(scaled, format="PNG")
            references[0] = scaled.getvalue()
    except ComfyImageGenerationError:
        raise
    except Exception as exc:
        raise ComfyImageGenerationError(f"Base asset is not a readable image: {exc}") from exc

    if pose_asset_id:
        # <Picture 1> is the artwork (kept at its own size: ComfyUI scales it), <Picture 2> the scaled pose picture.
        try:
            with Image.open(io.BytesIO(base_bytes)) as artwork:
                flat = io.BytesIO()
                artwork.convert("RGB").save(flat, format="PNG")
        except Exception as exc:
            raise ComfyImageGenerationError(f"Base asset is not a readable image: {exc}") from exc
        references.insert(0, flat.getvalue())

    client = ComfyUIClient()
    reg = ComfyWorkflowRegistry(client)
    try:
        reg.load(EDIT_WORKFLOW_ID)
        preflight = reg.preflight(EDIT_WORKFLOW_ID)
    except (ComfyUIError, WorkflowRegistryError) as exc:
        raise ComfyImageGenerationError(str(exc)) from exc
    if not preflight["ready"]:
        raise ComfyImageGenerationError(
            f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, "
            f"missing models={preflight['missing_models']}"
        )

    # The checkpoint wants a caption of the finished picture, not a one-line instruction.
    # The local model writes it; the instruction is used as it is when the model is away.
    if pose_asset_id:
        caption = compose_transfer_prompt(references[0], references[1], prompt)
    else:
        caption = compose_edit_prompt(prompt, references[0])
    if caption != prompt.strip():
        progress(0.1, "Writing the caption for the edited picture")
    # The local model and the H3 checkpoint do not fit in the VRAM together.
    release_local_model()

    try:
        art = ArtEngine(client, reg).edit(
            caption, references, width=width, height=height, seed=seed,
            prefix=f"panelflow/{project_id}/{EDIT_WORKFLOW_ID}",
            timeout=timeout_s, is_cancelled=is_cancelled, progress=progress,
            client_id=f"panelflow-{project_id}")
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
        "caption": caption,
        "seed": seed,
        "requested_width": width,
        "requested_height": height,
        "source_width": source_width,
        "source_height": source_height,
        "source_output": art.source_output,
        "base_asset_id": base_asset_id,
    }
    if reference_asset_ids:
        provenance["reference_asset_ids"] = list(reference_asset_ids)
    if pose_asset_id:
        provenance["mode"] = "pose_camera_transfer"
        provenance["pose_asset_id"] = pose_asset_id
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
    progress(1.0, "Edited image verified and persisted")
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
    if "workflow_id" not in payload and "asset_id" in payload:  # an edit job: its input is the edit request itself
        return lambda db, progress, is_cancelled: edit_image_operation(
            db,
            progress,
            is_cancelled,
            project_id=project_id,
            base_asset_id=payload["asset_id"],
            prompt=payload.get("prompt", ""),
            reference_asset_ids=payload.get("reference_asset_ids") or None,
            pose_asset_id=payload.get("pose_asset_id"),
            seed=payload.get("seed", 20261019),
            timeout_s=payload.get("timeout_s", 1800.0),
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


H3_CLIP_JOB_TYPE = "COMFYUI_H3_CLIP_GENERATION"  # also listed in engine.jobs.manager.COMFYUI_JOB_TYPES (the GPU gate)


class H3ClipGenerationError(RuntimeError):
    """Raised when an H3 clip cannot be rendered, verified or persisted."""


def _probe_video(path: Path) -> tuple[int, int, int, float]:
    """(width, height, frame count, fps) of a video file, or an error if it cannot be decoded."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), float(cap.get(cv2.CAP_PROP_FPS))
    finally:
        cap.release()
    if width <= 0 or height <= 0 or frames <= 0:
        raise H3ClipGenerationError("H3 returned a video that cannot be decoded")
    return width, height, frames, fps


def generate_clip_operation(
    db: Session,
    progress,
    is_cancelled,
    *,
    project_id: str,
    action: str,
    seconds: float,
    seed: int,
    first_asset_id: str,
    last_asset_id: str | None = None,
    timeout_s: float = 1500.0,
) -> dict[str, Any]:
    """Render one MiniMax H3 clip from project pictures and persist it as a project video asset.

    One picture is image-to-video; a first and a last picture is FL2VA (give the same asset twice for a clip that loops).
    The H3 prompt skeleton is built here (engine.original.h3_modes), so the caller sends only the change, in plain words.
    shortcut: the render itself cannot be cancelled once ComfyUI has it (h3_modes.make_clip has no cancel hook); cancel is honoured before it starts.
    """
    from engine.original import animate, h3_modes  # lazy: they import this package

    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise H3ClipGenerationError("Project not found")
    workspace = Path(str(project.workspace_path))
    first = _project_asset_file(db, project_id, workspace, first_asset_id, "First-frame asset", H3ClipGenerationError)
    last = _project_asset_file(db, project_id, workspace, last_asset_id, "Last-frame asset", H3ClipGenerationError) if last_asset_id else None
    mode = "fl2va" if last else "i2va"
    workflow_id = h3_modes.WORKFLOWS[mode]
    prompt = h3_modes.fl2va_prompt(action, seconds) if last else h3_modes.i2va_prompt(action)
    output_dir = resolve_contained_path(workspace, Path("generated") / "comfyui")
    output_dir.mkdir(parents=True, exist_ok=True)

    if is_cancelled():
        raise H3ClipGenerationError("Clip generation cancelled before rendering")
    client = ComfyUIClient()
    try:
        _workflow, workflow_sha256 = ComfyWorkflowRegistry(client).load(workflow_id)
        progress(0.05, f"Verified workflow {workflow_id}")
        animate.release_ollama()  # the film pipeline frees the local LLM before every H3 clip
        progress(0.1, f"Rendering {mode} clip with MiniMax H3")
        raw = h3_modes.make_clip(mode, prompt, seed=seed, seconds=seconds, first=first, last=last, client=client, timeout=timeout_s,
                                 prefix=f"panelflow/{project_id}/h3")
    except (ComfyUIError, WorkflowRegistryError, ValueError, RuntimeError) as exc:
        raise H3ClipGenerationError(str(exc)) from exc

    asset_id = str(uuid.uuid4())
    filename = f"{asset_id}.mp4"
    target = _write_project_image(workspace, Path("generated") / "comfyui" / filename, raw)  # generic exclusive byte writer despite its name
    try:
        width, height, frames, fps = _probe_video(target)
    except H3ClipGenerationError:
        target.unlink(missing_ok=True)  # never leave an unreadable file behind as an asset
        raise
    sha256 = hashlib.sha256(raw).hexdigest()
    relative_path = target.relative_to(workspace).as_posix()
    db.add(AssetRecord(
        id=asset_id, project_id=project_id, asset_type="COMFYUI_GENERATED_VIDEO", filename=filename, relative_path=relative_path,
        content_type="video/mp4", width=width, height=height, byte_size=len(raw), sha256=sha256, status="READY",
        provenance={"provider": "comfyui", "endpoint": client.base_url.rstrip("/"), "workflow_id": workflow_id, "workflow_sha256": workflow_sha256,
                    "mode": mode, "prompt": prompt, "action": action, "seed": seed, "requested_seconds": seconds, "frames": frames, "fps": fps,
                    "first_asset_id": first_asset_id, "last_asset_id": last_asset_id},
    ))
    db.commit()
    progress(1.0, "H3 clip verified and persisted")
    return {"asset_id": asset_id, "relative_path": relative_path, "filename": filename, "content_type": "video/mp4", "width": width,
            "height": height, "byte_size": len(raw), "sha256": sha256, "workflow_id": workflow_id, "mode": mode, "frames": frames, "fps": fps}


def build_h3_clip_operation(project_id: str, payload: dict[str, Any]):
    """Rehydrate an H3 clip operation from its persisted validated input."""
    return lambda db, progress, is_cancelled: generate_clip_operation(
        db, progress, is_cancelled, project_id=project_id, action=payload["action"], seconds=payload["seconds"], seed=payload["seed"],
        first_asset_id=payload["first_asset_id"], last_asset_id=payload.get("last_asset_id"), timeout_s=payload.get("timeout_s", 1500.0))


register_operation_factory(H3_CLIP_JOB_TYPE, build_h3_clip_operation)


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
