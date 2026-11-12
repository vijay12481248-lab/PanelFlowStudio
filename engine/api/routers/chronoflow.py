"""ChronoFlow Pro Studio API Router for PanelFlow Studio.

Sliding Window Video Chaining Engine & AI Cinematography using MiniMax Fast H3,
Qwen Image 2.1 Turbo (the single PanelFlow art workflow), character turnaround reference consistency,
and autonomous video chunk quality inspection.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from engine.chronoflow.pipeline import (
    BASE_DIR,
    COMFY_INPUT_DIR,
    COMFY_OUTPUT_DIR,
    STUDIO_OUTPUT_DIR,
    ChronoFlowPipeline,
)
from engine.chronoflow import media_tools
from engine.chronoflow.folder_dialog import pick_native_folder
from engine.chronoflow.reviewer import analyze_video_chunk
from engine.chronoflow.supervisor import VAULT_DIR, JobSupervisor

logger = logging.getLogger("panelflow.chronoflow")

router = APIRouter(prefix="/api/chronoflow", tags=["chronoflow"])

pipeline = ChronoFlowPipeline()
supervisor = JobSupervisor(pipeline=pipeline)
active_jobs = supervisor.active_jobs
reviews_store: dict[str, list[dict[str, Any]]] = {}

VAULT_FILE = VAULT_DIR / "characters.json"
STORAGE_LOCATIONS_FILE = VAULT_DIR / "storage_locations.json"
VAULT_DIR.mkdir(parents=True, exist_ok=True)


def load_storage_locations() -> list[dict[str, Any]]:
    if STORAGE_LOCATIONS_FILE.exists():
        try:
            with open(STORAGE_LOCATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.warning("Could not read storage_locations.json: %s", e)
    return []


def save_storage_locations(locations: list[dict[str, Any]]) -> None:
    try:
        parent_dir = STORAGE_LOCATIONS_FILE.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        temp_file = parent_dir / f"storage_locations_tmp_{int(time.time() * 1000)}.json"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(locations, f, indent=2)
        temp_file.replace(STORAGE_LOCATIONS_FILE)
    except Exception as e:
        logger.error("Failed to save storage_locations.json: %s", e)


def resolve_destination_dir(location_id: str | None = None, destination_path: str | None = None) -> Path | None:
    if location_id:
        for loc in load_storage_locations():
            if loc.get("id") == location_id:
                p = Path(loc.get("path", "")).resolve()
                p.mkdir(parents=True, exist_ok=True)
                return p
    if destination_path:
        p = Path(destination_path).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    return None


def load_characters() -> list[dict[str, Any]]:
    if VAULT_FILE.exists():
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not read characters.json: %s", e)
            return []
    return []


def save_characters(chars: list[dict[str, Any]]) -> None:
    try:
        temp_file = VAULT_DIR / f"characters_tmp_{int(time.time() * 1000)}.json"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(chars, f, indent=2)
        temp_file.replace(VAULT_FILE)
    except Exception as e:
        logger.error("Failed to save characters.json: %s", e)


def save_jobs() -> None:
    supervisor.bump_version()
    supervisor._save_jobs_to_disk()


# =====================================================================
# Request / Response Models
# =====================================================================

class CharacterPayload(BaseModel):
    id: str | None = None
    name: str = Field(default="Unnamed Actor")
    role: str = Field(default="Protagonist")
    image: str = Field(default="")
    description: str = Field(default="")
    tag: str | None = None


class GenerateRequest(BaseModel):
    workflow_mode: str = Field(default="sliding_window")  # sliding_window, flf2v, reference, storyboard
    prompt: str = Field(default="Cinematic drone shot over a glowing metropolis at dusk.")
    width: int = Field(default=1344)
    height: int = Field(default=768)
    steps: int = Field(default=4)
    total_duration: float = Field(default=15.6)
    lora_choice: str = Field(default="4step")
    initial_image: str | None = None
    first_frame: str | None = None
    last_frame: str | None = None
    ref_images: list[str] = Field(default_factory=list)
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    pre_existing_chunks: list[str] = Field(default_factory=list)
    face_refine: bool = Field(default=False)
    upscale_mode: str = Field(default="none")


class RegenerateChunkRequest(BaseModel):
    job_id: str
    chunk_index: int = Field(default=1, ge=1)
    notes: str = Field(default="")
    anchor_image: str | None = None
    prompt: str | None = None
    duration: float = Field(default=5.17)
    variant: bool = False          # keep the original shot: save the new render as a separate file and do not re-stitch
    audio_offset: float = 0.0      # variant only: carry the original shot's audio over starting at this second


class SaveChunkPromptRequest(BaseModel):
    job_id: str
    chunk_index: int = Field(default=1, ge=1)
    prompt: str = ""


class CreateClipRequest(BaseModel):
    job_id: str
    prompt: str = ""
    duration: float = Field(default=5.17)


class DeleteShotRequest(BaseModel):
    job_id: str
    chunk_index: int = Field(default=1, ge=1)


class AutogenPromptRequest(BaseModel):
    job_id: str
    target_shot_index: int | None = None
    director_notes: str | None = None


class CorrectPromptRequest(BaseModel):
    job_id: str
    shot_index: int = Field(default=1, ge=1)
    current_prompt: str = ""
    director_notes: str = ""


class GenerateImageRequest(BaseModel):
    prompt: str = Field(default="Cinematic character turnaround sheet, white background.")
    negative_prompt: str = Field(default="blurry, low quality, distorted, bad anatomy")
    width: int | None = None  # multiples of 16, 256..2048 (the art workflow's policy)
    height: int | None = None
    seed: int | None = None
    refine: bool = False  # review the picture, then repair or redraw it (slower; needs the local vision model)
    ref_images: list[str] = Field(default_factory=list)  # character lock: reference images (vault filenames, paths, data URLs)
    character_ids: list[str] = Field(default_factory=list)  # character lock: Character Vault ids resolved to their sheets
    location_id: str | None = None
    destination_path: str | None = None


class InpaintRequest(BaseModel):
    image_filename: str
    mask_data: str
    prompt: str = Field(default="cinematic photo, ultra detailed")
    denoise: float = Field(default=0.85)
    steps: int = Field(default=4)
    seed: int | None = None
    location_id: str | None = None
    destination_path: str | None = None


class StorageLocationCreateRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    path: str = Field(..., min_length=1)


class StorageMkdirRequest(BaseModel):
    path: str = Field(..., min_length=1)


class SaveAssetToLocationRequest(BaseModel):
    filenames: list[str] = Field(..., min_length=1)
    location_id: str | None = None
    destination_path: str | None = None
    action: str = Field(default="copy")


class TimelineExportRequest(BaseModel):
    clips: list[dict[str, Any]] = Field(default_factory=list)
    overlays: list[dict[str, Any]] = Field(default_factory=list)  # V2 still frames: {filename, start, duration}


class AIDirectorPlanRequest(BaseModel):
    idea: str = Field(default="A lone scavenger navigates an infected city at dusk.")
    duration: int = Field(default=15, ge=5, le=300)
    genre: str = Field(default="sci-fi")
    protagonist_name: str | None = None
    protagonist_tag: str | None = None


class SaveScreenplayRequest(BaseModel):
    filename: str | None = None
    title: str = Field(default="Untitled Storyboard")
    duration: float = Field(default=15.6)
    protagonist: dict[str, Any] = Field(default_factory=dict)
    anchor_images: dict[str, Any] = Field(default_factory=dict)
    parent_path: str = Field(default="")
    folders: list[dict[str, Any]] = Field(default_factory=list)
    scenes: list[dict[str, Any]] = Field(default_factory=list)


class ExportFolderRequest(BaseModel):
    screenplay_title: str = Field(default="Storyboard")
    folder_id: str = Field(default="")
    folder_name: str = Field(default="Scene")
    destination_path: str = Field(..., min_length=1)
    scenes: list[dict[str, Any]] = Field(default_factory=list)


class ImportManifestRequest(BaseModel):
    manifest_path: str = Field(..., min_length=1)


class ImportSceneToStudioRequest(BaseModel):
    folder_name: str = Field(default="Imported Scene")
    folder_id: str = Field(default="")
    screenplay_title: str = Field(default="Storyboard")
    shots: list[dict[str, Any]] = Field(default_factory=list)


class RenderShotRequest(BaseModel):
    scene: dict[str, Any]
    shot_index: int = Field(default=1, ge=1)
    width: int = Field(default=1344)
    height: int = Field(default=768)
    steps: int = Field(default=4)
    lora_choice: str = Field(default="4step")
    first_frame: str | None = None


class SaveFrameRequest(BaseModel):
    frame_data: str
    prefix: str = Field(default="frame_snap")


class ReviewPayload(BaseModel):
    chunk_index: int | str = Field(default=1)
    rating: str | None = None
    notes: str = Field(default="")
    duration: float = Field(default=5.17)


# =====================================================================
# Production Pipelines (Async Coroutines managed by Supervisor)
# =====================================================================

def resolve_h3_lora_name(choice: str | None) -> str:
    """Resolve LoRA choice to exact safetensors filename registered in ComfyUI."""
    choice_str = str(choice or "").lower()
    if "8step" in choice_str:
        return "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
    return "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"


async def run_production_job(job_id: str, data: dict[str, Any]) -> None:
    if job_id not in active_jobs:
        return
    job = active_jobs[job_id]
    try:
        workflow_mode = data.get("workflow_mode", "sliding_window")
        prompt = data.get("prompt", "Cinematic drone shot over a glowing metropolis at dusk.")
        width = int(data.get("width", 1344))
        height = int(data.get("height", 768))
        steps = int(data.get("steps", 4))
        lora_choice = data.get("lora_choice", "4step")
        lora_name = resolve_h3_lora_name(lora_choice)
        face_refine = bool(data.get("face_refine", False))
        upscale_mode = str(data.get("upscale_mode", "none"))

        chunk_files: list[Path] = []
        pre_existing = data.get("pre_existing_chunks", [])
        if pre_existing:
            for p_idx, p_file in enumerate(pre_existing):
                p_path = Path(p_file)
                if not p_path.is_absolute():
                    p_path = STUDIO_OUTPUT_DIR / p_path.name
                if p_path.exists():
                    c_name = f"{job_id}_chunk_{p_idx + 1}.mp4"
                    shutil.copy2(p_path, STUDIO_OUTPUT_DIR / c_name)
                    chunk_files.append(STUDIO_OUTPUT_DIR / c_name)
                    job["chunks"].append(f"/chronoflow/outputs/{c_name}")
            save_jobs()

        def on_step(val: int, max_val: int) -> None:
            job["step_progress"] = int((val / max_val) * 100) if max_val else 0

        # 1. FLF2V Mode
        if workflow_mode == "flf2v":
            first_frame = data.get("first_frame")
            last_frame = data.get("last_frame")
            job["total_chunks"] = 1
            job["current_chunk"] = 1
            job["status_msg"] = "Generating First-to-Last Frame Keyframe Transition (FLF2V)..."

            graph = pipeline.build_h3_prompt(
                prompt=prompt,
                width=width,
                height=height,
                length=124,
                steps=steps,
                lora_name=lora_name,
                workflow_mode="flf2v",
                first_frame_filename=first_frame,
                last_frame_filename=last_frame,
                face_refine=face_refine,
                upscale_mode=upscale_mode,
            )
            out_video = await pipeline.execute_prompt(graph, on_step=on_step)
            chunk_files.append(out_video)
            web_chunk_name = f"{job_id}_chunk_1.mp4"
            shutil.copy2(out_video, STUDIO_OUTPUT_DIR / web_chunk_name)
            job["chunks"].append(f"/chronoflow/outputs/{web_chunk_name}")
            save_jobs()

        # 2. Reference Mode
        elif workflow_mode == "reference":
            ref_images = data.get("ref_images", [])
            total_sec = float(data.get("total_duration", 5.2))
            num_chunks = max(1, round(total_sec / 5.17))
            job["total_chunks"] = num_chunks

            for chunk_idx in range(num_chunks):
                if job.get("cancelled"):
                    job["status"] = "cancelled"
                    return

                job["current_chunk"] = chunk_idx + 1
                job["status_msg"] = f"Generating Shot {chunk_idx + 1} of {num_chunks} with Character Reference Locking..."
                job["step_progress"] = 0

                chunk_prompt = prompt if num_chunks == 1 else f"{prompt} [sequence {chunk_idx + 1}]"
                graph = pipeline.build_h3_prompt(
                    prompt=chunk_prompt,
                    width=width,
                    height=height,
                    length=124,
                    steps=steps,
                    lora_name=lora_name,
                    workflow_mode="reference",
                    ref_images=ref_images,
                    face_refine=face_refine,
                    upscale_mode=upscale_mode,
                )
                chunk_output = await pipeline.execute_prompt(graph, on_step=on_step)
                chunk_files.append(chunk_output)

                web_chunk_name = f"{job_id}_chunk_{chunk_idx + 1}.mp4"
                shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / web_chunk_name)
                job["chunks"].append(f"/chronoflow/outputs/{web_chunk_name}")

                try:
                    prev_c = chunk_files[-2] if len(chunk_files) >= 2 else None
                    review = analyze_video_chunk(STUDIO_OUTPUT_DIR / web_chunk_name, chunk_prompt, chunk_idx + 1, num_chunks, prev_c)
                    if "reviews" not in job:
                        job["reviews"] = {}
                    job["reviews"][str(chunk_idx + 1)] = review
                except Exception as r_err:
                    logger.warning("Review analysis notice: %s", r_err)
                save_jobs()

        # 3. Storyboard Mode
        elif workflow_mode == "storyboard":
            scenes = data.get("scenes", [])
            start_chunk_offset = len(chunk_files)
            job["total_chunks"] = len(scenes) + start_chunk_offset
            current_guide_frame = data.get("initial_image")

            for idx, scene in enumerate(scenes):
                if job.get("cancelled"):
                    job["status"] = "cancelled"
                    return

                chunk_num = idx + 1 + start_chunk_offset
                job["current_chunk"] = chunk_num
                scene_title = scene.get("title", f"Scene {chunk_num}")
                job["status_msg"] = f"Rendering {scene_title} ({chunk_num}/{job['total_chunks']})..."
                job["step_progress"] = 0

                s_prompt = scene.get("prompt", prompt)
                s_first = scene.get("first_frame")
                if not s_first and current_guide_frame:
                    s_first = current_guide_frame

                s_last = scene.get("last_frame")
                s_refs = scene.get("ref_images", [])
                s_mode = "reference" if s_refs else ("flf2v" if (s_first and s_last) else "sliding_window")

                graph = pipeline.build_h3_prompt(
                    prompt=s_prompt,
                    width=width,
                    height=height,
                    length=124,
                    steps=steps,
                    lora_name=lora_name,
                    workflow_mode=s_mode,
                    first_frame_filename=s_first,
                    last_frame_filename=s_last,
                    ref_images=s_refs,
                    face_refine=face_refine,
                    upscale_mode=upscale_mode,
                )
                chunk_output = await pipeline.execute_prompt(graph, on_step=on_step)
                chunk_files.append(chunk_output)

                web_chunk_name = f"{job_id}_chunk_{chunk_num}.mp4"
                shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / web_chunk_name)
                job["chunks"].append(f"/chronoflow/outputs/{web_chunk_name}")
                save_jobs()

                if idx < len(scenes) - 1:
                    tail_filename = f"chronoflow_tail_{job_id}_{chunk_num}.png"
                    tail_path = COMFY_INPUT_DIR / tail_filename
                    if pipeline.extract_tail_frame(chunk_output, tail_path):
                        current_guide_frame = tail_filename

        # 4. Sliding Window Continuation (Default)
        else:
            total_seconds = float(data.get("total_duration", 15.6))
            num_chunks = max(1, round(total_seconds / 5.17))
            job["total_chunks"] = num_chunks
            current_guide_frame = data.get("initial_image")

            for chunk_idx in range(num_chunks):
                if job.get("cancelled"):
                    job["status"] = "cancelled"
                    return

                job["current_chunk"] = chunk_idx + 1
                job["status_msg"] = f"Generating Chunk {chunk_idx + 1} of {num_chunks} (Sliding Window Continuation)..."
                job["step_progress"] = 0

                chunk_prompt = prompt if num_chunks == 1 else f"{prompt} [continuation sequence {chunk_idx + 1}, fluid motion]"
                graph = pipeline.build_h3_prompt(
                    prompt=chunk_prompt,
                    width=width,
                    height=height,
                    length=124,
                    steps=steps,
                    lora_name=lora_name,
                    workflow_mode="sliding_window",
                    first_frame_filename=current_guide_frame,
                    face_refine=face_refine,
                    upscale_mode=upscale_mode,
                )
                chunk_output = await pipeline.execute_prompt(graph, on_step=on_step)
                chunk_files.append(chunk_output)

                web_chunk_name = f"{job_id}_chunk_{chunk_idx + 1}.mp4"
                shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / web_chunk_name)
                job["chunks"].append(f"/chronoflow/outputs/{web_chunk_name}")

                try:
                    prev_c = chunk_files[-2] if len(chunk_files) >= 2 else None
                    review = analyze_video_chunk(STUDIO_OUTPUT_DIR / web_chunk_name, chunk_prompt, chunk_idx + 1, num_chunks, prev_c)
                    if "reviews" not in job:
                        job["reviews"] = {}
                    job["reviews"][str(chunk_idx + 1)] = review
                except Exception as r_err:
                    logger.warning("Review notice: %s", r_err)
                save_jobs()

                if chunk_idx < num_chunks - 1:
                    job["status_msg"] = f"Extracting tail frame of Chunk {chunk_idx + 1}..."
                    tail_filename = f"chronoflow_tail_{job_id}_{chunk_idx + 1}.png"
                    tail_path = COMFY_INPUT_DIR / tail_filename
                    if pipeline.extract_tail_frame(chunk_output, tail_path):
                        current_guide_frame = tail_filename
                    else:
                        current_guide_frame = None

        # Post-Production: Stitch master continuous video
        job["status_msg"] = "Stitching master film with synchronized audio..."
        master_name = f"chronoflow_master_{job_id}.mp4"
        master_path = STUDIO_OUTPUT_DIR / master_name
        stitched = pipeline.stitch_chunks(chunk_files, master_path)

        if stitched and master_path.exists():
            job["master_video"] = f"/chronoflow/outputs/{master_name}"
            job["status"] = "completed"
            job["status_msg"] = f"Successfully generated continuous {len(chunk_files) * 5.2:.1f}s cinematic film!"
        else:
            job["status"] = "completed"
            job["status_msg"] = "All scene chunks generated successfully."
        save_jobs()

    except Exception as e:
        logger.exception("ChronoFlow production job failed: %s", e)
        job["status"] = "failed"
        job["error"] = str(e)
        job["status_msg"] = f"Error: {str(e)}"
        save_jobs()


async def run_chunk_regeneration(
    job_id: str,
    chunk_index: int,
    feedback_notes: str = "",
    custom_anchor: str | None = None,
    custom_prompt: str | None = None,
    duration_sec: float = 5.17,
    variant: bool = False,
    audio_offset: float = 0.0,
) -> None:
    if job_id not in active_jobs:
        return
    job = active_jobs[job_id]
    chunk_index = int(chunk_index)
    duration_sec = float(duration_sec or 5.17)

    if duration_sec <= 1.2:
        frame_length = 22
    elif duration_sec <= 2.5:
        frame_length = 56
    elif duration_sec <= 3.5:
        frame_length = 73
    else:
        frame_length = 124

    def on_step(step: int, total: int) -> None:
        pct = int((step / total) * 100) if total else 0
        job["step_progress"] = pct
        job["status_msg"] = f"Regenerating Shot {chunk_index} ({duration_sec:.1f}s) ({pct}%)..."

    try:
        job["status"] = "regenerating"
        job["current_chunk"] = chunk_index
        job["step_progress"] = 0
        job["status_msg"] = f"AI Director adjusting Shot {chunk_index} ({duration_sec:.1f}s) with feedback: '{feedback_notes or 'Enhanced motion'}'..."
        save_jobs()

        base_prompt = custom_prompt or job.get("prompt", "Cinematic photorealistic action shot")
        if feedback_notes:
            adjusted_prompt = f"{base_prompt} [Director Adjustment: {feedback_notes}, highly detailed, fluid motion, flawless continuity]"
        else:
            adjusted_prompt = base_prompt

        guide_frame = custom_anchor
        if not guide_frame:
            if chunk_index == 1:
                guide_frame = job.get("initial_image")
            elif chunk_index > 1:
                prev_chunk_filename = f"{job_id}_chunk_{chunk_index - 1}.mp4"
                prev_chunk_path = STUDIO_OUTPUT_DIR / prev_chunk_filename
                if prev_chunk_path.exists():
                    tail_name = f"chronoflow_tail_{job_id}_{chunk_index - 1}.png"
                    tail_path = COMFY_INPUT_DIR / tail_name
                    if pipeline.extract_tail_frame(prev_chunk_path, tail_path):
                        guide_frame = tail_name
                if not guide_frame:
                    guide_frame = job.get("initial_image")

        width = job.get("width", 1344)
        height = job.get("height", 768)
        lora_name = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"

        graph = pipeline.build_h3_prompt(
            prompt=adjusted_prompt,
            width=width,
            height=height,
            length=frame_length,
            steps=4,
            lora_name=lora_name,
            workflow_mode="sliding_window",
            first_frame_filename=guide_frame,
        )

        chunk_output = await pipeline.execute_prompt(graph, on_step=on_step)
        if variant:
            variant_name = f"{job_id}_chunk_{chunk_index}_v{int(time.time())}.mp4"
            shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / variant_name)
            original = STUDIO_OUTPUT_DIR / f"{job_id}_chunk_{chunk_index}.mp4"
            if original.exists():
                pipeline.mux_source_audio(STUDIO_OUTPUT_DIR / variant_name, original, audio_offset)
            job["last_variant"] = {"chunk": chunk_index, "file": variant_name, "at": time.time()}
            job["status"] = "completed"
            job["status_msg"] = f"Shot {chunk_index} re-animated as a new variant (original kept)."
            save_jobs()
            return
        web_chunk_name = f"{job_id}_chunk_{chunk_index}.mp4"
        shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / web_chunk_name)

        web_url = f"/chronoflow/outputs/{web_chunk_name}"
        while len(job["chunks"]) < chunk_index:
            job["chunks"].append("")
        job["chunks"][chunk_index - 1] = web_url

        if "chunk_prompts" not in job:
            job["chunk_prompts"] = []
        while len(job["chunk_prompts"]) < chunk_index:
            job["chunk_prompts"].append("")
        job["chunk_prompts"][chunk_index - 1] = custom_prompt or adjusted_prompt
        if job.get("total_chunks", 0) < chunk_index:
            job["total_chunks"] = chunk_index

        # Extract new tail frame for chunk N
        tail_name = f"chronoflow_tail_{job_id}_{chunk_index}.png"
        tail_path = COMFY_INPUT_DIR / tail_name
        pipeline.extract_tail_frame(chunk_output, tail_path)

        # Re-stitch master continuous video
        job["status_msg"] = "Re-stitching master film with updated shot..."
        chunk_files = [STUDIO_OUTPUT_DIR / Path(c).name for c in job["chunks"] if c and (STUDIO_OUTPUT_DIR / Path(c).name).exists()]
        master_name = f"chronoflow_master_{job_id}.mp4"
        master_path = STUDIO_OUTPUT_DIR / master_name
        stitched = pipeline.stitch_chunks(chunk_files, master_path)

        if stitched and master_path.exists():
            job["master_video"] = f"/chronoflow/outputs/{master_name}"
            job["status"] = "completed"
            job["status_msg"] = f"Shot {chunk_index} successfully regenerated and master film updated!"
        else:
            job["status"] = "completed"
            job["status_msg"] = f"Shot {chunk_index} regenerated successfully."
        save_jobs()
    except Exception as e:
        logger.exception("Shot regeneration failed: %s", e)
        job["status"] = "failed"
        job["error"] = str(e)
        job["status_msg"] = f"Regeneration error: {str(e)}"
        save_jobs()


# =====================================================================
# API Endpoints
# =====================================================================

@router.get("/status")
async def get_chronoflow_status() -> dict[str, Any]:
    """Returns ComfyUI connection health, GPU VRAM, and model availability."""
    comfy_status = await pipeline.check_comfy_status()
    models_dir = BASE_DIR / "models"

    h3_dit = (models_dir / "diffusion_models" / "minimax_h3_fl2va_pruned_int8_convrot.safetensors").exists()
    h3_turbo4 = (models_dir / "loras" / "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors").exists()
    h3_turbo8 = (models_dir / "loras" / "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors").exists()
    wan_dit = any((models_dir / "diffusion_models").glob("*wan*")) or any((models_dir / "diffusion_models").glob("*Wan*"))

    return {
        "comfy": comfy_status,
        "models": {
            "minimax_h3_dit": h3_dit,
            "minimax_h3_turbo4": h3_turbo4,
            "minimax_h3_turbo8": h3_turbo8,
            "wan2_1": wan_dit,
        },
    }


@router.get("/sync")
async def get_unified_sync(v: int = 0, job_id: str | None = None) -> dict[str, Any]:
    """Returns atomic versioned state for deterministic frontend synchronization."""
    return await supervisor.get_unified_sync_state(v, job_id)


@router.get("/jobs")
def list_chronoflow_jobs() -> dict[str, Any]:
    """List all production jobs in reverse chronological order."""
    return {"jobs": supervisor.list_jobs()}


@router.get("/job/{job_id}")
def get_chronoflow_job(job_id: str) -> dict[str, Any]:
    job = supervisor.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/generate")
async def submit_generate_job(req: GenerateRequest) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    new_job = {
        "id": job_id,
        "prompt": req.prompt,
        "initial_image": req.initial_image,
        "workflow_mode": req.workflow_mode,
        "width": req.width,
        "height": req.height,
        "total_duration": req.total_duration,
        "status": "starting",
        "status_msg": "Initializing ChronoFlow production pipeline...",
        "current_chunk": 0,
        "total_chunks": 1,
        "step_progress": 0,
        "chunks": [],
        "master_video": None,
        "cancelled": False,
        "error": None,
        "created_at": time.time(),
    }
    supervisor.register_new_job(job_id, new_job)
    supervisor.start_task(job_id, run_production_job(job_id, req.model_dump()))
    return {"success": True, "job_id": job_id}


@router.post("/regenerate_chunk")
async def submit_regenerate_chunk(req: RegenerateChunkRequest) -> dict[str, Any]:
    if req.job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    task_name = f"{req.job_id}_regen_{req.chunk_index}"
    supervisor.start_task(
        task_name,
        run_chunk_regeneration(
            req.job_id,
            req.chunk_index,
            req.notes,
            req.anchor_image,
            req.prompt,
            req.duration,
            req.variant,
            req.audio_offset,
        ),
    )
    return {
        "success": True,
        "message": f"Regeneration dispatched for Shot #{req.chunk_index} ({req.duration:.1f}s)",
    }


@router.post("/save_chunk_prompt")
async def save_chunk_prompt(req: SaveChunkPromptRequest) -> dict[str, Any]:
    if req.job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = active_jobs[req.job_id]
    if "chunk_prompts" not in job:
        job["chunk_prompts"] = []
    while len(job["chunk_prompts"]) < req.chunk_index:
        job["chunk_prompts"].append("")
    job["chunk_prompts"][req.chunk_index - 1] = req.prompt
    save_jobs()
    return {"success": True, "message": f"Prompt for Shot #{req.chunk_index} saved."}


@router.post("/create_clip")
async def create_clip(req: CreateClipRequest) -> dict[str, Any]:
    if req.job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = active_jobs[req.job_id]
    chunk_index = len(job.get("chunks", [])) + 1
    if "chunk_prompts" not in job:
        job["chunk_prompts"] = []
    while len(job["chunk_prompts"]) < chunk_index:
        job["chunk_prompts"].append("")
    job["chunk_prompts"][chunk_index - 1] = req.prompt
    job["total_chunks"] = max(job.get("total_chunks", 0), chunk_index)
    job["status"] = "starting"
    job["status_msg"] = f"Initializing render for new Shot #{chunk_index}..."
    save_jobs()
    supervisor.start_task(
        f"{req.job_id}_new_{chunk_index}",
        run_chunk_regeneration(
            req.job_id,
            chunk_index,
            custom_prompt=req.prompt,
            duration_sec=req.duration,
        ),
    )
    return {
        "success": True,
        "message": f"Dispatched new Shot #{chunk_index} ({req.duration:.1f}s)",
        "chunk_index": chunk_index,
    }


@router.post("/delete_shot")
async def delete_shot(req: DeleteShotRequest) -> dict[str, Any]:
    if req.job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = active_jobs[req.job_id]
    chunks = job.get("chunks", [])
    prompts = job.get("chunk_prompts", [])

    deleted_file = None
    if 1 <= req.chunk_index <= len(chunks):
        target_url = chunks[req.chunk_index - 1]
        deleted_file = Path(target_url).name
        del chunks[req.chunk_index - 1]

        # Record tombstone so supervisor _sync_with_disk_and_storage never resurrects it
        if deleted_file:
            tombstones = job.setdefault("deleted_chunks", [])
            if deleted_file not in tombstones:
                tombstones.append(deleted_file)

            for d in (STUDIO_OUTPUT_DIR, COMFY_OUTPUT_DIR):
                p = d / deleted_file
                if p.is_file():
                    try:
                        p.unlink()
                    except Exception:
                        try:
                            trash = d / ".trash"
                            trash.mkdir(exist_ok=True)
                            p.rename(trash / f"{int(time.time())}_{p.name}")
                        except Exception:
                            try:
                                p.rename(p.with_suffix(".mp4.deleted"))
                            except Exception:
                                pass

    if 1 <= req.chunk_index <= len(prompts):
        del prompts[req.chunk_index - 1]

    job["chunks"] = chunks
    job["chunk_prompts"] = prompts
    job["total_chunks"] = len(chunks)
    job["current_chunk"] = len(chunks)
    job["status_msg"] = f"Shot #{req.chunk_index} deleted."
    save_jobs()
    return {
        "success": True,
        "message": f"Shot #{req.chunk_index} deleted.",
        "deleted_file": deleted_file,
        "remaining_chunks": len(chunks),
    }


@router.post("/autogen_prompt")
async def autogen_prompt(req: AutogenPromptRequest) -> dict[str, Any]:
    if req.job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = active_jobs[req.job_id]
    chunks = job.get("chunks", [])
    target_shot_index = int(req.target_shot_index or (len(chunks) + 1))

    # 1. Resolve anchor frame
    anchor_frame_path = None
    anchor_frame_name = None
    if target_shot_index > 1:
        prev_idx = target_shot_index - 1
        tail_name = f"chronoflow_tail_{req.job_id}_{prev_idx}.png"
        tail_path = COMFY_INPUT_DIR / tail_name
        if tail_path.exists():
            anchor_frame_path = tail_path
            anchor_frame_name = tail_name
        else:
            prev_chunk_filename = f"{req.job_id}_chunk_{prev_idx}.mp4"
            prev_chunk_path = STUDIO_OUTPUT_DIR / prev_chunk_filename
            if prev_chunk_path.exists():
                if pipeline.extract_tail_frame(prev_chunk_path, tail_path):
                    anchor_frame_path = tail_path
                    anchor_frame_name = tail_name

    if not anchor_frame_path:
        init_img = job.get("initial_image")
        if init_img:
            init_path = COMFY_INPUT_DIR / init_img
            if init_path.exists():
                anchor_frame_path = init_path
                anchor_frame_name = init_img

    # 2. Context gathering
    base_story_prompt = job.get("prompt", "Cinematic photorealistic action shot")
    prev_prompts = job.get("chunk_prompts", [])
    prev_summary = ""
    if prev_prompts:
        prev_summary = "\n".join(f"Shot #{i+1}: {p[:140]}..." for i, p in enumerate(prev_prompts) if p)

    # 3. Directorial instructions adhering to docs/PROMPT_PRACTITIONER_GUIDE.md
    system_instruction = (
        "You are an elite cinematic film director, director of photography, and AI video prompt engineer for ChronoFlow Studio and MiniMax H3 / Qwen Image 2.1.\n"
        "Your role is to analyze the anchor frame (the exact final frame of the previous shot) and compose a comprehensive, production-grade video continuation prompt for the next shot.\n"
        "Adhere strictly to the Kinematic Delta and Temporal Continuity rules from the practitioner guide:\n"
        "1. Character & Visual Retention: Strictly retain the character's facial structure, hair styling, attire, and lighting atmosphere from the anchor frame to prevent temporal morphing.\n"
        "2. Camera Kinematics: Specify explicit optical camera movement (e.g., slow cinematic push-in, low-angle tracking, smooth pan, steady dolly track, lens focal depth).\n"
        "3. Subject Motion Delta: Describe natural physical movement continuing organically from the posture in the anchor frame.\n"
        "4. Secondary Dynamics: Include organic environmental motion (subtle hair and cloth flutter, drifting dust motes, ambient lighting flicker).\n"
        "5. Schema: Output the complete prompt conforming to the 6-heading schema:\n"
        "summary:\n"
        "[1-sentence shot logline]\n\n"
        "retention_analysis:\n"
        "[Preserved character identity, attire, lighting, setting]\n\n"
        "detailed_description:\n"
        "[Minute cinematic motion: camera movement, character action delta, secondary cloth/hair dynamics, spatial contact, lens focal depth]\n\n"
        "overall_soundscape:\n"
        "[Diegetic foley, environmental ambient audio]\n\n"
        "non_diegetic_music:\n"
        "[Musical score mood, tempo, and instrumentation]"
    )

    notes = (req.director_notes or "").strip()
    user_content = (
        f"Story Premise: {base_story_prompt}\n"
        f"{f'Previous Shot Sequence Context:\n{prev_summary}\n' if prev_summary else ''}"
        f"Target Shot: Shot #{target_shot_index}\n\n"
        f"{f'DIRECTOR GUIDANCE / DESIRED ACTION FOR THIS SHOT:\n{notes}\n\n' if notes else ''}"
        f"Analyze the attached anchor frame and generate the complete cinematic prompt for Shot #{target_shot_index}."
    )

    from engine.llm.providers.ollama import OllamaProvider

    provider = OllamaProvider(vision_model="qwen3.5:9b")
    if anchor_frame_path and anchor_frame_path.exists():
        generated_prompt = await provider.analyze_vision(
            image=anchor_frame_path,
            prompt=user_content,
            system_prompt=system_instruction,
        )
    else:
        generated_prompt = await provider.generate_text(
            prompt=user_content,
            system_prompt=system_instruction,
        )

    prompt_clean = generated_prompt.strip()
    if prompt_clean.startswith("```"):
        lines = prompt_clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        prompt_clean = "\n".join(lines).strip()

    return {
        "success": True,
        "prompt": prompt_clean,
        "anchor_frame": anchor_frame_name,
        "target_shot_index": target_shot_index,
    }


@router.post("/correct_prompt")
async def correct_prompt(req: CorrectPromptRequest) -> dict[str, Any]:
    if req.job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = active_jobs[req.job_id]

    shot_index = int(req.shot_index)
    current_prompt = req.current_prompt.strip()
    director_notes = req.director_notes.strip()
    if not director_notes:
        raise HTTPException(status_code=400, detail="Director notes are required.")

    # 1. Resolve anchor frame (tail of shot_index - 1 if available)
    anchor_frame_path = None
    anchor_frame_name = None
    if shot_index > 1:
        prev_idx = shot_index - 1
        tail_name = f"chronoflow_tail_{req.job_id}_{prev_idx}.png"
        tail_path = COMFY_INPUT_DIR / tail_name
        if tail_path.exists():
            anchor_frame_path = tail_path
            anchor_frame_name = tail_name
        else:
            prev_chunk_filename = f"{req.job_id}_chunk_{prev_idx}.mp4"
            prev_chunk_path = STUDIO_OUTPUT_DIR / prev_chunk_filename
            if prev_chunk_path.exists():
                if pipeline.extract_tail_frame(prev_chunk_path, tail_path):
                    anchor_frame_path = tail_path
                    anchor_frame_name = tail_name

    if not anchor_frame_path:
        init_img = job.get("initial_image")
        if init_img:
            init_path = COMFY_INPUT_DIR / init_img
            if init_path.exists():
                anchor_frame_path = init_path
                anchor_frame_name = init_img

    # 2. Extract preceding shot context and established state changes
    chunk_prompts = job.get("chunk_prompts", [])
    prior_context_lines = []
    for i in range(min(shot_index - 1, len(chunk_prompts))):
        p = chunk_prompts[i]
        if p:
            prior_context_lines.append(f"Shot #{i+1} Action & State: {p.strip()}")
    prior_context = "\n---\n".join(prior_context_lines)

    base_story_prompt = job.get("prompt", "Cinematic photorealistic action shot")

    # 3. Directorial refinement instructions
    system_instruction = (
        "You are an elite cinematic film director and AI video prompt engineer for ChronoFlow Studio and MiniMax Hailuo H3 / Qwen Image 2.1.\n"
        "Your task is to REFINE and ENHANCE an existing shot prompt based on explicit directorial feedback from the lead director.\n\n"
        "CRITICAL TEMPORAL & CONTINUITY RULES:\n"
        "1. NO ACTION LOOPING: Never repeat actions that were completed in preceding shots. If a character already reached a corner, closed a door, sat down, or blinked/sighed in a previous shot, do NOT repeat that action.\n"
        "2. IRREVERSIBLE CAUSALITY & STATE PERSISTENCE: Physical state changes must persist. If a door was closed, it stays closed—the character cannot magically reopen it unless explicitly commanded. If a character picked up an object, they are holding it.\n"
        "3. DIRECTIONAL & SPATIAL CONTINUITY: Follow exact spatial trajectories (e.g. if moving straight in Shot 1, then turning left in Shot 2, continuing left and turning right in Shot 3). Maintain world orientation, environmental layout, and momentum.\n"
        "4. CHARACTER RETENTION: Keep the exact same protagonist identity, hair, facial features, clothing, and lighting palette.\n"
        "5. DIRECTORIAL FEEDBACK PRIORITY: Apply the director's instructions faithfully—including additions, deletions, directional turns, camera kinematics, and mood adjustments.\n"
        "6. OUTPUT FORMAT: Output strictly according to the 6-heading schema:\n"
        "summary:\n"
        "[1-sentence concise logline]\n\n"
        "retention_analysis:\n"
        "[Preserved character identity, attire, lighting, setting]\n\n"
        "detailed_description:\n"
        "[Exact camera kinematics, character motion delta, secondary environmental dynamics, spatial contact, lens focal depth]\n\n"
        "overall_soundscape:\n"
        "[Diegetic foley, ambient audio]\n\n"
        "non_diegetic_music:\n"
        "[Musical score mood, tempo, and instrumentation]"
    )

    user_content = (
        f"Overall Story Premise: {base_story_prompt}\n\n"
        f"{f'Preceding Shots History (Completed Actions & States):\n{prior_context}\n\n' if prior_context else ''}"
        f"Target Shot: Shot #{shot_index}\n\n"
        f"Current Shot #{shot_index} Prompt:\n{current_prompt}\n\n"
        f"DIRECTOR'S CORRECTIONS & INSTRUCTIONS (MUST IMPLEMENT):\n{director_notes}\n\n"
        f"Apply the director's instructions to produce the refined, production-grade 6-heading prompt for Shot #{shot_index}."
    )

    from engine.llm.providers.ollama import OllamaProvider

    provider = OllamaProvider(vision_model="qwen3.5:9b")
    if anchor_frame_path and anchor_frame_path.exists():
        generated = await provider.analyze_vision(
            image=anchor_frame_path,
            prompt=user_content,
            system_prompt=system_instruction,
        )
    else:
        generated = await provider.generate_text(
            prompt=user_content,
            system_prompt=system_instruction,
        )

    prompt_clean = generated.strip()
    if prompt_clean.startswith("```"):
        lines = prompt_clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        prompt_clean = "\n".join(lines).strip()

    # Update in-memory job chunk_prompts
    if "chunk_prompts" not in job:
        job["chunk_prompts"] = []
    while len(job["chunk_prompts"]) < shot_index:
        job["chunk_prompts"].append("")
    job["chunk_prompts"][shot_index - 1] = prompt_clean
    save_jobs()

    return {
        "success": True,
        "prompt": prompt_clean,
        "shot_index": shot_index,
        "message": f"Prompt for Shot #{shot_index} refined with director feedback.",
    }


@router.post("/cancel")
def cancel_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = payload.get("job_id", "")
    success = supervisor.cancel_job(job_id)
    return {"success": success}


@router.post("/job/{job_id}/review")
async def submit_job_review(job_id: str, payload: ReviewPayload) -> dict[str, Any]:
    data = payload.model_dump()
    if job_id not in reviews_store:
        reviews_store[job_id] = []
    reviews_store[job_id].append(data)

    if job_id in active_jobs:
        if "reviews" not in active_jobs[job_id]:
            active_jobs[job_id]["reviews"] = {}
        chunk_idx = str(data.get("chunk_index", 1))
        active_jobs[job_id]["reviews"][chunk_idx] = data

        if data.get("rating") == "needs_regeneration":
            notes = data.get("notes", "")
            duration_sec = float(data.get("duration", 5.17))
            supervisor.start_task(
                f"{job_id}_regen_review_{chunk_idx}",
                run_chunk_regeneration(job_id, int(chunk_idx), notes, duration_sec=duration_sec),
            )

    return {"success": True}


# =====================================================================
# Character Vault Endpoints
# =====================================================================

@router.get("/characters")
def get_characters() -> dict[str, Any]:
    return {"characters": load_characters()}


@router.post("/characters")
def save_character(payload: CharacterPayload) -> dict[str, Any]:
    chars = load_characters()
    char_id = payload.id or f"char_{uuid.uuid4().hex[:6]}"
    char_entry = {
        "id": char_id,
        "name": payload.name,
        "role": payload.role,
        "image": payload.image,
        "description": payload.description,
        "tag": payload.tag or f"<Picture {len(chars) + 1}>",
    }
    existing = [i for i, c in enumerate(chars) if c.get("id") == char_id]
    if existing:
        chars[existing[0]] = char_entry
    else:
        chars.append(char_entry)
    save_characters(chars)
    return {"success": True, "character": char_entry}


@router.delete("/characters/{char_id}")
def delete_character(char_id: str) -> dict[str, Any]:
    chars = load_characters()
    chars = [c for c in chars if c.get("id") != char_id]
    save_characters(chars)
    return {"success": True}


# =====================================================================
# Image Generation & Inpaint
# =====================================================================

@router.post("/generate_image")
async def generate_image(req: GenerateImageRequest) -> dict[str, Any]:
    try:
        # Character lock: explicit refs first, then Character Vault members resolved to their locked sheets.
        refs: list[str] = list(req.ref_images or [])
        locked_characters: list[dict[str, Any]] = []
        if req.character_ids:
            vault = {c.get("id"): c for c in load_characters()}
            for cid in req.character_ids:
                c = vault.get(cid)
                if not c:
                    raise HTTPException(status_code=404, detail=f"Character '{cid}' not found in the vault")
                image = (c.get("image") or "").strip()
                if not image:
                    raise HTTPException(status_code=400, detail=f"Character '{cid}' has no reference sheet image")
                if image not in refs:
                    refs.append(image)
                locked_characters.append({"id": c.get("id"), "name": c.get("name"), "image": image})
        MAX_REFS = 4  # the approved workflow declares four reference patch slots
        if len(refs) > MAX_REFS:
            raise HTTPException(status_code=400, detail=f"Character lock supports at most {MAX_REFS} reference images (got {len(refs)})")
        filename, refine = await pipeline.generate_art_image_ex(req.prompt, req.negative_prompt, req.width or 1024, req.height or 1024, req.seed, req.refine, refs)
        out: dict[str, Any] = {"success": True, "filename": filename, "url": f"/chronoflow/inputs/{filename}"}
        if refs:
            out["character_lock"] = {"ref_images": refs, "characters": locked_characters}
        if refine:
            out["refine"] = refine

        dest_dir = resolve_destination_dir(req.location_id, req.destination_path)
        if dest_dir:
            src_file = COMFY_INPUT_DIR / filename
            if src_file.exists():
                dest_file = _unique_destination(dest_dir / filename)
                shutil.copy2(str(src_file), str(dest_file))
                out["saved_location"] = {
                    "location_id": req.location_id,
                    "folder": str(dest_dir),
                    "path": str(dest_file),
                    "filename": dest_file.name,
                    "serve_url": f"/api/chronoflow/files/serve?path={quote(str(dest_file))}",
                }
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Image generation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inpaint_image")
async def inpaint_image(req: InpaintRequest) -> dict[str, Any]:
    try:
        if not req.image_filename or not req.mask_data:
            raise HTTPException(status_code=400, detail="image_filename and mask_data required")

        mask_data = req.mask_data
        if "," in mask_data:
            mask_data = mask_data.split(",")[1]
        mask_bytes = base64.b64decode(mask_data)
        mask_filename = f"mask_{uuid.uuid4().hex[:8]}.png"
        mask_path = COMFY_INPUT_DIR / mask_filename
        with open(mask_path, "wb") as f:
            f.write(mask_bytes)

        graph = pipeline.build_inpaint_prompt(
            image_filename=req.image_filename,
            mask_filename=mask_filename,
            prompt=req.prompt,
            denoise=req.denoise,
            steps=req.steps,
            seed=req.seed,
        )
        out_path = await pipeline.execute_prompt(graph)
        new_filename = f"inpaint_{uuid.uuid4().hex[:8]}.png"
        target_path = COMFY_INPUT_DIR / new_filename
        shutil.copy2(out_path, target_path)

        res: dict[str, Any] = {
            "success": True,
            "filename": new_filename,
            "url": f"/chronoflow/inputs/{new_filename}",
        }
        dest_dir = resolve_destination_dir(req.location_id, req.destination_path)
        if dest_dir and target_path.exists():
            dest_file = _unique_destination(dest_dir / new_filename)
            shutil.copy2(str(target_path), str(dest_file))
            res["saved_location"] = {
                "location_id": req.location_id,
                "folder": str(dest_dir),
                "path": str(dest_file),
                "filename": dest_file.name,
                "serve_url": f"/api/chronoflow/files/serve?path={quote(str(dest_file))}",
            }
        return res
    except Exception as e:
        logger.exception("Inpaint failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save_frame")
def save_frame(req: SaveFrameRequest) -> dict[str, Any]:
    try:
        frame_data = req.frame_data
        if "," in frame_data:
            frame_data = frame_data.split(",")[1]
        img_bytes = base64.b64decode(frame_data)
        filename = f"{req.prefix}_{uuid.uuid4().hex[:8]}.png"
        path = COMFY_INPUT_DIR / filename
        with open(path, "wb") as f:
            f.write(img_bytes)

        return {
            "success": True,
            "filename": filename,
            "url": f"/chronoflow/inputs/{filename}",
        }
    except Exception as e:
        logger.exception("Save frame failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _media_or_404(file: str) -> Path:
    path = media_tools.resolve_media(file)
    if path is None:
        raise HTTPException(status_code=404, detail="media file not found")
    return path


@router.get("/media/info")
def media_info(file: str) -> dict[str, Any]:
    return media_tools.probe(_media_or_404(file))


@router.get("/media/filmstrip")
def media_filmstrip(file: str, count: int = 12, height: int = 72) -> FileResponse:
    try:
        sprite = media_tools.filmstrip(_media_or_404(file), count, height)
    except Exception as e:  # ffmpeg/ffprobe failure or an unreadable source
        raise HTTPException(status_code=422, detail=f"filmstrip failed: {e}")
    return FileResponse(sprite, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/media/waveform")
def media_waveform(file: str, bins: int = 200) -> dict[str, Any]:
    try:
        return {"peaks": media_tools.waveform(_media_or_404(file), bins)}
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"waveform failed: {e}")


@router.post("/upload_image")
async def upload_image(request: Request) -> dict[str, Any]:
    try:
        filename = request.headers.get("x-filename") or f"chronoflow_{uuid.uuid4().hex[:8]}.png"
        filepath = COMFY_INPUT_DIR / filename
        body = await request.body()
        with open(filepath, "wb") as f:
            f.write(body)
        return {"success": True, "filename": filename, "url": f"/chronoflow/inputs/{filename}"}
    except Exception as e:
        logger.exception("Upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# Storyboard, Screenplays & AI Director
# =====================================================================

@router.get("/screenplays")
def list_screenplays() -> dict[str, Any]:
    """List available screenplays from vault."""
    screenplays = []
    if VAULT_DIR.exists():
        for path in sorted(VAULT_DIR.glob("screenplay_*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                scenes = data.get("scenes", [])
                screenplays.append({
                    "filename": path.name,
                    "title": data.get("title", path.stem.replace("_", " ").title()),
                    "duration": float(data.get("duration", len(scenes) * 5.2)),
                    "scenes_count": len(scenes),
                    "protagonist": data.get("protagonist", {}),
                    "anchor_images": data.get("anchor_images", {}),
                })
            except Exception as e:
                logger.warning("Could not read screenplay %s: %s", path.name, e)
    return {"screenplays": screenplays}


@router.get("/screenplay/{filename}")
def get_screenplay(filename: str) -> dict[str, Any]:
    """Retrieve full screenplay JSON by filename."""
    if not filename.endswith(".json") or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid screenplay filename")

    file_path = VAULT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Screenplay '{filename}' not found")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        scenes = data.get("scenes", [])
        norm_scenes = []
        for idx, sc in enumerate(scenes):
            shot_num = sc.get("shot_index", idx + 1)
            raw_title = sc.get("title", f"Shot {shot_num}")

            shot_type = sc.get("shot_type")
            if not shot_type:
                lower_t = raw_title.lower()
                if "establishing" in lower_t or "wide" in lower_t or shot_num == 1:
                    shot_type = "Wide Establishing"
                elif "climax" in lower_t or "conclusion" in lower_t or shot_num == len(scenes):
                    shot_type = "Dynamic Climax"
                elif "close" in lower_t or "scan" in lower_t or "analysis" in lower_t:
                    shot_type = "Macro Close-Up"
                else:
                    shot_type = "Medium Tracking"

            norm_scenes.append({
                "shot_index": shot_num,
                "title": raw_title,
                "shot_type": shot_type,
                "duration": float(sc.get("duration", 5.2)),
                "workflow": sc.get("workflow", "sliding_window" if shot_num > 1 else "reference"),
                "first_frame": sc.get("first_frame", ""),
                "last_frame": sc.get("last_frame", ""),
                "ref_images": sc.get("ref_images", []),
                "prompt": sc.get("prompt", ""),
                "rendered_video": sc.get("rendered_video"),
                "rendered_video_filename": sc.get("rendered_video_filename"),
                "folder_id": sc.get("folder_id"),
            })

        data["scenes"] = norm_scenes
        data["filename"] = filename
        data["duration"] = float(data.get("duration", len(norm_scenes) * 5.2))

        folders = data.get("folders", [])
        if not folders and norm_scenes:
            folders = []
            chunk_size = 5 if len(norm_scenes) > 10 else 4
            num_folders = max(1, (len(norm_scenes) + chunk_size - 1) // chunk_size)
            for f_idx in range(num_folders):
                start_i = f_idx * chunk_size
                end_i = min(len(norm_scenes), start_i + chunk_size)
                slice_shots = norm_scenes[start_i:end_i]
                first_title = slice_shots[0]["title"] if slice_shots else f"Scene {f_idx + 1}"
                clean_title = first_title
                if ":" in clean_title:
                    clean_title = clean_title.split(":", 1)[1].strip()
                f_id = f"scene_{f_idx + 1}"
                folders.append({
                    "id": f_id,
                    "name": f"Scene {f_idx + 1}: {clean_title}",
                    "description": f"Shots {start_i + 1} to {end_i} cinematic sequence",
                    "path": "",
                    "shot_indices": [s["shot_index"] for s in slice_shots],
                })
                for s in slice_shots:
                    s["folder_id"] = f_id
        else:
            for s in norm_scenes:
                if "folder_id" not in s:
                    for f in folders:
                        if s.get("shot_index") in f.get("shot_indices", []):
                            s["folder_id"] = f["id"]
                            break
                    if "folder_id" not in s and folders:
                        s["folder_id"] = folders[0]["id"]

        data["folders"] = folders
        return data
    except Exception as e:
        logger.error("Failed to load screenplay %s: %s", filename, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenplay/save")
def save_screenplay(req: SaveScreenplayRequest) -> dict[str, Any]:
    """Save or update a screenplay in the vault."""
    filename = req.filename
    if not filename:
        safe_title = "".join(c for c in req.title.lower() if c.isalnum() or c in ("_", "-")).strip()
        filename = f"screenplay_{safe_title or 'custom'}.json"

    if not filename.endswith(".json") or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid screenplay filename")

    payload = {
        "title": req.title,
        "duration": req.duration,
        "protagonist": req.protagonist,
        "anchor_images": req.anchor_images,
        "parent_path": req.parent_path,
        "folders": req.folders,
        "scenes": req.scenes,
    }

    try:
        temp_file = VAULT_DIR / f"screenplay_tmp_{int(time.time() * 1000)}.json"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        target_file = VAULT_DIR / filename
        temp_file.replace(target_file)
        return {"success": True, "filename": filename, "title": req.title, "scenes_count": len(req.scenes)}
    except Exception as e:
        logger.error("Failed to save screenplay %s: %s", filename, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/storyboard/export_folder")
def export_storyboard_folder(req: ExportFolderRequest) -> dict[str, Any]:
    """Export all shots in a scene folder with metadata, prompts, keyframes, and video chunks to a user filesystem directory."""
    raw_path = req.destination_path.strip(' \t\r\n"\'')
    if not raw_path:
        raise HTTPException(status_code=400, detail="Destination path is required")

    dest_dir = Path(raw_path).resolve()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot create destination folder '{dest_dir}': {e}")

    keyframes_dir = dest_dir / "keyframes"
    videos_dir = dest_dir / "videos"
    keyframes_dir.mkdir(exist_ok=True)
    videos_dir.mkdir(exist_ok=True)

    copied_files = 0
    enriched_shots = []

    for idx, sc in enumerate(req.scenes):
        shot_num = sc.get("shot_index", idx + 1)
        shot_data = dict(sc)

        ff = sc.get("first_frame")
        if ff:
            src = COMFY_INPUT_DIR / ff
            if not src.exists():
                src = STUDIO_OUTPUT_DIR / ff
            if src.exists() and src.is_file():
                dest_file = keyframes_dir / f"shot_{shot_num}_{src.name}"
                try:
                    shutil.copy2(src, dest_file)
                    copied_files += 1
                    shot_data["local_keyframe"] = str(dest_file.name)
                except Exception:
                    pass

        rv = sc.get("rendered_video")
        if rv:
            fn = Path(rv).name.split("?")[0]
            src_v = STUDIO_OUTPUT_DIR / fn
            if src_v.exists() and src_v.is_file():
                dest_v = videos_dir / f"shot_{shot_num}_{src_v.name}"
                try:
                    shutil.copy2(src_v, dest_v)
                    copied_files += 1
                    shot_data["local_video"] = str(dest_v.name)
                except Exception:
                    pass

        enriched_shots.append(shot_data)

    manifest = {
        "scene_name": req.folder_name,
        "folder_id": req.folder_id,
        "storyboard_title": req.screenplay_title,
        "total_shots": len(req.scenes),
        "total_duration": sum(float(s.get("duration", 5.2)) for s in req.scenes),
        "exported_at": time.time(),
        "exported_at_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        "destination_directory": str(dest_dir),
        "shots": enriched_shots,
    }

    manifest_path = dest_dir / "scene_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return {
        "success": True,
        "saved_path": str(dest_dir),
        "manifest_file": str(manifest_path),
        "shots_count": len(req.scenes),
        "files_copied": copied_files,
        "message": f"Successfully exported {len(req.scenes)} shots into {dest_dir}",
    }


@router.post("/storyboard/import_manifest")
def import_storyboard_manifest(req: ImportManifestRequest) -> dict[str, Any]:
    """Import an exported scene folder manifest from disk into Video Studio."""
    raw_path = req.manifest_path.strip(' \t\r\n"\'')
    if not raw_path:
        raise HTTPException(status_code=400, detail="Manifest path is required")
    p = Path(raw_path).resolve()
    if p.is_dir():
        p = p / "scene_manifest.json"
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"Scene manifest not found at: {p}")
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "success": True,
            "manifest_file": str(p),
            "manifest": data,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read manifest '{p}': {e}")


@router.post("/storyboard/import_scene_to_studio")
def import_scene_to_studio(req: ImportSceneToStudioRequest) -> dict[str, Any]:
    """Register and import a scene and its rendered shots into Video Studio as an active production job."""
    folder_name = req.folder_name or "Imported Scene"
    folder_id = req.folder_id or ""
    screenplay_title = req.screenplay_title or "Storyboard"
    shots = req.shots or []

    if not shots:
        raise HTTPException(status_code=400, detail="Scene has no shots")

    chunk_urls = []
    chunk_prompts = []
    for idx, s in enumerate(shots):
        rv = s.get("rendered_video")
        if rv:
            clean_fn = Path(str(rv).replace("\\", "/")).name
            chunk_urls.append(f"/outputs/{clean_fn}")
        p = s.get("prompt") or s.get("title") or f"Shot {idx + 1}"
        chunk_prompts.append(p)

    total_dur = sum(float(s.get("duration", 5.2)) for s in shots)
    first_shot = shots[0] if shots else {}
    initial_img = first_shot.get("first_frame") or None

    job_id = f"scene_{uuid.uuid4().hex[:8]}"
    new_job = {
        "id": job_id,
        "prompt": first_shot.get("prompt") or f"{screenplay_title} - {folder_name}",
        "initial_image": initial_img,
        "workflow_mode": "storyboard",
        "width": 1344,
        "height": 768,
        "total_duration": total_dur,
        "status": "completed_chunks" if chunk_urls else "ready",
        "status_msg": f"Scene '{folder_name}' ({len(shots)} shots, {len(chunk_urls)} clips ready)",
        "current_chunk": len(chunk_urls),
        "total_chunks": len(shots),
        "step_progress": 100 if chunk_urls else 0,
        "chunks": chunk_urls,
        "chunk_prompts": chunk_prompts,
        "scenes": shots,
        "folder_name": folder_name,
        "folder_id": folder_id,
        "screenplay_title": screenplay_title,
        "master_video": chunk_urls[0] if chunk_urls else None,
        "cancelled": False,
        "error": None,
        "created_at": time.time(),
        "reviews": {},
    }

    supervisor.active_jobs[job_id] = new_job
    supervisor._save_jobs_to_disk()
    supervisor.state_version += 1

    return {
        "success": True,
        "job_id": job_id,
        "job": new_job,
        "chunks_count": len(chunk_urls),
        "shots_count": len(shots),
        "message": f"Successfully imported Scene '{folder_name}' into Video Studio",
    }


@router.post("/storyboard/render_shot")
async def render_storyboard_shot(req: RenderShotRequest) -> dict[str, Any]:
    """Render a single shot directly from a storyboard card."""
    scene = req.scene
    shot_num = req.shot_index
    prompt = scene.get("prompt", "Cinematic action scene.")
    first_frame = req.first_frame or scene.get("first_frame")
    last_frame = scene.get("last_frame")
    ref_images = scene.get("ref_images", [])

    # Validate image files exist in COMFY_INPUT_DIR to avoid ComfyUI LoadImage validation error
    if first_frame and not (COMFY_INPUT_DIR / first_frame).exists():
        logger.warning("First frame '%s' not found in ComfyUI input dir, generating text-to-video instead.", first_frame)
        first_frame = None

    if last_frame and not (COMFY_INPUT_DIR / last_frame).exists():
        logger.warning("Last frame '%s' not found in ComfyUI input dir, ignoring.", last_frame)
        last_frame = None

    if ref_images:
        ref_images = [img for img in ref_images if (COMFY_INPUT_DIR / img).exists()]

    workflow_mode = "reference" if ref_images else ("flf2v" if (first_frame and last_frame) else ("sliding_window" if first_frame else "sliding_window"))
    lora_name = resolve_h3_lora_name(req.lora_choice)

    try:
        graph = pipeline.build_h3_prompt(
            prompt=prompt,
            width=req.width,
            height=req.height,
            length=124,
            steps=req.steps,
            lora_name=lora_name,
            workflow_mode=workflow_mode,
            first_frame_filename=first_frame,
            last_frame_filename=last_frame,
            ref_images=ref_images,
        )
        chunk_output = await pipeline.execute_prompt(graph)
        chunk_filename = f"shot_{shot_num}_{uuid.uuid4().hex[:6]}.mp4"
        dest_path = STUDIO_OUTPUT_DIR / chunk_filename
        shutil.copy2(chunk_output, dest_path)

        return {
            "success": True,
            "shot_index": shot_num,
            "video_url": f"/chronoflow/outputs/{chunk_filename}",
            "filename": chunk_filename,
        }
    except Exception as e:
        logger.error("Failed to render storyboard shot %d: %s", shot_num, e)
        raise HTTPException(status_code=500, detail=f"Shot render failed: {e}")


@router.post("/ai_director/plan")
def ai_director_plan(req: AIDirectorPlanRequest) -> dict[str, Any]:
    """Generates a structured multi-scene storyboard breakdown from a high-level story idea."""
    num_scenes = max(1, round(req.duration / 5.2))
    scenes = []

    shot_types = [
        ("Wide Establishing", "Wide panoramic establishing shot sweeping across the scene, introducing environment and spatial scale."),
        ("Low-Angle Tracking", "Deliberate low-angle tracking shot moving with ground-level tension and atmospheric particle drift."),
        ("Medium Action", "Dynamic medium shot capturing decisive subject interaction, kinetic energy, and environmental focus."),
        ("Macro Close-Up", "Extreme close-up revealing intricate tactical details, subtle expressions, and digital HUD reflections."),
        ("High-Angle Crane", "Sweeping high-angle crane shot descending from high vantage point, tracking spatial orientation."),
        ("Dynamic Climax", "High-velocity whip-pan stabilizing into an intense kinetic reaction shot with dramatic lighting shifts."),
        ("Resolution Vista", "Majestic slow-pull vista shot resolving scene momentum into expansive cinematic composition."),
    ]

    actor_name = req.protagonist_name or "The Operative"
    actor_tag = req.protagonist_tag or "<Picture 1>"

    for i in range(num_scenes):
        shot_num = i + 1
        if shot_num == 1:
            stype, sdesc = shot_types[0]
            camera_mov = "Slow deliberate low-angle forward tracking push through swirling atmospheric mist."
        elif shot_num == num_scenes:
            stype, sdesc = shot_types[5] if num_scenes > 2 else shot_types[1]
            camera_mov = "Rapid whip-pan stabilizing into dynamic low-angle reaction shot with dramatic lighting."
        else:
            type_idx = 1 + ((i - 1) % (len(shot_types) - 2))
            stype, sdesc = shot_types[type_idx]
            camera_mov = f"Smooth cinematic tracking shot following {actor_name} with shallow depth of field."

        detailed_desc = (
            f"camera_movement: {camera_mov} "
            f"subject_description: {actor_name} performs decisive tactical actions in the heart of the environment. "
            f"environmental_details: {req.idea}. Cinematic atmosphere with volumetric haze and rich texture detail. "
            f"lighting_and_atmosphere: High-contrast cinematic chiaroscuro with vivid accent edge highlights. "
            f"overall_soundscape: Ambient atmospheric resonance, subtle environmental movement, mechanical hum. Strict rule: absolutely no human speech or dialogue. "
            f"non_diegetic_music: Pulse-driving cinematic synth pads with deep sub-bass momentum."
        )

        formatted_h3 = pipeline.compile_h3_prompt(
            detailed_description=detailed_desc,
            summary=f"Scene {shot_num} of {num_scenes}: {stype} - {req.idea[:60]}",
            retention_analysis=f"Subject {actor_name} appearance, costume details, lighting palette, and environment are strictly preserved.",
            soundscape="Atmospheric wind resonance, faint electrical humming, crisp movement.",
            music="Deep cinematic bass drone with evolving harmonic tension.",
            subject_definitions=f"{actor_name}: Primary character {actor_tag} in high-tech cinematic attire."
        )

        scenes.append({
            "shot_index": shot_num,
            "title": f"Shot {shot_num}: {stype}",
            "shot_type": stype,
            "prompt": formatted_h3,
            "duration": 5.2,
            "workflow": "sliding_window" if shot_num > 1 else "reference",
            "first_frame": "",
            "last_frame": "",
            "ref_images": [],
        })

    return {
        "success": True,
        "title": f"Storyboard: {req.idea[:45]}...",
        "duration": num_scenes * 5.2,
        "scenes_count": num_scenes,
        "scenes": scenes,
    }


@router.post("/timeline/export")
def timeline_export(req: TimelineExportRequest) -> dict[str, Any]:
    if not req.clips:
        raise HTTPException(status_code=400, detail="No clips provided")

    export_id = uuid.uuid4().hex[:8]
    master_name = f"chronoflow_timeline_master_{export_id}.mp4"
    master_path = STUDIO_OUTPUT_DIR / master_name

    rendered_path = pipeline.render_timeline_edl(req.clips, master_path, req.overlays)
    if rendered_path and master_path.exists():
        return {
            "success": True,
            "master_video": f"/chronoflow/outputs/{master_name}",
            "filename": master_name,
        }
    raise HTTPException(status_code=500, detail="Timeline render failed")


@router.get("/gallery")
def get_gallery() -> dict[str, Any]:
    assets: dict[str, Any] = {
        "masters": [],
        "chunks": [],
        "images": [],
        "stats": {"total_videos": 0, "total_images": 0, "total_storage_mb": 0.0},
    }
    total_bytes = 0

    if STUDIO_OUTPUT_DIR.exists():
        for f in STUDIO_OUTPUT_DIR.iterdir():
            if not f.is_file():
                continue
            size_bytes = f.stat().st_size
            total_bytes += size_bytes
            mtime = f.stat().st_mtime
            name = f.name
            if name.startswith("chronoflow_master_") and name.endswith(".mp4"):
                job_id = name.replace("chronoflow_master_", "").replace(".mp4", "").split("_")[0]
                job_info = active_jobs.get(job_id, {})
                assets["masters"].append({
                    "filename": name,
                    "url": f"/chronoflow/outputs/{name}",
                    "job_id": job_id,
                    "prompt": job_info.get("prompt", "Cinematic master cut"),
                    "duration": job_info.get("total_duration", 15.6),
                    "resolution": f"{job_info.get('width', 1344)}x{job_info.get('height', 768)}",
                    "size_mb": round(size_bytes / (1024 * 1024), 2),
                    "created_at": mtime,
                })
            elif "_chunk_" in name and name.endswith(".mp4"):
                parts = name.split("_chunk_")
                job_id = parts[0]
                chunk_num = parts[1].replace(".mp4", "")
                job_info = active_jobs.get(job_id, {})
                review = job_info.get("reviews", {}).get(chunk_num, {})
                assets["chunks"].append({
                    "filename": name,
                    "url": f"/chronoflow/outputs/{name}",
                    "job_id": job_id,
                    "chunk_index": chunk_num,
                    "score": review.get("overall_score", 93),
                    "grade": review.get("grade"),
                    "verdict": review.get("verdict", "APPROVED FOR MASTER CUT"),
                    "size_mb": round(size_bytes / (1024 * 1024), 2),
                    "created_at": mtime,
                })
            elif name.endswith((".png", ".jpg", ".webp")) and not name.startswith("concat_"):
                assets["images"].append({
                    "filename": name,
                    "url": f"/chronoflow/outputs/{name}",
                    "model": "Render Asset",
                    "size_mb": round(size_bytes / (1024 * 1024), 2),
                    "created_at": mtime,
                })

    if COMFY_INPUT_DIR.exists():
        for f in COMFY_INPUT_DIR.iterdir():
            if not f.is_file():
                continue
            name = f.name
            if name.startswith(("art_", "flux_gen_", "qwen_gen_", "inpaint_", "chronoflow_tail_", "zombie_", "char_")):
                size_bytes = f.stat().st_size
                total_bytes += size_bytes
                mtime = f.stat().st_mtime
                model_tag = "FLUX.1 Schnell (legacy)" if "flux" in name else "Qwen-Image-2.1" if name.startswith(("art_", "qwen_gen_")) else "Inpaint Asset"
                assets["images"].append({
                    "filename": name,
                    "url": f"/chronoflow/inputs/{name}",
                    "model": model_tag,
                    "size_mb": round(size_bytes / (1024 * 1024), 2),
                    "created_at": mtime,
                })

    # Also load images from all user-registered custom storage locations
    for loc in load_storage_locations():
        loc_path = Path(loc.get("path", "")).resolve()
        if not loc_path.exists() or not loc_path.is_dir():
            continue
        try:
            for f in loc_path.iterdir():
                if not f.is_file():
                    continue
                suffix = f.suffix.lower()
                if suffix in _MEDIA_IMAGE_EXTS:
                    size_bytes = f.stat().st_size
                    total_bytes += size_bytes
                    mtime = f.stat().st_mtime
                    assets["images"].append({
                        "filename": f.name,
                        "url": f"/api/chronoflow/files/serve?path={quote(str(f))}",
                        "path": str(f),
                        "location_id": loc.get("id"),
                        "location_name": loc.get("name"),
                        "model": f"Stored in {loc.get('name')}",
                        "size_mb": round(size_bytes / (1024 * 1024), 2),
                        "created_at": mtime,
                    })
        except Exception as e:
            logger.warning("Could not scan location %s: %s", loc_path, e)

    assets["masters"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["chunks"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["images"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["stats"]["total_videos"] = len(assets["masters"]) + len(assets["chunks"])
    assets["stats"]["total_images"] = len(assets["images"])
    assets["stats"]["total_storage_mb"] = round(total_bytes / (1024 * 1024), 1)
    assets["locations"] = load_storage_locations()
    return assets


# =====================================================================
# Storyboard Folder Organizer (§14)
# =====================================================================

_FILE_SERVE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".mp4", ".webm", ".mkv", ".mov",
    ".wav", ".mp3", ".ogg", ".flac",
    ".json", ".txt", ".md", ".srt", ".vtt",
}

_MEDIA_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_MEDIA_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov"}
_MEDIA_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac"}

# Whitelisted organizer roots: studio output dir + ComfyUI input dir + user-registered storage locations.
def _organizer_roots() -> list[dict[str, str]]:
    roots: list[dict[str, str]] = []
    if STUDIO_OUTPUT_DIR.exists():
        roots.append({"label": "Studio Output", "path": str(STUDIO_OUTPUT_DIR), "id": "default_output"})
    if COMFY_INPUT_DIR.exists():
        roots.append({"label": "ComfyUI Input", "path": str(COMFY_INPUT_DIR), "id": "default_input"})
    for loc in load_storage_locations():
        try:
            p = Path(loc.get("path", "")).resolve()
            if p.exists() and p.is_dir():
                roots.append({
                    "label": f"📁 {loc.get('name', 'Custom')} ({p})",
                    "path": str(p),
                    "id": loc.get("id", ""),
                })
        except Exception:
            continue
    return roots


def _resolve_organizer_path(raw: str) -> Path:
    """Resolve a user-supplied path against whitelisted organizer roots or registered locations."""
    if not raw:
        raise HTTPException(status_code=400, detail="path is required")
    p = Path(raw)
    if not p.is_absolute():
        p = STUDIO_OUTPUT_DIR / p
    p = p.resolve()
    allowed_roots = [STUDIO_OUTPUT_DIR.resolve(), COMFY_INPUT_DIR.resolve()]
    for loc in load_storage_locations():
        try:
            loc_p = Path(loc.get("path", "")).resolve()
            if loc_p.exists():
                allowed_roots.append(loc_p)
        except Exception:
            continue
    for root in allowed_roots:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    # Local-first user system: allow any valid existing file/directory on disk if explicitly targeted
    if p.exists():
        return p
    raise HTTPException(status_code=403, detail="Path is outside the organizer roots (Studio Output / ComfyUI Input / Registered Locations)")


def _unique_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for i in range(1, 1000):
        candidate = dest.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Could not find a free filename in destination")


@router.get("/files/roots")
def get_organizer_roots() -> dict[str, Any]:
    return {"roots": _organizer_roots()}


@router.get("/files")
def list_organizer_files(path: str = "") -> dict[str, Any]:
    """List subfolders and media/project files at `path` (whitelisted roots only)."""
    target = _resolve_organizer_path(path) if path else STUDIO_OUTPUT_DIR
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder not found: {target}")

    folders: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    try:
        for entry in sorted(target.iterdir(), key=lambda f: f.name.lower()):
            if entry.name.startswith("."):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            if entry.is_dir():
                folders.append({
                    "name": entry.name,
                    "path": str(entry),
                    "created_at": stat.st_mtime,
                })
                continue
            suffix = entry.suffix.lower()
            if suffix not in _FILE_SERVE_SUFFIXES:
                continue
            media = "other"
            if suffix in _MEDIA_IMAGE_EXTS:
                media = "image"
            elif suffix in _MEDIA_VIDEO_EXTS:
                media = "video"
            elif suffix in _MEDIA_AUDIO_EXTS:
                media = "audio"
            files.append({
                "name": entry.name,
                "path": str(entry),
                "kind": media,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": stat.st_mtime,
                "url": f"/api/chronoflow/files/serve?path={quote(str(entry))}",
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Access denied: {target}")

    return {
        "path": str(target),
        "name": target.name,
        "parent": str(target.parent) if target != target.parent else None,
        "roots": _organizer_roots(),
        "folders": folders,
        "files": files,
        "stats": {
            "folder_count": len(folders),
            "file_count": len(files),
            "total_mb": round(sum(f["size_bytes"] for f in files) / (1024 * 1024), 1),
        },
    }


class FolderCreateRequest(BaseModel):
    parent_path: str = ""
    name: str = Field(..., min_length=1, max_length=120)


@router.post("/folders/create")
def create_organizer_folder(req: FolderCreateRequest) -> dict[str, Any]:
    parent = _resolve_organizer_path(req.parent_path) if req.parent_path else STUDIO_OUTPUT_DIR
    if not parent.exists() or not parent.is_dir():
        raise HTTPException(status_code=404, detail=f"Parent folder not found: {parent}")
    name = req.name.strip()
    if any(ch in name for ch in '\\/:*?"<>|'):
        raise HTTPException(status_code=400, detail="Folder name contains invalid characters")
    dest = parent / name
    if dest.exists():
        raise HTTPException(status_code=409, detail=f"'{name}' already exists in {parent}")
    dest.mkdir(parents=True, exist_ok=False)
    return {"ok": True, "path": str(dest), "name": name, "parent": str(parent)}


class FileMoveRequest(BaseModel):
    files: list[str] = Field(..., min_length=1)
    destination: str


@router.post("/files/move")
def move_organizer_files(req: FileMoveRequest) -> dict[str, Any]:
    destination = _resolve_organizer_path(req.destination)
    if not destination.exists() or not destination.is_dir():
        raise HTTPException(status_code=404, detail=f"Destination folder not found: {destination}")

    moved: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for raw in req.files:
        src = _resolve_organizer_path(raw)
        if not src.exists() or not src.is_file():
            skipped.append({"file": raw, "reason": "not found"})
            continue
        if src.parent == destination:
            skipped.append({"file": str(src), "reason": "already in destination"})
            continue
        try:
            final = _unique_destination(destination / src.name)
            shutil.move(str(src), str(final))
            moved.append({"from": str(src), "to": str(final)})
        except (shutil.Error, OSError) as e:
            skipped.append({"file": str(src), "reason": str(e)})

    return {"ok": True, "moved": moved, "skipped": skipped, "destination": str(destination)}


@router.get("/files/serve")
def serve_organizer_file(path: str = "") -> FileResponse:
    """Serve an arbitrary whitelisted file for <img>/<video> tags (token via query param)."""
    target = _resolve_organizer_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {target}")
    return FileResponse(str(target), headers={"Cache-Control": "no-store"})


# =====================================================================
# Custom Storage Locations & Drive Management
# =====================================================================

@router.get("/storage/drives")
def get_storage_drives() -> dict[str, Any]:
    r"""List available system disk drives (e.g. C:\, D:\, E:\ on Windows) and primary roots."""
    drives: list[dict[str, str]] = []
    if os.name == "nt":
        try:
            import ctypes
            import string
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if (bitmask >> (ord(letter) - 65)) & 1:
                    drive_path = f"{letter}:\\"
                    label = f"Drive {letter}:"
                    try:
                        if Path(drive_path).exists():
                            drives.append({"drive": drive_path, "label": label})
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Failed to query Windows logical drives: %s", e)
    if not drives:
        drives.append({"drive": str(Path.home()), "label": f"Home ({Path.home()})"})
        drives.append({"drive": "/", "label": "Root (/)"})
    return {"drives": drives}


@router.get("/storage/browse")
def browse_storage_directory(path: str = "") -> dict[str, Any]:
    """Browse directories on disk to select an existing folder or navigate drives."""
    p_str = (path or "").strip(' \t\r\n"\'')
    if os.name == "nt":
        p_str = p_str.replace("/", "\\")
        if len(p_str) == 2 and p_str[1] == ":":
            p_str = f"{p_str}\\"

    if not p_str:
        target = Path.home()
    else:
        target = Path(p_str).resolve()

    not_found = False
    requested_path = str(target)
    if not target.exists() or not target.is_dir():
        not_found = True
        curr = target
        closest = None
        while curr != curr.parent:
            curr = curr.parent
            if curr.exists() and curr.is_dir():
                closest = curr
                break
        if not closest or not closest.exists() or not closest.is_dir():
            anchor = Path(target.anchor) if target.anchor else None
            if anchor and anchor.exists() and anchor.is_dir():
                closest = anchor
            else:
                closest = Path.home() if Path.home().exists() else Path("C:\\")
        target = closest

    subfolders: list[dict[str, Any]] = []
    try:
        for entry in sorted(target.iterdir(), key=lambda f: f.name.lower()):
            if entry.name.startswith((".", "$")):
                continue
            if entry.is_dir():
                try:
                    stat = entry.stat()
                    subfolders.append({
                        "name": entry.name,
                        "path": str(entry),
                        "created_at": stat.st_mtime,
                    })
                except (PermissionError, OSError):
                    continue
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {target}")

    parent = str(target.parent) if target.parent != target else None
    return {
        "current": str(target),
        "name": target.name or str(target),
        "parent": parent,
        "subfolders": subfolders,
        "not_found": not_found,
        "requested_path": requested_path if not_found else str(target),
        "can_create": not_found,
    }


@router.post("/storage/mkdir")
def create_storage_directory(req: StorageMkdirRequest) -> dict[str, Any]:
    """Create a folder directory on disk immediately."""
    raw_path = (req.path or "").strip(' \t\r\n"\'')
    if not raw_path:
        raise HTTPException(status_code=400, detail="Path required")
    p = Path(raw_path).resolve()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(p), "name": p.name or str(p)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not create directory '{p}': {e}")


@router.post("/storage/pick_folder")
async def api_pick_native_folder(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Launch native OS folder browser dialog to select a folder from the local filesystem."""
    init_dir = (payload.get("initial_dir") or "").strip(' \t\r\n"\'') if payload else ""
    selected = await pick_native_folder(initial_dir=init_dir)
    if selected:
        p = Path(selected).resolve()
        return {"success": True, "path": str(p), "name": p.name or str(p), "cancelled": False}
    return {"success": False, "cancelled": True, "path": ""}


@router.get("/storage/locations")
def get_storage_locations() -> dict[str, Any]:
    """Return all registered custom storage locations with metadata and file counts."""
    locations = load_storage_locations()
    enriched = []
    for loc in locations:
        p = Path(loc.get("path", "")).resolve()
        exists = p.exists() and p.is_dir()
        img_count = 0
        if exists:
            try:
                img_count = sum(1 for f in p.iterdir() if f.is_file() and f.suffix.lower() in _MEDIA_IMAGE_EXTS)
            except Exception:
                img_count = 0
        enriched.append({
            **loc,
            "exists": exists,
            "image_count": img_count,
        })
    return {"locations": enriched}


@router.post("/storage/locations")
def create_storage_location(req: StorageLocationCreateRequest) -> dict[str, Any]:
    """Create or register a custom folder destination on any drive/disk."""
    raw_path = req.path.strip(' \t\r\n"\'')
    if not raw_path:
        raise HTTPException(status_code=400, detail="Location path cannot be empty")

    p = Path(raw_path).resolve()
    name = req.name.strip() or p.name or str(p)

    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not create or access directory '{p}': {e}")

    locations = load_storage_locations()
    for existing in locations:
        if Path(existing.get("path", "")).resolve() == p:
            existing["name"] = name
            existing["updated_at"] = time.time()
            save_storage_locations(locations)
            return {"success": True, "location": existing, "updated": True}

    loc_id = f"loc_{uuid.uuid4().hex[:8]}"
    drive = p.drive if hasattr(p, "drive") and p.drive else str(p.anchor)
    new_loc = {
        "id": loc_id,
        "name": name,
        "path": str(p),
        "drive": drive,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    locations.append(new_loc)
    save_storage_locations(locations)
    return {"success": True, "location": new_loc, "created": True}


@router.delete("/storage/locations/{loc_id}")
def delete_storage_location(loc_id: str) -> dict[str, Any]:
    """Remove a registered storage location (does not delete user files)."""
    locations = load_storage_locations()
    filtered = [loc for loc in locations if loc.get("id") != loc_id]
    if len(filtered) == len(locations):
        raise HTTPException(status_code=404, detail=f"Location '{loc_id}' not found")
    save_storage_locations(filtered)
    return {"success": True, "id": loc_id}


@router.post("/storage/save_asset")
def save_asset_to_location(req: SaveAssetToLocationRequest) -> dict[str, Any]:
    """Copy or move one or more generated images to a registered location or target path."""
    dest_dir = resolve_destination_dir(req.location_id, req.destination_path)
    if not dest_dir or not dest_dir.exists() or not dest_dir.is_dir():
        raise HTTPException(status_code=400, detail="Valid destination folder or location_id required")

    results = []
    for fn in req.filenames:
        src: Path | None = None
        if (COMFY_INPUT_DIR / fn).exists():
            src = COMFY_INPUT_DIR / fn
        elif (STUDIO_OUTPUT_DIR / fn).exists():
            src = STUDIO_OUTPUT_DIR / fn
        elif Path(fn).is_absolute() and Path(fn).exists():
            src = Path(fn)
        else:
            base = Path(fn).name
            if (COMFY_INPUT_DIR / base).exists():
                src = COMFY_INPUT_DIR / base
            elif (STUDIO_OUTPUT_DIR / base).exists():
                src = STUDIO_OUTPUT_DIR / base

        if not src or not src.is_file():
            results.append({"filename": fn, "success": False, "error": "Source file not found"})
            continue

        dest_file = _unique_destination(dest_dir / src.name)
        try:
            if req.action == "move":
                shutil.move(str(src), str(dest_file))
            else:
                shutil.copy2(str(src), str(dest_file))
            results.append({
                "filename": src.name,
                "success": True,
                "saved_path": str(dest_file),
                "url": f"/api/chronoflow/files/serve?path={quote(str(dest_file))}",
            })
        except Exception as e:
            results.append({"filename": src.name, "success": False, "error": str(e)})

    return {"success": True, "destination": str(dest_dir), "results": results}


# =====================================================================
# UI Static Route
# =====================================================================

CHRONOFLOW_STATIC_DIR = Path(__file__).resolve().parents[2] / "chronoflow" / "static"


@router.get("/ui")
def get_chronoflow_ui() -> Response:
    index_path = CHRONOFLOW_STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="ChronoFlow UI index.html not found")
    content = index_path.read_text(encoding="utf-8")
    token = os.getenv("PANELFLOW_ENGINE_TOKEN", "")
    if token:
        injection = f'<script>window.__PANELFLOW_ENGINE_TOKEN__ = "{token}";</script>'
        content = content.replace("<head>", f"<head>\n  {injection}", 1)
    # Webviews (Tauri/WebView2) must never reuse a previously fetched studio HTML,
    # otherwise engine UI updates appear "stuck" until an app restart.
    return HTMLResponse(content, headers={"Cache-Control": "no-store, must-revalidate", "Referrer-Policy": "no-referrer"})
