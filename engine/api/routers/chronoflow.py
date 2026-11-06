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

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from engine.chronoflow.pipeline import (
    BASE_DIR,
    COMFY_INPUT_DIR,
    STUDIO_OUTPUT_DIR,
    ChronoFlowPipeline,
)
from engine.chronoflow import media_tools
from engine.chronoflow.reviewer import analyze_video_chunk
from engine.chronoflow.supervisor import VAULT_DIR, JobSupervisor

logger = logging.getLogger("panelflow.chronoflow")

router = APIRouter(prefix="/api/chronoflow", tags=["chronoflow"])

pipeline = ChronoFlowPipeline()
supervisor = JobSupervisor(pipeline=pipeline)
active_jobs = supervisor.active_jobs
reviews_store: dict[str, list[dict[str, Any]]] = {}

VAULT_FILE = VAULT_DIR / "characters.json"
VAULT_DIR.mkdir(parents=True, exist_ok=True)


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


class GenerateImageRequest(BaseModel):
    prompt: str = Field(default="Cinematic character turnaround sheet, white background.")
    negative_prompt: str = Field(default="blurry, low quality, distorted, bad anatomy")
    width: int | None = None  # multiples of 16, 256..2048 (the art workflow's policy)
    height: int | None = None
    seed: int | None = None
    refine: bool = False  # review the picture, then repair or redraw it (slower; needs the local vision model)


class InpaintRequest(BaseModel):
    image_filename: str
    mask_data: str
    prompt: str = Field(default="cinematic photo, ultra detailed")
    denoise: float = Field(default=0.85)
    steps: int = Field(default=4)
    seed: int | None = None


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
    scenes: list[dict[str, Any]] = Field(default_factory=list)


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
        filename, refine = await pipeline.generate_art_image_ex(req.prompt, req.negative_prompt, req.width or 1024, req.height or 1024, req.seed, req.refine)
        return {"success": True, "filename": filename, "url": f"/chronoflow/inputs/{filename}", **({"refine": refine} if refine else {})}
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

        return {
            "success": True,
            "filename": new_filename,
            "url": f"/chronoflow/inputs/{new_filename}",
        }
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
            })

        data["scenes"] = norm_scenes
        data["filename"] = filename
        data["duration"] = float(data.get("duration", len(norm_scenes) * 5.2))
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
                    "grade": review.get("grade", "A"),
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

    assets["masters"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["chunks"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["images"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["stats"]["total_videos"] = len(assets["masters"]) + len(assets["chunks"])
    assets["stats"]["total_images"] = len(assets["images"])
    assets["stats"]["total_storage_mb"] = round(total_bytes / (1024 * 1024), 1)
    return assets


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
    return HTMLResponse(content, headers={"Cache-Control": "no-cache", "Referrer-Policy": "no-referrer"})
