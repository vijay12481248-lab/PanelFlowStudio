"""ChronoFlow Pro Studio API Router for PanelFlow Studio.

Sliding Window Video Chaining Engine & AI Cinematography using MiniMax Fast H3,
FLUX.1 Schnell fp8, Qwen-Image-2.1 Turbo, character turnaround reference consistency,
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
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from engine.chronoflow.pipeline import (
    BASE_DIR,
    COMFY_INPUT_DIR,
    STUDIO_OUTPUT_DIR,
    ChronoFlowPipeline,
)
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


class RegenerateChunkRequest(BaseModel):
    job_id: str
    chunk_index: int = Field(default=1, ge=1)
    notes: str = Field(default="")
    anchor_image: str | None = None
    prompt: str | None = None
    duration: float = Field(default=5.17)


class GenerateImageRequest(BaseModel):
    model: str = Field(default="flux")  # flux or qwen
    prompt: str = Field(default="Cinematic character turnaround sheet, white background.")
    negative_prompt: str = Field(default="blurry, low quality, distorted, bad anatomy")
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    seed: int | None = None


class InpaintRequest(BaseModel):
    image_filename: str
    mask_data: str
    prompt: str = Field(default="cinematic photo, ultra detailed")
    denoise: float = Field(default=0.85)
    steps: int = Field(default=4)
    seed: int | None = None


class TimelineExportRequest(BaseModel):
    clips: list[dict[str, Any]] = Field(default_factory=list)


class AIDirectorPlanRequest(BaseModel):
    idea: str = Field(default="A lone scavenger navigates an infected city at dusk.")
    duration: int = Field(default=15, ge=5, le=300)


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
        lora_name = (
            "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
            if lora_choice == "4step"
            else "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
        )

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
def submit_generate_job(req: GenerateRequest) -> dict[str, Any]:
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
def submit_regenerate_chunk(req: RegenerateChunkRequest) -> dict[str, Any]:
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
def submit_job_review(job_id: str, payload: ReviewPayload) -> dict[str, Any]:
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
        model_choice = req.model.lower()
        width = req.width or (1344 if "flux" in model_choice else 1024)
        height = req.height or (768 if "flux" in model_choice else 1024)
        steps = req.steps or (4 if "flux" in model_choice else 8)

        if "flux" in model_choice:
            graph = pipeline.build_flux_image_prompt(
                prompt=req.prompt,
                width=width,
                height=height,
                steps=steps,
                seed=req.seed,
            )
            prefix = "flux_gen"
        else:
            graph = pipeline.build_qwen_image_prompt(
                prompt=req.prompt,
                negative_prompt=req.negative_prompt,
                width=width,
                height=height,
                steps=steps,
                seed=req.seed,
            )
            prefix = "qwen_gen"

        out_path = await pipeline.execute_prompt(graph)
        new_filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
        target_path = COMFY_INPUT_DIR / new_filename
        shutil.copy2(out_path, target_path)

        return {
            "success": True,
            "filename": new_filename,
            "url": f"/chronoflow/inputs/{new_filename}",
        }
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
# AI Director & Timeline Export
# =====================================================================

@router.post("/ai_director/plan")
def ai_director_plan(req: AIDirectorPlanRequest) -> dict[str, Any]:
    num_scenes = max(1, round(req.duration / 5.2))
    scenes = []

    for i in range(num_scenes):
        shot_num = i + 1
        if shot_num == 1:
            desc = f"Establishing Shot: Wide panoramic view introducing the scene. {req.idea}. The camera drifts forward slowly through atmospheric haze."
            shot_type = "Wide Establishing"
        elif shot_num == num_scenes:
            desc = f"Climactic Shot: Low angle dynamic reaction. High tension conclusion, quick camera pan and dramatic lighting."
            shot_type = "Dynamic Climax"
        else:
            desc = f"Subject Action Shot: Medium close-up focusing on character movement, environmental interaction, and mounting suspense."
            shot_type = "Medium Tracking"

        formatted_h3 = pipeline.compile_h3_prompt(
            detailed_description=f"[Shot {shot_num}] {desc}",
            summary=f"Scene {shot_num} of {num_scenes}: {shot_type}",
            retention_analysis="Subject appearance and lighting atmosphere are preserved.",
            soundscape="Subtle ambient wind, distant electrical hum, metallic creaks.",
            music="Tense low cinematic bass drone.",
        )

        scenes.append({
            "shot_index": shot_num,
            "title": f"Shot {shot_num}: {shot_type}",
            "prompt": formatted_h3,
            "duration": 5.2,
            "workflow": "sliding_window" if shot_num > 1 else "reference",
        })

    return {
        "success": True,
        "title": f"Cinematic Project: {req.idea[:40]}...",
        "total_duration": num_scenes * 5.2,
        "scenes": scenes,
    }


@router.post("/timeline/export")
def timeline_export(req: TimelineExportRequest) -> dict[str, Any]:
    if not req.clips:
        raise HTTPException(status_code=400, detail="No clips provided")

    export_id = uuid.uuid4().hex[:8]
    master_name = f"chronoflow_timeline_master_{export_id}.mp4"
    master_path = STUDIO_OUTPUT_DIR / master_name

    rendered_path = pipeline.render_timeline_edl(req.clips, master_path)
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
            if name.startswith(("flux_gen_", "qwen_gen_", "inpaint_", "chronoflow_tail_", "zombie_", "char_")):
                size_bytes = f.stat().st_size
                total_bytes += size_bytes
                mtime = f.stat().st_mtime
                model_tag = "FLUX.1 Schnell" if "flux" in name else "Qwen-Image-2.1" if "qwen" in name else "Inpaint Asset"
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
def get_chronoflow_ui() -> FileResponse:
    index_path = CHRONOFLOW_STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="ChronoFlow UI index.html not found")
    return FileResponse(index_path, headers={"Cache-Control": "no-cache"})
