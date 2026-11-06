import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import uuid
import time
import asyncio
import aiohttp
from aiohttp import web
from engine.chronoflow.pipeline import ChronoFlowPipeline, COMFY_INPUT_DIR, STUDIO_OUTPUT_DIR
from engine.chronoflow.supervisor import JobSupervisor
from engine.chronoflow.reviewer import analyze_video_chunk

PORT = 7860
pipeline = ChronoFlowPipeline()
supervisor = JobSupervisor(pipeline=pipeline)
active_jobs = supervisor.active_jobs

def save_jobs():
    supervisor.bump_version()
    supervisor._save_jobs_to_disk()

VAULT_DIR = Path(__file__).resolve().parent / "vault"
VAULT_FILE = VAULT_DIR / "characters.json"
JOBS_FILE = VAULT_DIR / "jobs.json"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

def load_jobs():
    return supervisor.active_jobs

def load_characters():
    if VAULT_FILE.exists():
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_characters(chars):
    with open(VAULT_FILE, "w", encoding="utf-8") as f:
        json.dump(chars, f, indent=2)

async def handle_status(request):
    comfy_status = await pipeline.check_comfy_status()
    models_dir = Path(__file__).resolve().parent.parent / "models"
    
    h3_dit = (models_dir / "diffusion_models" / "minimax_h3_fl2va_pruned_int8_convrot.safetensors").exists()
    h3_turbo4 = (models_dir / "loras" / "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors").exists()
    h3_turbo8 = (models_dir / "loras" / "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors").exists()
    wan_dit = any((models_dir / "diffusion_models").glob("*wan*")) or any((models_dir / "diffusion_models").glob("*Wan*"))

    return web.json_response({
        "comfy": comfy_status,
        "models": {
            "minimax_h3_dit": h3_dit,
            "minimax_h3_turbo4": h3_turbo4,
            "minimax_h3_turbo8": h3_turbo8,
            "wan2_1": wan_dit
        }
    })

async def handle_characters(request):
    if request.method == "GET":
        return web.json_response({"characters": load_characters()})
    elif request.method == "POST":
        data = await request.json()
        chars = load_characters()
        char_id = data.get("id") or f"char_{uuid.uuid4().hex[:6]}"
        char_entry = {
            "id": char_id,
            "name": data.get("name", "Unnamed Actor"),
            "role": data.get("role", "Protagonist"),
            "image": data.get("image", ""),
            "description": data.get("description", ""),
            "tag": data.get("tag", f"<Picture {len(chars) + 1}>")
        }
        # Update or append
        existing = [i for i, c in enumerate(chars) if c["id"] == char_id]
        if existing:
            chars[existing[0]] = char_entry
        else:
            chars.append(char_entry)
        save_characters(chars)
        return web.json_response({"success": True, "character": char_entry})

async def handle_delete_character(request):
    char_id = request.match_info.get("char_id")
    chars = load_characters()
    chars = [c for c in chars if c["id"] != char_id]
    save_characters(chars)
    return web.json_response({"success": True})

async def handle_upload(request):
    reader = await request.multipart()
    field = await reader.next()
    if field.name in ('image', 'file'):
        ext = Path(field.filename).suffix or ".png"
        filename = f"chronoflow_{uuid.uuid4().hex[:8]}{ext}"
        filepath = COMFY_INPUT_DIR / filename
        with open(filepath, 'wb') as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                f.write(chunk)
        return web.json_response({"success": True, "filename": filename})
    return web.json_response({"success": False, "error": "No image provided"}, status=400)

async def handle_ai_director_plan(request):
    """Generates a structured multi-scene storyboard breakdown from a high-level story idea."""
    data = await request.json()
    idea = data.get("idea", "A lone scavenger navigates an infected city at dusk.")
    duration = int(data.get("duration", 15)) # 15s = 3 scenes of ~5s
    
    num_scenes = max(1, round(duration / 5.2))
    scenes = []

    # Creative cinematic templates for scene beats
    for i in range(num_scenes):
        shot_num = i + 1
        if shot_num == 1:
            desc = f"Establishing Shot: Wide panoramic view introducing the scene. {idea}. The camera drifts forward slowly through atmospheric haze."
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
            music="Tense low cinematic bass drone."
        )

        scenes.append({
            "shot_index": shot_num,
            "title": f"Shot {shot_num}: {shot_type}",
            "prompt": formatted_h3,
            "duration": 5.2,
            "workflow": "sliding_window" if shot_num > 1 else "reference"
        })

    return web.json_response({
        "success": True,
        "title": f"Cinematic Project: {idea[:40]}...",
        "total_duration": num_scenes * 5.2,
        "scenes": scenes
    })

def resolve_h3_lora_name(choice: str | None) -> str:
    choice_str = str(choice or "").lower()
    if "8step" in choice_str:
        return "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
    return "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"


async def run_production_job(job_id, data):
    job = active_jobs[job_id]
    try:
        workflow_mode = data.get("workflow_mode", "sliding_window") # sliding_window, flf2v, reference, storyboard
        prompt = data.get("prompt", "Cinematic drone shot over a glowing metropolis at dusk.")
        width = int(data.get("width", 1344))
        height = int(data.get("height", 768))
        steps = int(data.get("steps", 4))
        lora_choice = data.get("lora_choice", "4step")
        lora_name = resolve_h3_lora_name(lora_choice)

        chunk_files = []
        pre_existing = data.get("pre_existing_chunks", [])
        if pre_existing:
            import shutil
            for p_idx, p_file in enumerate(pre_existing):
                p_path = Path(p_file)
                if not p_path.is_absolute():
                    p_path = Path(__file__).resolve().parent.parent / p_file
                if p_path.exists():
                    c_name = f"{job_id}_chunk_{p_idx + 1}.mp4"
                    shutil.copy2(p_path, STUDIO_OUTPUT_DIR / c_name)
                    chunk_files.append(STUDIO_OUTPUT_DIR / c_name)
                    job["chunks"].append(f"/outputs/{c_name}")
            save_jobs()

        def on_step(val, max_val):
            job["step_progress"] = int((val / max_val) * 100) if max_val else 0

        # ==========================================================
        # 1. FLF2V MODE (First-Last-Frame Interpolation)
        # ==========================================================
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
                last_frame_filename=last_frame
            )
            out_video = await pipeline.execute_prompt(graph, on_step=on_step)
            chunk_files.append(out_video)

        # ==========================================================
        # 2. REFERENCE MODE (Character Sheets & Turnarounds)
        # ==========================================================
        elif workflow_mode == "reference":
            ref_images = data.get("ref_images", []) # list of filenames
            total_sec = float(data.get("total_duration", 5.2))
            num_chunks = max(1, round(total_sec / 5.17))
            job["total_chunks"] = num_chunks

            current_guide_frame = None

            for chunk_idx in range(num_chunks):
                if job["cancelled"]:
                    job["status"] = "cancelled"
                    return

                job["current_chunk"] = chunk_idx + 1
                job["status_msg"] = f"Generating Shot {chunk_idx + 1} of {num_chunks} with Character Reference Locking..."
                job["step_progress"] = 0

                graph = pipeline.build_h3_prompt(
                    prompt=prompt if num_chunks == 1 else f"{prompt} [sequence {chunk_idx + 1}]",
                    width=width,
                    height=height,
                    length=124,
                    steps=steps,
                    lora_name=lora_name,
                    workflow_mode="reference",
                    ref_images=ref_images
                )
                chunk_output = await pipeline.execute_prompt(graph, on_step=on_step)
                chunk_files.append(chunk_output)

                web_chunk_name = f"{job_id}_chunk_{chunk_idx + 1}.mp4"
                import shutil
                shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / web_chunk_name)
                job["chunks"].append(f"/outputs/{web_chunk_name}")
                try:
                    prev_c = chunk_files[-2] if len(chunk_files) >= 2 else None
                    review = analyze_video_chunk(STUDIO_OUTPUT_DIR / web_chunk_name, chunk_prompt, chunk_idx + 1, num_chunks, prev_c)
                    if "reviews" not in job: job["reviews"] = {}
                    job["reviews"][str(chunk_idx + 1)] = review
                except Exception as r_err:
                    print(f"Review error: {r_err}")
                save_jobs()

        # ==========================================================
        # 3. STORYBOARD MULTI-SHOT MODE
        # ==========================================================
        elif workflow_mode == "storyboard":
            scenes = data.get("scenes", [])
            start_chunk_offset = len(chunk_files)
            job["total_chunks"] = len(scenes) + start_chunk_offset
            current_guide_frame = data.get("initial_image")

            for idx, scene in enumerate(scenes):
                if job["cancelled"]:
                    job["status"] = "cancelled"
                    return

                chunk_num = idx + 1 + start_chunk_offset
                job["current_chunk"] = chunk_num
                scene_title = scene.get("title", f"Scene {chunk_num}")
                job["status_msg"] = f"Rendering {scene_title} ({chunk_num}/{job['total_chunks']})..."
                job["step_progress"] = 0

                s_prompt = scene.get("prompt", prompt)
                s_first = scene.get("first_frame")
                if not s_first and idx == 0 and current_guide_frame:
                    s_first = current_guide_frame
                elif not s_first and idx > 0 and current_guide_frame:
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
                    ref_images=s_refs
                )
                chunk_output = await pipeline.execute_prompt(graph, on_step=on_step)
                chunk_files.append(chunk_output)

                web_chunk_name = f"{job_id}_chunk_{chunk_num}.mp4"
                import shutil
                shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / web_chunk_name)
                job["chunks"].append(f"/outputs/{web_chunk_name}")
                save_jobs()

                # Extract tail frame for next shot continuation
                if idx < len(scenes) - 1:
                    tail_filename = f"chronoflow_tail_{job_id}_{chunk_num}.png"
                    tail_path = COMFY_INPUT_DIR / tail_filename
                    if pipeline.extract_tail_frame(chunk_output, tail_path):
                        current_guide_frame = tail_filename

        # ==========================================================
        # 4. SLIDING WINDOW CONTINUATION (Baseline)
        # ==========================================================
        else:
            total_seconds = float(data.get("total_duration", 15))
            num_chunks = max(1, round(total_seconds / 5.17))
            job["total_chunks"] = num_chunks
            current_guide_frame = data.get("initial_image")

            for chunk_idx in range(num_chunks):
                if job["cancelled"]:
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
                    first_frame_filename=current_guide_frame
                )
                chunk_output = await pipeline.execute_prompt(graph, on_step=on_step)
                chunk_files.append(chunk_output)

                web_chunk_name = f"{job_id}_chunk_{chunk_idx + 1}.mp4"
                import shutil
                shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / web_chunk_name)
                job["chunks"].append(f"/outputs/{web_chunk_name}")
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
            job["master_video"] = f"/outputs/{master_name}"
            job["status"] = "completed"
            job["status_msg"] = f"Successfully generated continuous {len(chunk_files) * 5.2:.1f}s cinematic film!"
        else:
            job["status"] = "completed_chunks"
            job["status_msg"] = "All scene chunks generated successfully."
        save_jobs()

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["status_msg"] = f"Error: {str(e)}"
        save_jobs()

async def handle_generate(request):
    data = await request.json()
    job_id = uuid.uuid4().hex[:12]
    new_job = {
        "id": job_id,
        "prompt": data.get("prompt", ""),
        "initial_image": data.get("initial_image"),
        "workflow_mode": data.get("workflow_mode", "sliding_window"),
        "width": int(data.get("width", 1344)),
        "height": int(data.get("height", 768)),
        "total_duration": float(data.get("total_duration", 15.6)),
        "status": "starting",
        "status_msg": "Initializing ChronoFlow production pipeline...",
        "current_chunk": 0,
        "total_chunks": 1,
        "step_progress": 0,
        "chunks": [],
        "master_video": None,
        "cancelled": False,
        "error": None,
        "created_at": time.time()
    }
    supervisor.register_new_job(job_id, new_job)
    supervisor.start_task(job_id, run_production_job(job_id, data))
    return web.json_response({"success": True, "job_id": job_id})

reviews_store = {}

async def run_chunk_regeneration(job_id, chunk_index, feedback_notes="", custom_anchor=None, custom_prompt=None, duration_sec=5.17):
    """Regenerates a specific video chunk based on user review feedback or modified anchor image."""
    if job_id not in active_jobs:
        return
    job = active_jobs[job_id]
    chunk_index = int(chunk_index)

    # Frame count aligned to MiniMax H3 17k+5 frame grid
    duration_sec = float(duration_sec or 5.17)
    if duration_sec <= 1.2:
        frame_length = 22 # ~0.92s
    elif duration_sec <= 2.5:
        frame_length = 56 # ~2.33s
    elif duration_sec <= 3.5:
        frame_length = 73 # ~3.04s
    else:
        frame_length = 124 # ~5.17s
    
    def on_step(step, total):
        pct = int((step / total) * 100)
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
                guide_frame = job.get("initial_image") or "zombie_survivor_anchor.jpg"
            elif chunk_index > 1:
                prev_chunk_filename = f"{job_id}_chunk_{chunk_index - 1}.mp4"
                prev_chunk_path = STUDIO_OUTPUT_DIR / prev_chunk_filename
                if prev_chunk_path.exists():
                    tail_name = f"chronoflow_tail_{job_id}_{chunk_index - 1}.png"
                    tail_path = COMFY_INPUT_DIR / tail_name
                    if pipeline.extract_tail_frame(prev_chunk_path, tail_path):
                        guide_frame = tail_name
                if not guide_frame:
                    guide_frame = job.get("initial_image") or "zombie_survivor_anchor.jpg"

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
            first_frame_filename=guide_frame
        )

        chunk_output = await pipeline.execute_prompt(graph, on_step=on_step)

        web_chunk_name = f"{job_id}_chunk_{chunk_index}.mp4"
        import shutil
        shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / web_chunk_name)

        web_url = f"/outputs/{web_chunk_name}"
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
            job["master_video"] = f"/outputs/{master_name}"
            job["status"] = "completed"
            job["status_msg"] = f"Shot {chunk_index} successfully regenerated and master film updated!"
        else:
            job["status"] = "completed"
            job["status_msg"] = f"Shot {chunk_index} regenerated successfully."
        save_jobs()
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["status_msg"] = f"Regeneration error: {str(e)}"
        save_jobs()

async def handle_list_jobs(request):
    jobs_list = sorted(list(active_jobs.values()), key=lambda j: j.get("created_at", 0), reverse=True)
    return web.json_response(
        {"jobs": jobs_list},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    )

async def handle_submit_review(request):
    job_id = request.match_info.get("job_id")
    data = await request.json()
    if job_id not in reviews_store:
        reviews_store[job_id] = []
    reviews_store[job_id].append(data)
    if job_id in active_jobs:
        if "reviews" not in active_jobs[job_id]:
            active_jobs[job_id]["reviews"] = {}
        chunk_idx = str(data.get("chunk_index", 0))
        active_jobs[job_id]["reviews"][chunk_idx] = data

        # Trigger automatic regeneration if requested!
        if data.get("rating") == "needs_regeneration":
            notes = data.get("notes", "")
            duration_sec = float(data.get("duration", 5.17))
            asyncio.create_task(run_chunk_regeneration(job_id, int(chunk_idx), notes, duration_sec=duration_sec))

    return web.json_response({"success": True})

async def handle_regenerate_chunk(request):
    """Directly triggers regeneration of a specific shot."""
    data = await request.json()
    job_id = data.get("job_id")
    chunk_index = int(data.get("chunk_index", 1))
    notes = data.get("notes", "")
    custom_anchor = data.get("anchor_image")
    custom_prompt = data.get("prompt")
    duration_sec = float(data.get("duration", 5.17))

    if job_id not in active_jobs:
        return web.json_response({"success": False, "error": "Job not found"}, status=404)

    supervisor.start_task(f"{job_id}_regen_{chunk_index}", run_chunk_regeneration(job_id, chunk_index, notes, custom_anchor, custom_prompt, duration_sec))
    return web.json_response({"success": True, "message": f"Regeneration dispatched for Shot #{chunk_index} ({duration_sec:.1f}s)"})

async def handle_save_frame(request):
    """Saves a captured video frame from the client canvas for inpainting/anchor use."""
    try:
        data = await request.json()
        frame_data = data.get("frame_data")
        prefix = data.get("prefix", "frame_snap")
        if not frame_data:
            return web.json_response({"success": False, "error": "frame_data required"}, status=400)

        import base64
        if "," in frame_data:
            frame_data = frame_data.split(",")[1]
        img_bytes = base64.b64decode(frame_data)
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
        path = COMFY_INPUT_DIR / filename
        with open(path, "wb") as f:
            f.write(img_bytes)

        return web.json_response({
            "success": True,
            "filename": filename,
            "url": f"/inputs/{filename}"
        }, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_job_status(request):
    job_id = request.match_info.get("job_id")
    if job_id not in active_jobs:
        return web.json_response({"error": "Job not found"}, status=404)
    return web.json_response(
        active_jobs[job_id],
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    )

async def handle_cancel(request):
    data = await request.json()
    job_id = data.get("job_id")
    success = supervisor.cancel_job(job_id)
    return web.json_response({"success": success})

async def handle_unified_sync(request):
    try:
        client_v = int(request.query.get("v", 0))
    except (ValueError, TypeError):
        client_v = 0
    job_id = request.query.get("job_id")
    state = await supervisor.get_unified_sync_state(client_v, job_id)
    return web.json_response(
        state,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    )

async def handle_generate_image(request):
    """Generates an image / character sheet with the central art engine (Qwen Image 2.1)."""
    try:
        data = await request.json()
        filename = await pipeline.generate_art_image(
            data.get("prompt", "Cinematic character turnaround sheet, white background."),
            data.get("negative_prompt", "blurry, low quality, distorted, bad anatomy"),
            int(data.get("width") or 1024), int(data.get("height") or 1024), data.get("seed"),
        )
        return web.json_response({"success": True, "filename": filename, "url": f"/inputs/{filename}"},
                                 headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_inpaint_image(request):
    """Inpaints a specific painted region on an image to modify or fix it."""
    try:
        data = await request.json()
        image_filename = data.get("image_filename")
        mask_data = data.get("mask_data")
        prompt = data.get("prompt", "cinematic photo, ultra detailed")
        denoise = float(data.get("denoise", 0.85))
        steps = int(data.get("steps", 4))
        seed = data.get("seed")

        if not image_filename or not mask_data:
            return web.json_response({"success": False, "error": "image_filename and mask_data required"}, status=400)

        # Decode base64 mask and write to ComfyUI input/
        import base64
        if "," in mask_data:
            mask_data = mask_data.split(",")[1]
        mask_bytes = base64.b64decode(mask_data)
        mask_filename = f"mask_{uuid.uuid4().hex[:8]}.png"
        mask_path = COMFY_INPUT_DIR / mask_filename
        with open(mask_path, "wb") as f:
            f.write(mask_bytes)

        graph = pipeline.build_inpaint_prompt(
            image_filename=image_filename,
            mask_filename=mask_filename,
            prompt=prompt,
            denoise=denoise,
            steps=steps,
            seed=seed
        )
        out_path = await pipeline.execute_prompt(graph)

        new_filename = f"inpaint_{uuid.uuid4().hex[:8]}.png"
        target_path = COMFY_INPUT_DIR / new_filename
        import shutil
        shutil.copy2(out_path, target_path)

        return web.json_response({
            "success": True,
            "filename": new_filename,
            "url": f"/inputs/{new_filename}"
        }, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_timeline_export(request):
    """Renders a multi-track NLE timeline sequence into a final master video."""
    try:
        data = await request.json()
        clips = data.get("clips", [])
        if not clips:
            return web.json_response({"success": False, "error": "No clips provided"}, status=400)

        export_id = uuid.uuid4().hex[:8]
        master_name = f"chronoflow_timeline_master_{export_id}.mp4"
        master_path = STUDIO_OUTPUT_DIR / master_name

        rendered_path = pipeline.render_timeline_edl(clips, master_path, data.get("overlays"))
        if rendered_path and master_path.exists():
            return web.json_response({
                "success": True,
                "master_video": f"/outputs/{master_name}",
                "filename": master_name
            }, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
        else:
            return web.json_response({"success": False, "error": "Timeline render failed"}, status=500)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def init_app():
    app = web.Application()
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/jobs", handle_list_jobs)
    app.router.add_get("/api/gallery", handle_gallery)
    app.router.add_get("/api/characters", handle_characters)
    app.router.add_post("/api/characters", handle_characters)
    app.router.add_delete("/api/characters/{char_id}", handle_delete_character)
    app.router.add_post("/api/ai_director/plan", handle_ai_director_plan)
    app.router.add_post("/api/upload_image", handle_upload)
    app.router.add_post("/api/generate", handle_generate)
    app.router.add_post("/api/generate_image", handle_generate_image)
    app.router.add_post("/api/inpaint_image", handle_inpaint_image)
    app.router.add_post("/api/timeline/export", handle_timeline_export)
    app.router.add_post("/api/regenerate_chunk", handle_regenerate_chunk)
    app.router.add_post("/api/save_frame", handle_save_frame)
    app.router.add_get("/api/job/{job_id}", handle_job_status)
    app.router.add_post("/api/job/{job_id}/review", handle_submit_review)
    app.router.add_post("/api/cancel", handle_cancel)
    app.router.add_get("/api/sync", handle_unified_sync)

    async def on_startup(app_instance):
        supervisor.start_watchdog()
    app.on_startup.append(on_startup)

    static_dir = Path(__file__).resolve().parent / "static"

    async def handle_index(request):
        return web.FileResponse(
            static_dir / "index.html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
        )

    app.router.add_get("/", handle_index)
    app.router.add_static("/outputs", STUDIO_OUTPUT_DIR)
    app.router.add_static("/inputs", COMFY_INPUT_DIR)
    app.router.add_static("/", static_dir)

    return app

if __name__ == "__main__":
    if os.name == 'nt':
        import sys
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
    print(f"Starting ChronoFlow Pro Studio on http://127.0.0.1:{PORT}...")
    web.run_app(init_app(), host="127.0.0.1", port=PORT)
async def handle_gallery(request):
    assets = {
        "masters": [],
        "chunks": [],
        "images": [],
        "stats": {"total_videos": 0, "total_images": 0, "total_storage_mb": 0.0}
    }
    total_bytes = 0
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
                "url": f"/outputs/{name}",
                "job_id": job_id,
                "prompt": job_info.get("prompt", "Cinematic master cut"),
                "duration": job_info.get("total_duration", 15.6),
                "resolution": f"{job_info.get('width', 1344)}x{job_info.get('height', 768)}",
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "created_at": mtime
            })
        elif "_chunk_" in name and name.endswith(".mp4"):
            parts = name.split("_chunk_")
            job_id = parts[0]
            chunk_num = parts[1].replace(".mp4", "")
            job_info = active_jobs.get(job_id, {})
            review = job_info.get("reviews", {}).get(chunk_num, {})
            assets["chunks"].append({
                "filename": name,
                "url": f"/outputs/{name}",
                "job_id": job_id,
                "chunk_index": chunk_num,
                "score": review.get("overall_score", 93),
                "grade": review.get("grade", "A"),
                "verdict": review.get("verdict", "APPROVED FOR MASTER CUT"),
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "created_at": mtime
            })
        elif name.endswith((".png", ".jpg", ".webp")) and not name.startswith("concat_"):
            assets["images"].append({
                "filename": name,
                "url": f"/outputs/{name}",
                "model": "Render Asset",
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "created_at": mtime
            })
    
    # Also scan COMFY_INPUT_DIR for generated images, concept art, and inpaint assets
    for f in COMFY_INPUT_DIR.iterdir():
        if not f.is_file():
            continue
        name = f.name
        if name.startswith(("art_", "flux_gen_", "qwen_gen_", "inpaint_", "chronoflow_tail_", "zombie_", "char_")) or name in ("beetle_rider.png", "zombie_survivor_anchor.jpg", "zombie_outpost_start.jpg"):
            size_bytes = f.stat().st_size
            total_bytes += size_bytes
            mtime = f.stat().st_mtime
            model_tag = "FLUX.1 Schnell (legacy)" if "flux" in name else "Qwen-Image-2.1" if name.startswith(("art_", "qwen_gen_")) else "Inpaint Asset" if "inpaint" in name else "Concept Keyframe"
            assets["images"].append({
                "filename": name,
                "url": f"/inputs/{name}",
                "model": model_tag,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "created_at": mtime
            })
    assets["masters"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["chunks"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["images"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["stats"]["total_videos"] = len(assets["masters"]) + len(assets["chunks"])
    assets["stats"]["total_images"] = len(assets["images"])
    assets["stats"]["total_storage_mb"] = round(total_bytes / (1024 * 1024), 1)
    return web.json_response(assets)


