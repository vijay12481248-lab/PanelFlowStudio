"""The one image-generation engine of PanelFlow Studio.

Every feature that needs a picture (Original Stories, ChronoFlow, the Comfy image screen, YouTube thumbnails, autopilot) calls
`ArtEngine.generate`, which runs the single approved text-to-image workflow `qwen_image_21` (Qwen Image 2.1 Turbo). There is no
second text-to-image workflow: do not add one, extend this one. The graph itself lives in `workflows/qwen_image_21.api.json` and is
registered (checksum, models, patch slots) in `workflow_registry.json`.

`ArtEngine.run` is the shared submit -> poll -> download step, also used by the image *edit* tools (inpaint, ControlNet, matting).
The pure helpers below (`_patch_workflow`, `_history_images`, `_validate_output_dimensions`) live here so that neither this module
nor `service.py` has to import the other.
"""
from __future__ import annotations

import io
import random
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from PIL import Image

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry

ART_WORKFLOW_ID = "qwen_image_21"
POLL_SECONDS = 1.5


class ComfyImageGenerationError(RuntimeError):
    """Raised when a generated ComfyUI image cannot be produced, verified or persisted."""


class ArtTimeoutError(ComfyImageGenerationError, TimeoutError):
    """ComfyUI produced no image in time."""


def _patch_workflow(
    workflow: dict[str, Any],
    patch_slots: dict[str, dict[str, str]],
    prompt: str,
    negative_prompt: str | None,
    width: int,
    height: int,
    seed: int,
    prefix: str,
    reference_image: str | None = None,
    reference_image_b: str | None = None,
    reference_weight: float | None = None,
    mask_image: str | None = None,
    denoise: float | None = None,
    pose_image: str | None = None,
    depth_image: str | None = None,
    pose_weight: float | None = None,
    depth_weight: float | None = None,
    duration: float | None = None,
) -> dict[str, Any]:
    patched = deepcopy(workflow)
    values: dict[str, Any] = {
        "prompt": prompt,
        "seed": seed,
        "filename_prefix": prefix,
    }
    if "negative_prompt" in patch_slots:  # a graph without a negative prompt input (the fast H3 video graph) simply has no slot for one
        values["negative_prompt"] = negative_prompt or ""
    if duration is not None and "duration" in patch_slots:
        values["duration"] = duration
    if "width" in patch_slots:
        values["width"] = width
    if "height" in patch_slots:
        values["height"] = height
    if reference_image is not None:
        values["reference_image"] = reference_image
    if reference_image_b is not None:
        values["reference_image_b"] = reference_image_b
    if reference_weight is not None and "reference_weight" in patch_slots:
        values["reference_weight"] = reference_weight
    if mask_image is not None:
        values["mask_image"] = mask_image
    if denoise is not None and "denoise" in patch_slots:
        values["denoise"] = denoise
    if pose_image is not None:
        values["pose_image"] = pose_image
    if depth_image is not None:
        values["depth_image"] = depth_image
    if pose_weight is not None and "pose_weight" in patch_slots:
        values["pose_weight"] = pose_weight
    if depth_weight is not None and "depth_weight" in patch_slots:
        values["depth_weight"] = depth_weight

    optional_unsupplied = set()
    if duration is None and "duration" in patch_slots:
        optional_unsupplied.add("duration")
    if reference_weight is None and "reference_weight" in patch_slots:
        optional_unsupplied.add("reference_weight")
    if denoise is None and "denoise" in patch_slots:
        optional_unsupplied.add("denoise")
    if pose_image is None and "pose_image" in patch_slots:
        optional_unsupplied.add("pose_image")
    if depth_image is None and "depth_image" in patch_slots:
        optional_unsupplied.add("depth_image")
    if pose_weight is None and "pose_weight" in patch_slots:
        optional_unsupplied.add("pose_weight")
    if depth_weight is None and "depth_weight" in patch_slots:
        optional_unsupplied.add("depth_weight")

    declared = set(patch_slots) - optional_unsupplied
    if declared != set(values):
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


@dataclass(frozen=True)
class ArtImage:
    png: bytes
    width: int
    height: int
    prompt_id: str
    workflow_id: str
    workflow_sha256: str
    model_files: list[str]
    source_output: dict[str, str]
    seed: int


def _never() -> bool:
    return False


class ArtEngine:
    """Text to image through the one approved workflow. Cheap to construct; the readiness check runs once per instance."""

    def __init__(self, client: ComfyUIClient | None = None, registry: ComfyWorkflowRegistry | None = None):
        self.client = client or ComfyUIClient()
        self.registry = registry or ComfyWorkflowRegistry(self.client)
        self._ready = False

    def require_ready(self) -> None:
        if self._ready:
            return
        preflight = self.registry.preflight(ART_WORKFLOW_ID)
        if not preflight["ready"]:
            raise ComfyImageGenerationError(
                f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, missing models={preflight['missing_models']}"
            )
        self._ready = True

    def run(
        self,
        workflow: dict[str, Any],
        *,
        timeout: float = 300.0,
        is_cancelled: Callable[[], bool] = _never,
        progress: Callable[[float, str], None] | None = None,
        client_id: str | None = None,
        collect: Callable[[dict[str, Any], str], list[dict[str, str]]] | None = None,
    ) -> tuple[bytes, str, dict[str, str]]:
        """Submit an already patched graph and wait for its first output (an image, or whatever `collect` extracts from the history, e.g. a video).
        Returns (bytes, prompt_id, history reference)."""
        prompt_id = self.client.submit_prompt(workflow, client_id=client_id) if client_id else self.client.submit_prompt(workflow)
        if progress:
            progress(0.12, f"Submitted ComfyUI prompt {prompt_id}")
        started = time.monotonic()
        deadline = started + timeout
        while time.monotonic() < deadline:
            if is_cancelled():
                raise ComfyImageGenerationError("Image generation cancelled; ComfyUI execution may still finish")
            images = (collect or _history_images)(self.client.history(prompt_id), prompt_id)
            if images:
                ref = images[0]
                return self.client.download_output(ref["filename"], ref["subfolder"], ref["type"]), prompt_id, ref
            if progress:
                progress(min(0.9, 0.12 + (time.monotonic() - started) / timeout * 0.75), "Waiting for ComfyUI output")
            time.sleep(POLL_SECONDS)
        raise ArtTimeoutError(f"ComfyUI did not produce an image within {timeout:.0f}s")

    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = "",
        width: int = 1344,
        height: int = 768,
        seed: int | None = None,
        prefix: str = "panelflow_art",
        *,
        timeout: float = 300.0,
        is_cancelled: Callable[[], bool] = _never,
        progress: Callable[[float, str], None] | None = None,
        client_id: str | None = None,
    ) -> ArtImage:
        self.require_ready()
        workflow, workflow_sha256 = self.registry.load(ART_WORKFLOW_ID)
        metadata = self.registry.metadata(ART_WORKFLOW_ID)
        policy = metadata["dimension_policy"]
        _validate_output_dimensions(actual_width=width, actual_height=height, requested_width=width, requested_height=height,
                                    dimension_policy=policy)  # rejects a request the workflow cannot honour before any GPU time is spent
        if seed is None:
            seed = random.randint(1, 2**31 - 1)
        patched = _patch_workflow(workflow, metadata["patch_slots"], prompt, negative_prompt, width, height, seed, prefix)
        if progress:
            progress(0.05, f"Verified workflow {ART_WORKFLOW_ID}")
        raw, prompt_id, ref = self.run(patched, timeout=timeout, is_cancelled=is_cancelled, progress=progress, client_id=client_id)
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                actual_width, actual_height = image.size
        except Exception as exc:
            raise ComfyImageGenerationError("ComfyUI returned an invalid image artifact") from exc
        _validate_output_dimensions(actual_width=actual_width, actual_height=actual_height, requested_width=width, requested_height=height,
                                    dimension_policy=policy)
        return ArtImage(png=raw, width=actual_width, height=actual_height, prompt_id=prompt_id, workflow_id=ART_WORKFLOW_ID,
                        workflow_sha256=workflow_sha256, model_files=list(metadata.get("model_files", [])), source_output=ref, seed=seed)
