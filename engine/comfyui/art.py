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
from pathlib import Path
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
    reference_images: list[str] | None = None,
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
    if reference_images is not None:
        # character lock: bind up to four approved reference slots (images.image_1..4 autogrow)
        ref_slots = [name for name in ("reference_image", "reference_image_b", "reference_image_c", "reference_image_d")
                     if name in patch_slots]
        if len(reference_images) > len(ref_slots):
            raise ComfyImageGenerationError(
                f"Approved workflow declares {len(ref_slots)} reference slots; got {len(reference_images)} reference images")
        for slot_name, value in zip(ref_slots, reference_images):
            values[slot_name] = value
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
    ref_slot = patch_slots.get("reference_image", {})
    if "reference_image" not in values and ref_slot.get("class_type") == "TextEncodeQwenImage21":
        optional_unsupplied.add("reference_image")
    for extra_ref_slot in ("reference_image_b", "reference_image_c", "reference_image_d"):
        # Only the Qwen text-to-image workflow binds references through TextEncodeQwenImage21 and lets a
        # slot go unbound; every other approved workflow (e.g. anime_sdxl_ipa2) declares its reference
        # slots as mandatory, so omitting one must still refuse to run.
        if (extra_ref_slot in patch_slots and extra_ref_slot not in values
                and patch_slots[extra_ref_slot].get("class_type") == "TextEncodeQwenImage21"):
            optional_unsupplied.add(extra_ref_slot)
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

        # WP-3.1: TextEncodeQwenImage21 autogrow reference image binding via LoadImage DAG injection
        if slot.get("class_type") == "TextEncodeQwenImage21" and input_name.startswith("images.image_"):
            if isinstance(value, (list, tuple)):
                inputs[input_name] = list(value)
            else:
                load_id = "13"
                while load_id in patched:
                    load_id = str(int(load_id) + 1)
                patched[load_id] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": str(value)},
                }
                inputs[input_name] = [load_id, 0]
        else:
            inputs[input_name] = value

    # Unsupplied reference slots: clean their null placeholders from TextEncodeQwenImage21
    for unsupplied_slot in [n for n in ("reference_image", "reference_image_b", "reference_image_c", "reference_image_d")
                            if n in patch_slots and n not in values]:
        slot_meta = patch_slots[unsupplied_slot]
        if slot_meta.get("class_type") == "TextEncodeQwenImage21":
            ref_node = patched.get(str(slot_meta.get("node_id")))
            if isinstance(ref_node, dict) and isinstance(ref_node.get("inputs"), dict):
                ref_node["inputs"].pop(slot_meta.get("input"), None)

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


def _extract_history_error(history_entry: dict | None) -> str | None:
    """Inspect ComfyUI history record or status entry for execution failure or interruption.
    Returns extracted error description if status is error, else None.
    """
    if not isinstance(history_entry, dict):
        return None
    status = history_entry.get("status")
    if status is None and "status_str" in history_entry:
        status = history_entry
    elif status is None:
        for val in history_entry.values():
            if isinstance(val, dict) and "status" in val:
                status = val.get("status")
                break
    if not isinstance(status, dict):
        return None
    if status.get("status_str") != "error":
        messages = status.get("messages")
        if not (isinstance(messages, list) and any(isinstance(m, (list, tuple)) and m and m[0] in ("execution_error", "execution_interrupted") for m in messages)):
            return None

    messages = status.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, (list, tuple)) and len(msg) >= 2:
                event, payload = msg[0], msg[1]
                if event == "execution_error" and isinstance(payload, dict):
                    exc_msg = payload.get("exception_message")
                    exc_type = payload.get("exception_type")
                    node_type = payload.get("node_type")
                    node_id = payload.get("node_id")
                    parts: list[str] = []
                    if exc_msg:
                        parts.append(str(exc_msg).strip())
                    elif exc_type:
                        parts.append(str(exc_type).strip())
                    if node_type or node_id:
                        node_str = f"node {node_id or '?'}: {node_type or '?'}"
                        if parts:
                            return f"{parts[0]} ({node_str})"
                        return f"Error in {node_str}"
                    if parts:
                        return parts[0]
                elif event == "execution_interrupted":
                    payload = payload if isinstance(payload, dict) else {}
                    node_type = payload.get("node_type")
                    node_id = payload.get("node_id")
                    if node_type or node_id:
                        return f"Execution interrupted at node {node_id or '?'}: {node_type or '?'}"
                    return "Execution interrupted"
            elif isinstance(msg, dict):
                exc_msg = msg.get("exception_message") or msg.get("message")
                if exc_msg:
                    return str(exc_msg).strip()
            elif isinstance(msg, str) and msg.strip():
                return msg.strip()

    return "ComfyUI execution failed"



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
            if not preflight.get("comfy_online", True):
                # Try auto-launching ComfyUI if available on the local machine
                try:
                    from engine.system.setup import comfyui_manager
                    if comfyui_manager.is_installed():
                        logger.info("ComfyUI is offline. Attempting automated startup...")
                        res = comfyui_manager.ensure_running(timeout_s=15.0)
                        if res.get("running"):
                            preflight = self.registry.preflight(ART_WORKFLOW_ID)
                            if preflight["ready"]:
                                self._ready = True
                                return
                except Exception as e:
                    logger.warning("Could not auto-launch ComfyUI: %s", e)
                raise ComfyImageGenerationError(
                    f"ComfyUI is offline or unreachable at {self.client.base_url}. Please launch ComfyUI to generate images."
                )
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
            history_data = self.client.history(prompt_id)
            record = history_data.get(prompt_id, history_data) if isinstance(history_data, dict) else None
            err = _extract_history_error(record)
            if err:
                raise ComfyImageGenerationError(f"ComfyUI execution failed: {err}")
            images = (collect or _history_images)(history_data, prompt_id)
            if images:
                ref = images[0]
                return self.client.download_output(ref["filename"], ref["subfolder"], ref["type"]), prompt_id, ref
            if progress:
                progress(min(0.9, 0.12 + (time.monotonic() - started) / timeout * 0.75), "Waiting for ComfyUI output")
            time.sleep(POLL_SECONDS)
        raise ArtTimeoutError(f"ComfyUI did not produce an image within {timeout:.0f}s")

    def _resolve_reference(self, item: Path | str | bytes) -> str:
        """One reference image into a ComfyUI-loadable name. Bytes and existing paths are uploaded into ComfyUI's input
        folder (name derived from content, so reruns reuse the upload); a bare filename is passed through unchanged —
        it must already live in ComfyUI's input folder (e.g. a Character Vault sheet)."""
        if isinstance(item, bytes):
            return self.client.upload_image_bytes(item)
        if isinstance(item, Path):
            return self.client.upload_image(item)
        if isinstance(item, str):
            p = Path(item)
            if p.is_file():
                return self.client.upload_image(p)
            return item
        raise ValueError(f"Unsupported reference_image type: {type(item)}")

    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = "",
        width: int = 1344,
        height: int = 768,
        seed: int | None = None,
        prefix: str = "panelflow_art",
        reference_image: Path | str | bytes | None = None,
        *,
        reference_images: list[Path | str | bytes] | None = None,
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

        ref_image_name: str | None = None
        if reference_image is not None:
            ref_image_name = self._resolve_reference(reference_image)

        ref_image_names: list[str] | None = None
        if reference_images is not None:
            ref_image_names = [self._resolve_reference(item) for item in reference_images]

        patched = _patch_workflow(
            workflow,
            metadata["patch_slots"],
            prompt,
            negative_prompt,
            width,
            height,
            seed,
            prefix,
            reference_image=ref_image_name,
            reference_images=ref_image_names,
        )
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
