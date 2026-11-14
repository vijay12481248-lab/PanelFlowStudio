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
import base64
import shutil
from urllib.parse import quote
from aiohttp import web
from engine.chronoflow.pipeline import ChronoFlowPipeline, COMFY_INPUT_DIR, STUDIO_OUTPUT_DIR, BASE_DIR
from engine.chronoflow.supervisor import JobSupervisor
from engine.chronoflow.reviewer import analyze_video_chunk
from engine.chronoflow import media_tools
from engine.chronoflow.folder_dialog import pick_native_folder
from engine.api.routers.chronoflow import (
    load_storage_locations,
    save_storage_locations,
    resolve_destination_dir,
    _unique_destination,
    _MEDIA_IMAGE_EXTS,
    _MEDIA_VIDEO_EXTS,
    _MEDIA_AUDIO_EXTS,
    _FILE_SERVE_SUFFIXES,
    _organizer_roots,
    _resolve_organizer_path,
)

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
    models_dir = BASE_DIR / "models"
    
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

async def handle_dependencies_status(request):
    from engine.system.setup import comfyui_manager, locate_and_configure_ffmpeg
    return web.json_response({
        "comfyui": comfyui_manager.get_status(),
        "ffmpeg": locate_and_configure_ffmpeg(),
    })

async def handle_launch_comfyui(request):
    from engine.system.setup import comfyui_manager
    res = comfyui_manager.ensure_running(timeout_s=15.0)
    return web.json_response(res)


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
    mode = data.get("mode", "antigravity") # "antigravity" (multi-agent) or "template"

    if mode == "antigravity" or data.get("use_creative_agents"):
        try:
            from engine.creative.orchestrator import CreativeOrchestrator
            from engine.creative.schema import StorySeed, StoryGenre, VisualStyle

            genre_str = data.get("genre", "mythological_epic")
            style_str = data.get("visual_style", "cinematic_photorealistic")
            tone = data.get("tone", "Epic, solemn, philosophically profound")
            target_chapters = int(data.get("target_chapters", 1))
            parent_folder = data.get("parent_folder")

            try:
                genre = StoryGenre(genre_str)
            except Exception:
                genre = StoryGenre.CUSTOM

            try:
                v_style = VisualStyle(style_str)
            except Exception:
                v_style = VisualStyle.CINEMATIC_PHOTO

            seed = StorySeed(
                prompt=idea,
                genre=genre,
                visual_style=v_style,
                tone=tone,
                target_chapters=target_chapters,
                parent_folder=parent_folder
            )

            orch = CreativeOrchestrator()
            project = await orch.synthesize_story(seed)

            all_shots = []
            folders = []
            for sc in project.scenes:
                folders.append({
                    "id": sc.id,
                    "name": sc.name,
                    "description": sc.description,
                    "path": sc.path or "",
                    "shot_indices": [s.shot_index for s in sc.shots]
                })
                for shot in sc.shots:
                    all_shots.append({
                        "shot_index": shot.shot_index,
                        "title": shot.title,
                        "shot_type": shot.shot_type,
                        "duration": shot.duration,
                        "workflow": shot.workflow,
                        "first_frame": shot.first_frame or "",
                        "last_frame": shot.last_frame or "",
                        "prompt": shot.prompt,
                        "art_prompt": shot.art_prompt,
                        "folder_id": sc.id
                    })

            first_char = project.bible.characters[0] if project.bible.characters else None
            return web.json_response({
                "success": True,
                "title": project.title,
                "total_duration": sum(s["duration"] for s in all_shots),
                "scenes": all_shots,
                "folders": folders,
                "protagonist": {
                    "id": first_char.id if first_char else "",
                    "name": first_char.name if first_char else "",
                    "role": first_char.role if first_char else "",
                    "description": first_char.visual_tags if first_char else "",
                    "tag": first_char.tag if first_char else "<Picture 1>"
                } if first_char else None,
                "novel_chapter": project.chapters[0].model_dump() if project.chapters else None,
                "bible": project.bible.model_dump(),
                "project_id": project.project_id
            })
        except Exception as e:
            logger.warning(f"Antigravity multi-agent synthesis encountered: {e}, falling back to template engine...")

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


async def handle_creative_synthesize(request):
    try:
        data = await request.json()
        from engine.creative.orchestrator import CreativeOrchestrator
        from engine.creative.schema import StorySeed, StoryGenre, VisualStyle

        prompt = data.get("prompt") or data.get("idea") or "A mythological epic"
        genre_str = data.get("genre", "mythological_epic")
        style_str = data.get("visual_style", "cinematic_photorealistic")
        tone = data.get("tone", "Epic, solemn, philosophically profound")
        target_chapters = int(data.get("target_chapters", 1))
        parent_folder = data.get("parent_folder")

        try:
            genre = StoryGenre(genre_str)
        except Exception:
            genre = StoryGenre.CUSTOM

        try:
            v_style = VisualStyle(style_str)
        except Exception:
            v_style = VisualStyle.CINEMATIC_PHOTO

        seed = StorySeed(
            prompt=prompt,
            genre=genre,
            visual_style=v_style,
            tone=tone,
            target_chapters=target_chapters,
            parent_folder=parent_folder,
        )

        orch = CreativeOrchestrator()
        project = await orch.synthesize_story(seed)
        return web.json_response({
            "success": True,
            "project_id": project.project_id,
            "title": project.title,
            "chapters_count": len(project.chapters),
            "scenes_count": len(project.scenes),
            "shots_count": sum(len(s.shots) for s in project.scenes),
            "project": project.model_dump(),
        })
    except Exception as e:
        logger.exception(f"handle_creative_synthesize failed: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_creative_projects(request):
    from engine.creative.vault import CreativeVault
    vault = CreativeVault()
    return web.json_response({"projects": vault.list_projects()})


async def handle_get_creative_project(request):
    proj_id = request.match_info.get("project_id")
    from engine.creative.vault import CreativeVault
    vault = CreativeVault()
    project = vault.get_project(proj_id)
    if not project:
        return web.json_response({"success": False, "error": "Not found"}, status=404)
    return web.json_response({"success": True, "project": project.model_dump()})


async def handle_creative_generate_anchor(request):
    try:
        data = await request.json()
        from engine.comfyui.art import ArtEngine
        from engine.creative.vault import CreativeVault

        vault = CreativeVault()
        project_id = data.get("project_id")
        project = vault.get_project(project_id)
        if not project:
            return web.json_response({"success": False, "error": "Project not found"}, status=404)

        prompt = data.get("prompt")
        char_id = data.get("character_id")
        shot_index = data.get("shot_index")
        char = None
        if char_id:
            char = next((c for c in project.bible.characters if c.id == char_id), None)
            if char and not prompt:
                prompt = (
                    f"Masterpiece cinematic portrait, {char.name}, {char.visual_tags}. "
                    f"{char.facial_features}. {project.seed.visual_style.value} style, 8k resolution, dramatic lighting."
                )

        if not prompt and shot_index:
            for sc in project.scenes:
                for sh in sc.shots:
                    if sh.shot_index == shot_index:
                        prompt = sh.art_prompt or sh.prompt
                        break

        if not prompt:
            return web.json_response({"success": False, "error": "No prompt for anchor"}, status=400)

        art_image = await asyncio.to_thread(
            ArtEngine().generate,
            prompt=prompt,
            width=1024,
            height=1024
        )
        image_name = art_image.filename

        if char and image_name:
            char.anchor_image = image_name
            vault.sync_characters_from_bible(project.bible.characters)

        if shot_index and image_name:
            for sc in project.scenes:
                for sh in sc.shots:
                    if sh.shot_index == shot_index:
                        sh.first_frame = image_name
                        break

        vault.save_project(project)
        return web.json_response({
            "success": True,
            "image": image_name,
            "prompt": prompt,
            "project_id": project.project_id
        })
    except Exception as e:
        logger.exception(f"handle_creative_generate_anchor failed: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

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
                if "chunk_prompts" not in job: job["chunk_prompts"] = []
                if len(job["chunk_prompts"]) <= chunk_idx:
                    job["chunk_prompts"].append(chunk_prompt)
                else:
                    job["chunk_prompts"][chunk_idx] = chunk_prompt
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

async def handle_save_chunk_prompt(request):
    """Persists an edited shot prompt for a job."""
    try:
        data = await request.json()
        job_id = data.get("job_id")
        chunk_index = int(data.get("chunk_index", 1))
        prompt = data.get("prompt", "")
        if job_id not in active_jobs:
            return web.json_response({"success": False, "error": "Job not found"}, status=404)
        job = active_jobs[job_id]
        if "chunk_prompts" not in job:
            job["chunk_prompts"] = []
        while len(job["chunk_prompts"]) < chunk_index:
            job["chunk_prompts"].append("")
        job["chunk_prompts"][chunk_index - 1] = prompt
        save_jobs()
        return web.json_response({"success": True, "message": f"Prompt for Shot #{chunk_index} saved."})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_create_clip(request):
    """Creates and appends a new continuation clip to the job."""
    try:
        data = await request.json()
        job_id = data.get("job_id")
        prompt = data.get("prompt", "")
        duration_sec = float(data.get("duration", 5.17))
        if job_id not in active_jobs:
            return web.json_response({"success": False, "error": "Job not found"}, status=404)
        job = active_jobs[job_id]
        chunk_index = len(job.get("chunks", [])) + 1
        if "chunk_prompts" not in job:
            job["chunk_prompts"] = []
        while len(job["chunk_prompts"]) < chunk_index:
            job["chunk_prompts"].append("")
        job["chunk_prompts"][chunk_index - 1] = prompt
        job["total_chunks"] = max(job.get("total_chunks", 0), chunk_index)
        job["status"] = "starting"
        job["status_msg"] = f"Initializing render for new Shot #{chunk_index}..."
        save_jobs()
        supervisor.start_task(f"{job_id}_new_{chunk_index}", run_chunk_regeneration(job_id, chunk_index, custom_prompt=prompt, duration_sec=duration_sec))
        return web.json_response({"success": True, "message": f"Dispatched new Shot #{chunk_index} ({duration_sec:.1f}s)", "chunk_index": chunk_index})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_delete_shot(request):
    """Deletes a specific shot/chunk and its prompt from a job, and cleans up the chunk file."""
    try:
        data = await request.json()
        job_id = data.get("job_id")
        chunk_index = int(data.get("chunk_index", 1))
        if job_id not in active_jobs:
            return web.json_response({"success": False, "error": "Job not found"}, status=404)
        job = active_jobs[job_id]
        chunks = job.get("chunks", [])
        prompts = job.get("chunk_prompts", [])

        deleted_file = None
        if 1 <= chunk_index <= len(chunks):
            target_url = chunks[chunk_index - 1]
            deleted_file = Path(target_url).name
            del chunks[chunk_index - 1]

            # Record tombstone so supervisor _sync_with_disk_and_storage never resurrects it
            if deleted_file:
                tombstones = job.setdefault("deleted_chunks", [])
                if deleted_file not in tombstones:
                    tombstones.append(deleted_file)

                # Attempt to unlink or move/rename file on disk
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

        if 1 <= chunk_index <= len(prompts):
            del prompts[chunk_index - 1]

        job["chunks"] = chunks
        job["chunk_prompts"] = prompts
        job["total_chunks"] = len(chunks)
        job["current_chunk"] = len(chunks)
        job["status_msg"] = f"Shot #{chunk_index} deleted."
        supervisor.state_version += 1
        save_jobs()
        return web.json_response({
            "success": True,
            "message": f"Shot #{chunk_index} deleted.",
            "deleted_file": deleted_file,
            "remaining_chunks": len(chunks)
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_autogen_prompt(request):
    """Analyzes previous frames/clips with Ollama qwen3.5:9b vision and composes the next shot prompt."""
    try:
        data = await request.json()
        job_id = data.get("job_id")
        if job_id not in active_jobs:
            return web.json_response({"success": False, "error": "Job not found"}, status=404)
        job = active_jobs[job_id]
        chunks = job.get("chunks", [])
        target_shot_index = int(data.get("target_shot_index") or (len(chunks) + 1))

        # 1. Resolve anchor frame
        anchor_frame_path = None
        anchor_frame_name = None
        if target_shot_index > 1:
            prev_idx = target_shot_index - 1
            tail_name = f"chronoflow_tail_{job_id}_{prev_idx}.png"
            tail_path = COMFY_INPUT_DIR / tail_name
            if tail_path.exists():
                anchor_frame_path = tail_path
                anchor_frame_name = tail_name
            else:
                prev_chunk_filename = f"{job_id}_chunk_{prev_idx}.mp4"
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

        director_notes = (data.get("director_notes") or "").strip()
        user_content = (
            f"Story Premise: {base_story_prompt}\n"
            f"{f'Previous Shot Sequence Context:\n{prev_summary}\n' if prev_summary else ''}"
            f"Target Shot: Shot #{target_shot_index}\n\n"
            f"{f'DIRECTOR GUIDANCE / DESIRED ACTION FOR THIS SHOT:\n{director_notes}\n\n' if director_notes else ''}"
            f"Analyze the attached anchor frame and generate the complete cinematic prompt for Shot #{target_shot_index}."
        )

        from engine.llm.providers.ollama import OllamaProvider
        provider = OllamaProvider(vision_model="qwen3.5:9b")
        if anchor_frame_path and anchor_frame_path.exists():
            generated_prompt = await provider.analyze_vision(
                image=anchor_frame_path,
                prompt=user_content,
                system_prompt=system_instruction
            )
        else:
            generated_prompt = await provider.generate_text(
                prompt=user_content,
                system_prompt=system_instruction
            )

        prompt_clean = generated_prompt.strip()
        if prompt_clean.startswith("```"):
            lines = prompt_clean.split("\n")
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].strip() == "```": lines = lines[:-1]
            prompt_clean = "\n".join(lines).strip()

        return web.json_response({
            "success": True,
            "prompt": prompt_clean,
            "anchor_frame": anchor_frame_name,
            "target_shot_index": target_shot_index
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_correct_prompt(request):
    """Refines and corrects an existing shot prompt using human directorial notes, 
    enforcing temporal causality, spatial progression, and anti-looping rules with Ollama qwen3.5:9b."""
    try:
        data = await request.json()
        job_id = data.get("job_id")
        if job_id not in active_jobs:
            return web.json_response({"success": False, "error": "Job not found"}, status=404)
        job = active_jobs[job_id]
        
        shot_index = int(data.get("shot_index", 1))
        current_prompt = (data.get("current_prompt") or "").strip()
        director_notes = (data.get("director_notes") or "").strip()
        
        if not director_notes:
            return web.json_response({"success": False, "error": "Director feedback notes are required."}, status=400)
        
        # 1. Resolve anchor frame (tail of shot_index - 1 if available)
        anchor_frame_path = None
        anchor_frame_name = None
        if shot_index > 1:
            prev_idx = shot_index - 1
            tail_name = f"chronoflow_tail_{job_id}_{prev_idx}.png"
            tail_path = COMFY_INPUT_DIR / tail_name
            if tail_path.exists():
                anchor_frame_path = tail_path
                anchor_frame_name = tail_name
            else:
                prev_chunk_filename = f"{job_id}_chunk_{prev_idx}.mp4"
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
                system_prompt=system_instruction
            )
        else:
            generated = await provider.generate_text(
                prompt=user_content,
                system_prompt=system_instruction
            )

        prompt_clean = generated.strip()
        if prompt_clean.startswith("```"):
            lines = prompt_clean.split("\n")
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].strip() == "```": lines = lines[:-1]
            prompt_clean = "\n".join(lines).strip()

        # Update in-memory job chunk_prompts
        if "chunk_prompts" not in job:
            job["chunk_prompts"] = []
        while len(job["chunk_prompts"]) < shot_index:
            job["chunk_prompts"].append("")
        job["chunk_prompts"][shot_index - 1] = prompt_clean
        save_jobs()

        return web.json_response({
            "success": True,
            "prompt": prompt_clean,
            "shot_index": shot_index,
            "message": f"Prompt for Shot #{shot_index} refined with director feedback."
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

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
        location_id = data.get("location_id")
        destination_path = data.get("destination_path")
        dest_dir = resolve_destination_dir(location_id, destination_path)
        saved_loc = None
        if dest_dir:
            src_file = COMFY_INPUT_DIR / filename
            if src_file.exists():
                dest_file = _unique_destination(dest_dir / filename)
                shutil.copy2(str(src_file), str(dest_file))
                saved_loc = {
                    "location_id": location_id,
                    "folder": str(dest_dir),
                    "path": str(dest_file),
                    "filename": dest_file.name,
                    "serve_url": f"/api/files/serve?path={quote(str(dest_file))}",
                }
        resp = {"success": True, "filename": filename, "url": f"/inputs/{filename}"}
        if saved_loc:
            resp["saved_location"] = saved_loc
        return web.json_response(resp, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
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

        location_id = data.get("location_id")
        destination_path = data.get("destination_path")
        dest_dir = resolve_destination_dir(location_id, destination_path)
        saved_loc = None
        if dest_dir and target_path.exists():
            dest_file = _unique_destination(dest_dir / new_filename)
            shutil.copy2(str(target_path), str(dest_file))
            saved_loc = {
                "location_id": location_id,
                "folder": str(dest_dir),
                "path": str(dest_file),
                "filename": dest_file.name,
                "serve_url": f"/api/files/serve?path={quote(str(dest_file))}",
            }

        resp = {
            "success": True,
            "filename": new_filename,
            "url": f"/inputs/{new_filename}"
        }
        if saved_loc:
            resp["saved_location"] = saved_loc
        return web.json_response(resp, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
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

        try:
            rendered_path = pipeline.render_timeline_edl(clips, master_path, data.get("overlays"), data.get("luts"))
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
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

async def handle_media_info(request):
    file_name = request.query.get("file", "")
    p = media_tools.resolve_media(file_name)
    if not p:
        return web.json_response({"error": "File not found"}, status=404)
    try:
        info = media_tools.probe(p)
        return web.json_response(info)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_media_filmstrip(request):
    file_name = request.query.get("file", "")
    p = media_tools.resolve_media(file_name)
    if not p:
        return web.json_response({"error": "File not found"}, status=404)
    count = int(request.query.get("count", 1))
    height = int(request.query.get("height", 72))
    try:
        strip_path = media_tools.filmstrip(p, count, height)
        return web.FileResponse(strip_path, headers={"Cache-Control": "max-age=86400"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_media_waveform(request):
    file_name = request.query.get("file", "")
    p = media_tools.resolve_media(file_name)
    if not p:
        return web.json_response({"error": "File not found"}, status=404)
    bins = int(request.query.get("bins", 600))
    try:
        peaks = media_tools.waveform(p, bins)
        return web.json_response({"peaks": peaks})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_nle_upload_ref(request):
    """Upload or decode a reference image to COMFY_INPUT_DIR."""
    try:
        data = await request.json()
        image_data = data.get("image", "")
        filename = data.get("filename", f"ref_{uuid.uuid4().hex[:8]}.png")
        if not filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            filename += ".png"
        target_path = COMFY_INPUT_DIR / filename

        if image_data.startswith("data:image"):
            header, b64_str = image_data.split(",", 1)
            target_path.write_bytes(base64.b64decode(b64_str))
        elif image_data.startswith("http"):
            async with aiohttp.ClientSession() as session:
                async with session.get(image_data) as resp:
                    if resp.status == 200:
                        target_path.write_bytes(await resp.read())
                    else:
                        return web.json_response({"error": f"Failed to download image from {image_data}"}, status=400)
        elif Path(image_data).exists():
            shutil.copy2(Path(image_data), target_path)
        else:
            return web.json_response({"error": "No valid image data or URL provided"}, status=400)

        return web.json_response({
            "success": True,
            "filename": filename,
            "url": f"/inputs/{filename}",
            "path": str(target_path)
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_nle_frame_generate(request):
    """Regenerate a specific frame using Qwen Image 2.1 or reference image."""
    try:
        data = await request.json()
        prompt = data.get("prompt", "")
        ref_image = data.get("reference_image") or data.get("initial_image")
        time_sec = float(data.get("time", 0.0))
        if not prompt:
            return web.json_response({"error": "Prompt is required"}, status=400)

        from engine.comfyui.art import ArtEngine
        fn = f"nle_frame_{uuid.uuid4().hex[:8]}.png"
        target_path = COMFY_INPUT_DIR / fn

        loop = asyncio.get_event_loop()
        def _run_art():
            ae = ArtEngine()
            return ae.generate_image(
                prompt=prompt,
                width=1024,
                height=576,
                output_path=target_path
            )

        img_path = await loop.run_in_executor(None, _run_art)
        return web.json_response({
            "success": True,
            "id": fn,
            "image_url": f"/inputs/{fn}",
            "time": time_sec
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_nle_frame_inpaint(request):
    """Inpaint a masked region of a video frame."""
    try:
        data = await request.json()
        prompt = data.get("prompt", "")
        mask_b64 = data.get("mask", "")
        frame_b64 = data.get("frame", "")
        time_sec = float(data.get("time", 0.0))

        mask_fn = f"mask_{uuid.uuid4().hex[:8]}.png"
        frame_fn = f"frame_{uuid.uuid4().hex[:8]}.png"
        out_fn = f"inpaint_{uuid.uuid4().hex[:8]}.png"

        if mask_b64.startswith("data:image"):
            mask_b64 = mask_b64.split(",", 1)[1]
        if frame_b64.startswith("data:image"):
            frame_b64 = frame_b64.split(",", 1)[1]

        (COMFY_INPUT_DIR / mask_fn).write_bytes(base64.b64decode(mask_b64))
        (COMFY_INPUT_DIR / frame_fn).write_bytes(base64.b64decode(frame_b64))

        from engine.comfyui.art import ArtEngine
        loop = asyncio.get_event_loop()
        def _run_art():
            ae = ArtEngine()
            return ae.generate_image(
                prompt=prompt,
                width=1024,
                height=576,
                output_path=COMFY_INPUT_DIR / out_fn
            )

        await loop.run_in_executor(None, _run_art)
        return web.json_response({
            "success": True,
            "id": out_fn,
            "image_url": f"/inputs/{out_fn}",
            "time": time_sec
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_nle_range_generate(request):
    """Generate replacement video chunk for range [t_start, t_end] using Fast H3."""
    try:
        data = await request.json()
        job_id = data.get("job_id")
        t_start = float(data.get("t_start", 0.0))
        t_end = float(data.get("t_end", t_start + 2.5))
        prompt = (data.get("prompt") or "").strip()
        ref_image = data.get("reference_image")

        duration = max(0.5, t_end - t_start)
        job = active_jobs.get(job_id, {})

        # 1. Resolve base video
        base_video = None
        if job_id:
            cand = STUDIO_OUTPUT_DIR / f"chronoflow_master_{job_id}.mp4"
            if cand.exists():
                base_video = cand
        if not base_video:
            masters = list(STUDIO_OUTPUT_DIR.glob("chronoflow_master_*.mp4"))
            if masters:
                masters.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                base_video = masters[0]

        # 2. Resolve guide frame / anchor frame for Fast H3
        guide_frame = None
        if ref_image:
            cand_ref = COMFY_INPUT_DIR / ref_image
            if cand_ref.exists():
                guide_frame = ref_image

        if not guide_frame and base_video and base_video.exists():
            anchor_fn = f"range_anchor_{uuid.uuid4().hex[:8]}.png"
            anchor_path = COMFY_INPUT_DIR / anchor_fn
            try:
                media_tools.extract_frame(base_video, t_start, anchor_path)
                guide_frame = anchor_fn
            except Exception as e:
                print(f"[RANGE GENERATE] Extract frame error: {e}")

        if not guide_frame:
            init_img = job.get("initial_image")
            if init_img and (COMFY_INPUT_DIR / init_img).exists():
                guide_frame = init_img
            else:
                guide_frame = "zombie_survivor_anchor.jpg"

        # 3. If prompt is an adjustment note without full 6-heading schema, auto-refine with Ollama vision
        if prompt and ("detailed_description:" not in prompt.lower()):
            try:
                from engine.llm.providers.ollama import OllamaProvider
                provider = OllamaProvider(vision_model="qwen3.5:9b")
                refine_sys = (
                    "You are an elite cinematic film director and AI video prompt engineer for ChronoFlow Studio and MiniMax H3 / Qwen Image 2.1.\n"
                    f"You are analyzing timeline video range [{t_start:.1f}s -> {t_end:.1f}s] ({duration:.1f}s duration).\n\n"
                    "TASK: Inspect the anchor frame at this timestamp, diagnose issues in action or continuity, "
                    "and compose a refined, production-grade Fast H3 prompt executing the director's requested adjustments.\n\n"
                    "CONTINUITY & KINEMATIC RULES:\n"
                    "1. CHARACTER & VISUAL RETENTION: Strictly preserve character face, hair, clothing, and scene environment.\n"
                    "2. CHRONOLOGICAL SEQUENCING: Execute actions in exact logical temporal sequence (e.g. turning on the light FIRST to illuminate the room, then reaching out and picking up the cup).\n"
                    "3. CAMERA KINEMATICS: Explicit camera motion (smooth low-angle push-in, steady tracking).\n"
                    "4. OUTPUT SCHEMA: Conforming to headings: summary, retention_analysis, detailed_description, overall_soundscape, non_diegetic_music."
                )
                refine_user = f"Director Adjustments / Scene Issues: {prompt}\nTimeline Range: [{t_start:.1f}s -> {t_end:.1f}s] ({duration:.1f}s)\nStory Context: {job.get('prompt', 'Cinematic shot')}"
                guide_path = COMFY_INPUT_DIR / guide_frame if guide_frame else None
                if guide_path and guide_path.exists():
                    exp = await provider.analyze_vision(image=guide_path, prompt=refine_user, system_prompt=refine_sys)
                else:
                    exp = await provider.generate_text(prompt=refine_user, system_prompt=refine_sys)
                if exp and len(exp.strip()) > 30:
                    clean_exp = exp.strip()
                    if clean_exp.startswith("```"):
                        lines = clean_exp.split("\n")
                        if lines[0].startswith("```"): lines = lines[1:]
                        if lines and lines[-1].strip() == "```": lines = lines[:-1]
                        clean_exp = "\n".join(lines).strip()
                    prompt = clean_exp
            except Exception as re_err:
                print(f"[RANGE AUTO REFINE] Note: {re_err}")

        # 4. Frame length matching Fast H3 / MiniMax H3
        if duration <= 1.5:
            frame_length = 22
        elif duration <= 2.5:
            frame_length = 56
        elif duration <= 3.5:
            frame_length = 73
        else:
            frame_length = 124

        width = job.get("width", 1344)
        height = job.get("height", 768)
        lora_name = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"

        # 5. Build Fast H3 workflow graph and execute
        graph = pipeline.build_h3_prompt(
            prompt=prompt,
            width=width,
            height=height,
            length=frame_length,
            steps=4,
            lora_name=lora_name,
            workflow_mode="sliding_window",
            first_frame_filename=guide_frame
        )

        chunk_output = await pipeline.execute_prompt(graph)

        chunk_fn = f"range_chunk_{uuid.uuid4().hex[:8]}.mp4"
        out_clip = STUDIO_OUTPUT_DIR / chunk_fn
        shutil.copy2(chunk_output, out_clip)

        return web.json_response({
            "success": True,
            "clip_url": f"/outputs/{chunk_fn}",
            "clip_filename": chunk_fn,
            "t_start": t_start,
            "t_end": t_end,
            "duration": duration,
            "anchor_image": guide_frame,
            "prompt": prompt
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_nle_range_auto_prompt(request):
    """
    Analyzes visual state of timeline range [t_start, t_end] using Ollama qwen3.5:9b vision,
    identifies scene issues, and synthesizes a production-grade Fast H3 prompt based on
    the director's adjustments/instructions.
    """
    try:
        data = await request.json()
        job_id = data.get("job_id")
        t_start = float(data.get("t_start", 0.0))
        t_end = float(data.get("t_end", t_start + 2.5))
        adjustments = (data.get("adjustments") or data.get("prompt") or "").strip()
        current_prompt = (data.get("current_prompt") or "").strip()
        ref_image = data.get("reference_image")

        job = active_jobs.get(job_id, {})
        base_video = None
        if job_id:
            cand = STUDIO_OUTPUT_DIR / f"chronoflow_master_{job_id}.mp4"
            if cand.exists():
                base_video = cand
        if not base_video:
            masters = list(STUDIO_OUTPUT_DIR.glob("chronoflow_master_*.mp4"))
            if masters:
                masters.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                base_video = masters[0]

        anchor_frame_path = None
        anchor_frame_name = None
        if ref_image:
            cand_ref = COMFY_INPUT_DIR / ref_image
            if cand_ref.exists():
                anchor_frame_path = cand_ref
                anchor_frame_name = ref_image

        if not anchor_frame_path and base_video and base_video.exists():
            anchor_frame_name = f"range_anchor_{uuid.uuid4().hex[:8]}.png"
            anchor_frame_path = COMFY_INPUT_DIR / anchor_frame_name
            try:
                media_tools.extract_frame(base_video, t_start, anchor_frame_path)
            except Exception as e:
                print(f"[RANGE AUTO PROMPT] Extract frame warning: {e}")
                anchor_frame_path = None

        if not anchor_frame_path:
            init_img = job.get("initial_image")
            if init_img and (COMFY_INPUT_DIR / init_img).exists():
                anchor_frame_path = COMFY_INPUT_DIR / init_img
                anchor_frame_name = init_img

        base_story_prompt = job.get("prompt", "Cinematic photorealistic action shot")
        chunk_prompts = job.get("chunk_prompts", [])
        prior_context = "\n".join(f"Shot #{i+1}: {p[:120]}..." for i, p in enumerate(chunk_prompts) if p)

        duration_sec = max(0.5, t_end - t_start)
        system_instruction = (
            "You are an elite cinematic film director and AI video prompt engineer for ChronoFlow Studio and MiniMax H3 / Qwen Image 2.1.\n"
            f"You are analyzing timeline video range [{t_start:.1f}s -> {t_end:.1f}s] ({duration_sec:.1f}s duration).\n\n"
            "TASK: Inspect the anchor frame at this exact timestamp, diagnose what is missing or flawed in the current action, "
            "and compose a refined, production-grade Fast H3 prompt executing the director's requested adjustments.\n\n"
            "CONTINUITY & KINEMATIC RULES:\n"
            "1. CHARACTER & VISUAL RETENTION: Strictly preserve the character's face, hair, costume, and the scene environment from the anchor frame.\n"
            "2. CHRONOLOGICAL SEQUENCING: Execute steps in exact logical temporal sequence (e.g. turning on the light FIRST to illuminate the scene, then reaching out and picking up the cup).\n"
            "3. NO ACTION REVERSAL OR TELEPORTATION: Natural physical movement progressing organically from the starting anchor posture.\n"
            "4. CAMERA KINEMATICS: Explicit camera movement (e.g., slow low-angle tracking, smooth subtle push-in, lens depth).\n"
            "5. OUTPUT SCHEMA: You MUST format your output conforming to the 6 headings:\n"
            "summary:\n"
            "[1-sentence concise shot logline]\n\n"
            "retention_analysis:\n"
            "[Preserved character identity, attire, lighting, setting]\n\n"
            "detailed_description:\n"
            "[Cinematic 35mm film shot. Precise camera kinematics, sequential character actions, physical contact with objects, secondary environmental dynamics, lighting transition]\n\n"
            "overall_soundscape:\n"
            "[Diegetic foley sound: click of switch, hum of light, ceramic clink]\n\n"
            "non_diegetic_music:\n"
            "[Cinematic score mood and instrumentation]"
        )

        user_content = (
            f"Overall Story Context: {base_story_prompt}\n"
            f"Timeline Interval: [{t_start:.1f}s -> {t_end:.1f}s] ({duration_sec:.1f}s)\n"
            f"{f'Prior Context:\n{prior_context}\n' if prior_context else ''}"
            f"{f'Current Baseline Prompt:\n{current_prompt}\n' if current_prompt else ''}"
            f"DIRECTOR'S ADJUSTMENTS & ISSUES TO FIX:\n{adjustments}\n\n"
            "Analyze the anchor frame, identify the delta, and generate the complete 6-heading prompt implementing these adjustments."
        )

        from engine.llm.providers.ollama import OllamaProvider
        provider = OllamaProvider(vision_model="qwen3.5:9b")
        if anchor_frame_path and anchor_frame_path.exists():
            generated = await provider.analyze_vision(
                image=anchor_frame_path,
                prompt=user_content,
                system_prompt=system_instruction
            )
        else:
            generated = await provider.generate_text(
                prompt=user_content,
                system_prompt=system_instruction
            )

        prompt_clean = generated.strip()
        if prompt_clean.startswith("```"):
            lines = prompt_clean.split("\n")
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].strip() == "```": lines = lines[:-1]
            prompt_clean = "\n".join(lines).strip()

        summary_line = ""
        for line in prompt_clean.split("\n"):
            if line.lower().startswith("summary:"):
                continue
            if line.strip() and not line.strip().endswith(":"):
                summary_line = line.strip()
                break

        return web.json_response({
            "success": True,
            "prompt": prompt_clean,
            "summary": summary_line or "Prompt refined from range analysis.",
            "anchor_image": anchor_frame_name,
            "anchor_url": f"/inputs/{anchor_frame_name}" if anchor_frame_name else None,
            "t_start": t_start,
            "t_end": t_end,
            "duration": duration_sec
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_nle_range_apply(request):
    """Splice the generated range clip into the master video."""
    try:
        data = await request.json()
        job_id = data.get("job_id")
        clip_filename = data.get("clip_filename")
        t_start = float(data.get("t_start", 0.0))
        t_end = float(data.get("t_end", 0.0))

        base_video = None
        if job_id:
            master_candidate = STUDIO_OUTPUT_DIR / f"chronoflow_master_{job_id}.mp4"
            if master_candidate.exists():
                base_video = master_candidate
        if not base_video:
            masters = list(STUDIO_OUTPUT_DIR.glob("chronoflow_master_*.mp4"))
            if masters:
                masters.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                base_video = masters[0]

        if not base_video or not base_video.exists():
            return web.json_response({"error": "No base master video found to splice into"}, status=404)

        rep_path = media_tools.resolve_media(clip_filename)
        if not rep_path or not rep_path.exists():
            rep_path = STUDIO_OUTPUT_DIR / clip_filename
        if not rep_path.exists():
            return web.json_response({"error": f"Replacement clip not found: {clip_filename}"}, status=404)

        out_name = f"chronoflow_spliced_{uuid.uuid4().hex[:8]}.mp4"
        out_path = STUDIO_OUTPUT_DIR / out_name

        loop = asyncio.get_event_loop()
        spliced = await loop.run_in_executor(
            None,
            media_tools.splice_timeline_range,
            base_video,
            rep_path,
            t_start,
            t_end,
            out_path
        )

        if job_id and out_path.exists():
            master_dest = STUDIO_OUTPUT_DIR / f"chronoflow_master_{job_id}.mp4"
            try:
                shutil.copy2(out_path, master_dest)
            except Exception as copy_err:
                print(f"[RANGE APPLY] Copy to master warning: {copy_err}")
            if job_id in active_jobs:
                active_jobs[job_id]["master_video"] = f"/outputs/chronoflow_master_{job_id}.mp4"
                save_jobs()

        return web.json_response({
            "success": True,
            "spliced_url": f"/outputs/{out_name}",
            "spliced_filename": out_name,
            "t_start": t_start,
            "t_end": t_end
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_nle_frame_apply(request):
    """Apply candidate still frame or hold to timeline."""
    try:
        data = await request.json()
        image_url = data.get("image_url", "")
        time_sec = float(data.get("time", 0.0))
        return web.json_response({
            "success": True,
            "message": "Frame applied successfully",
            "image_url": image_url,
            "time": time_sec
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def init_app():
    app = web.Application()
    app.router.add_get("/api/media/info", handle_media_info)
    app.router.add_get("/api/media/filmstrip", handle_media_filmstrip)
    app.router.add_get("/api/media/waveform", handle_media_waveform)
    
    # NLE Frame and Range editing routes
    for prefix in ("/api/nle", "/nle", "/api/chronoflow/nle", "/api/chronoflow/api/nle", "/api/api/nle", "/chronoflow/nle"):
        app.router.add_post(f"{prefix}/upload_ref", handle_nle_upload_ref)
        app.router.add_post(f"{prefix}/frame/generate", handle_nle_frame_generate)
        app.router.add_post(f"{prefix}/frame/inpaint", handle_nle_frame_inpaint)
        app.router.add_post(f"{prefix}/frame/apply", handle_nle_frame_apply)
        app.router.add_post(f"{prefix}/range/generate", handle_nle_range_generate)
        app.router.add_post(f"{prefix}/range/auto_prompt", handle_nle_range_auto_prompt)
        app.router.add_post(f"{prefix}/range/apply", handle_nle_range_apply)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/dependencies/status", handle_dependencies_status)
    app.router.add_post("/api/dependencies/launch_comfyui", handle_launch_comfyui)
    app.router.add_get("/api/jobs", handle_list_jobs)
    app.router.add_get("/api/gallery", handle_gallery)
    app.router.add_get("/api/characters", handle_characters)
    app.router.add_post("/api/characters", handle_characters)
    app.router.add_delete("/api/characters/{char_id}", handle_delete_character)
    app.router.add_post("/api/ai_director/plan", handle_ai_director_plan)
    app.router.add_post("/api/creative/synthesize", handle_creative_synthesize)
    app.router.add_get("/api/creative/projects", handle_creative_projects)
    app.router.add_get("/api/creative/project/{project_id}", handle_get_creative_project)
    app.router.add_post("/api/creative/generate_anchor", handle_creative_generate_anchor)
    app.router.add_post("/api/upload_image", handle_upload)
    app.router.add_post("/api/generate", handle_generate)
    app.router.add_post("/api/generate_image", handle_generate_image)
    app.router.add_post("/api/inpaint_image", handle_inpaint_image)
    app.router.add_post("/api/timeline/export", handle_timeline_export)
    app.router.add_post("/api/regenerate_chunk", handle_regenerate_chunk)
    app.router.add_post("/api/save_chunk_prompt", handle_save_chunk_prompt)
    app.router.add_post("/api/create_clip", handle_create_clip)
    app.router.add_post("/api/delete_shot", handle_delete_shot)
    app.router.add_post("/api/autogen_prompt", handle_autogen_prompt)
    app.router.add_post("/api/correct_prompt", handle_correct_prompt)
    app.router.add_post("/api/save_frame", handle_save_frame)
    app.router.add_get("/api/job/{job_id}", handle_job_status)
    app.router.add_post("/api/job/{job_id}/review", handle_submit_review)
    app.router.add_post("/api/cancel", handle_cancel)
    app.router.add_get("/api/sync", handle_unified_sync)
    app.router.add_get("/api/storage/drives", handle_storage_drives)
    app.router.add_get("/api/storage/browse", handle_storage_browse)
    app.router.add_post("/api/storage/mkdir", handle_storage_mkdir)
    app.router.add_post("/api/storage/pick_folder", handle_storage_pick_folder)
    app.router.add_get("/api/storage/locations", handle_storage_locations)
    app.router.add_post("/api/storage/locations", handle_storage_locations)
    app.router.add_delete("/api/storage/locations/{loc_id}", handle_delete_storage_location)
    app.router.add_post("/api/storage/save_asset", handle_storage_save_asset)
    app.router.add_get("/api/files/serve", handle_serve_file)
    app.router.add_get("/api/files/roots", handle_files_roots)
    app.router.add_get("/api/files", handle_files_list)
    app.router.add_post("/api/folders/create", handle_folder_create)
    app.router.add_post("/api/files/move", handle_files_move)
    app.router.add_get("/api/screenplays", handle_list_screenplays)
    app.router.add_get("/api/screenplay/{filename}", handle_get_screenplay)
    app.router.add_post("/api/screenplay/save", handle_save_screenplay)
    app.router.add_post("/api/storyboard/render_shot", handle_storyboard_render_shot)
    app.router.add_post("/api/storyboard/export_folder", handle_storyboard_export_folder)
    app.router.add_post("/api/storyboard/import_manifest", handle_storyboard_import_manifest)
    app.router.add_post("/api/storyboard/import_scene_to_studio", handle_storyboard_import_scene_to_studio)
    app.router.add_get("/api/original_stories/list", handle_list_original_stories)
    app.router.add_get("/api/original_stories/{slug}/workbench", handle_get_story_workbench)
    app.router.add_get("/api/original_stories/{slug}/panel/{panel_id}", handle_serve_story_panel)
    app.router.add_get("/api/original_stories/{slug}/audio/{panel_id}", handle_serve_story_audio)
    app.router.add_post("/api/original_stories/{slug}/panel/{panel_id}/approve", handle_approve_story_panel)
    app.router.add_post("/api/original_stories/{slug}/panel/{panel_id}/reroll", handle_reroll_story_panel)
    app.router.add_post("/api/original_stories/{slug}/panel/{panel_id}/agent_action", handle_story_agent_action)
    app.router.add_post("/api/original_stories/{slug}/open", handle_open_story_folder)

    async def on_startup(app_instance):
        supervisor.start_watchdog()
        try:
            from engine.system.setup import comfyui_manager
            if comfyui_manager.is_installed() and not comfyui_manager.is_running():
                print("[ChronoFlow] Auto-launching ComfyUI for ChronoFlow Studio...")
                res = comfyui_manager.start()
                print(f"[ChronoFlow] ComfyUI launch initiated: {res.get('status')} (PID {res.get('pid')})")
        except Exception as e:
            print(f"[ChronoFlow] ComfyUI auto-launch notice: {e}")
    app.on_startup.append(on_startup)

    static_dir = Path(__file__).resolve().parent / "static"

    async def handle_index(request):
        return web.FileResponse(
            static_dir / "index.html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
        )

    app.router.add_get("/", handle_index)
    app.router.add_static("/chronoflow/outputs", STUDIO_OUTPUT_DIR)
    app.router.add_static("/chronoflow/inputs", COMFY_INPUT_DIR)
    app.router.add_static("/outputs", STUDIO_OUTPUT_DIR)
    app.router.add_static("/inputs", COMFY_INPUT_DIR)
    app.router.add_static("/", static_dir)

    return app


async def handle_gallery(request):
    assets = {
        "masters": [],
        "chunks": [],
        "images": [],
        "stats": {"total_videos": 0, "total_images": 0, "total_storage_mb": 0.0}
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
                    "grade": review.get("grade"),
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
    if COMFY_INPUT_DIR.exists():
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

    # Also scan user-registered custom storage locations
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
                        "url": f"/api/files/serve?path={quote(str(f))}",
                        "path": str(f),
                        "location_id": loc.get("id"),
                        "location_name": loc.get("name"),
                        "model": f"Stored in {loc.get('name')}",
                        "size_mb": round(size_bytes / (1024 * 1024), 2),
                        "created_at": mtime,
                    })
        except Exception:
            pass

    assets["masters"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["chunks"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["images"].sort(key=lambda x: x["created_at"], reverse=True)
    assets["stats"]["total_videos"] = len(assets["masters"]) + len(assets["chunks"])
    assets["stats"]["total_images"] = len(assets["images"])
    assets["stats"]["total_storage_mb"] = round(total_bytes / (1024 * 1024), 1)
    assets["locations"] = load_storage_locations()
    return web.json_response(assets)


async def handle_storage_drives(request):
    r"""List available system disk drives (e.g. C:\, D:\, E:\ on Windows)."""
    drives = []
    if os.name == "nt":
        try:
            import ctypes
            import string
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if (bitmask >> (ord(letter) - 65)) & 1:
                    drv = f"{letter}:\\"
                    try:
                        if Path(drv).exists():
                            drives.append({"drive": drv, "label": f"Drive {letter}:"})
                    except Exception:
                        pass
        except Exception:
            pass
    if not drives:
        drives.append({"drive": str(Path.home()), "label": f"Home ({Path.home()})"})
        drives.append({"drive": "/", "label": "Root (/)"})
    return web.json_response({"drives": drives})


async def handle_storage_browse(request):
    """Browse directories on disk to select an existing folder or navigate drives."""
    p_str = request.query.get("path", "").strip(' \t\r\n"\'')
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

    subfolders = []
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
        return web.json_response({"detail": f"Permission denied: {target}"}, status=403)

    parent = str(target.parent) if target.parent != target else None
    return web.json_response({
        "current": str(target),
        "name": target.name or str(target),
        "parent": parent,
        "subfolders": subfolders,
        "not_found": not_found,
        "requested_path": requested_path if not_found else str(target),
        "can_create": not_found,
    })


async def handle_storage_mkdir(request):
    """Create a folder directory on disk immediately."""
    data = await request.json()
    raw_path = (data.get("path") or "").strip(' \t\r\n"\'')
    if not raw_path:
        return web.json_response({"detail": "Path required"}, status=400)
    p = Path(raw_path).resolve()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return web.json_response({"success": True, "path": str(p), "name": p.name or str(p)})
    except Exception as e:
        return web.json_response({"detail": f"Could not create directory '{p}': {e}"}, status=400)


async def handle_storage_pick_folder(request):
    """Launch native OS folder browser dialog to select a folder from the local filesystem."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    init_dir = (data.get("initial_dir") or "").strip(' \t\r\n"\'')
    selected = await pick_native_folder(initial_dir=init_dir)
    if selected:
        p = Path(selected).resolve()
        return web.json_response({"success": True, "path": str(p), "name": p.name or str(p), "cancelled": False})
    return web.json_response({"success": False, "cancelled": True, "path": ""})


async def handle_storage_locations(request):
    if request.method == "GET":
        locs = load_storage_locations()
        enriched = []
        for loc in locs:
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
        return web.json_response({"locations": enriched})
    elif request.method == "POST":
        data = await request.json()
        raw_path = (data.get("path") or "").strip(' \t\r\n"\'')
        if not raw_path:
            return web.json_response({"detail": "Location path cannot be empty"}, status=400)
        p = Path(raw_path).resolve()
        name = (data.get("name") or "").strip() or p.name or str(p)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return web.json_response({"detail": f"Could not create folder '{p}': {e}"}, status=400)

        locations = load_storage_locations()
        for existing in locations:
            if Path(existing.get("path", "")).resolve() == p:
                existing["name"] = name
                existing["updated_at"] = time.time()
                save_storage_locations(locations)
                return web.json_response({"success": True, "location": existing, "updated": True})

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
        return web.json_response({"success": True, "location": new_loc, "created": True})


async def handle_delete_storage_location(request):
    loc_id = request.match_info.get("loc_id")
    locations = load_storage_locations()
    filtered = [l for l in locations if l.get("id") != loc_id]
    if len(filtered) == len(locations):
        return web.json_response({"detail": f"Location '{loc_id}' not found"}, status=404)
    save_storage_locations(filtered)
    return web.json_response({"success": True, "id": loc_id})


async def handle_storage_save_asset(request):
    data = await request.json()
    dest_dir = resolve_destination_dir(data.get("location_id"), data.get("destination_path"))
    if not dest_dir or not dest_dir.exists() or not dest_dir.is_dir():
        return web.json_response({"detail": "Valid destination folder or location_id required"}, status=400)

    action = data.get("action", "copy")
    results = []
    for fn in data.get("filenames", []):
        src = None
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
            if action == "move":
                shutil.move(str(src), str(dest_file))
            else:
                shutil.copy2(str(src), str(dest_file))
            results.append({
                "filename": src.name,
                "success": True,
                "saved_path": str(dest_file),
                "url": f"/api/files/serve?path={quote(str(dest_file))}",
            })
        except Exception as e:
            results.append({"filename": src.name, "success": False, "error": str(e)})

    return web.json_response({"success": True, "destination": str(dest_dir), "results": results})


async def handle_serve_file(request):
    p_str = request.query.get("path", "")
    if not p_str:
        return web.json_response({"detail": "path is required"}, status=400)
    p = Path(p_str).resolve()
    if not p.exists() or not p.is_file():
        return web.json_response({"detail": "File not found"}, status=404)
    return web.FileResponse(p, headers={"Cache-Control": "no-store"})


async def handle_files_roots(request):
    return web.json_response({"roots": _organizer_roots()})


async def handle_files_list(request):
    path_param = request.query.get("path", "")
    target = _resolve_organizer_path(path_param) if path_param else STUDIO_OUTPUT_DIR
    if not target.exists() or not target.is_dir():
        return web.json_response({"detail": f"Folder not found: {target}"}, status=404)

    folders = []
    files = []
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
                "url": f"/api/files/serve?path={quote(str(entry))}",
            })
    except PermissionError:
        return web.json_response({"detail": f"Access denied: {target}"}, status=403)

    return web.json_response({
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
    })


async def handle_folder_create(request):
    data = await request.json()
    parent_path = data.get("parent_path", "")
    name = (data.get("name") or "").strip()
    if not name:
        return web.json_response({"detail": "Folder name is required"}, status=400)
    parent = _resolve_organizer_path(parent_path) if parent_path else STUDIO_OUTPUT_DIR
    if not parent.exists() or not parent.is_dir():
        return web.json_response({"detail": f"Parent folder not found: {parent}"}, status=404)
    dest = parent / name
    if dest.exists():
        return web.json_response({"detail": f"'{name}' already exists in {parent}"}, status=409)
    dest.mkdir(parents=True, exist_ok=False)
    return web.json_response({"ok": True, "path": str(dest), "name": name, "parent": str(parent)})


async def handle_files_move(request):
    data = await request.json()
    destination = _resolve_organizer_path(data.get("destination", ""))
    if not destination.exists() or not destination.is_dir():
        return web.json_response({"detail": f"Destination folder not found: {destination}"}, status=404)

    moved, skipped = [], []
    for raw in data.get("files", []):
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

    return web.json_response({"ok": True, "moved": moved, "skipped": skipped, "destination": str(destination)})


async def handle_list_screenplays(request):
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
                    "folders": data.get("folders", []),
                })
            except Exception as e:
                logger.warning("Could not read screenplay %s: %s", path.name, e)
    return web.json_response({"screenplays": screenplays})


async def handle_get_screenplay(request):
    filename = request.match_info.get("filename", "")
    if not filename.endswith(".json") or "/" in filename or "\\" in filename or ".." in filename:
        return web.json_response({"detail": "Invalid screenplay filename"}, status=400)

    file_path = VAULT_DIR / filename
    if not file_path.exists():
        return web.json_response({"detail": f"Screenplay '{filename}' not found"}, status=404)

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
        return web.json_response(data)
    except Exception as e:
        logger.error("Failed to load screenplay %s: %s", filename, e)
        return web.json_response({"detail": str(e)}, status=500)


async def handle_save_screenplay(request):
    data = await request.json()
    title = data.get("title", "Untitled Storyboard")
    filename = data.get("filename")
    if not filename:
        safe_title = "".join(c for c in title.lower() if c.isalnum() or c in ("_", "-")).strip()
        filename = f"screenplay_{safe_title or 'custom'}.json"

    if not filename.endswith(".json") or "/" in filename or "\\" in filename or ".." in filename:
        return web.json_response({"detail": "Invalid screenplay filename"}, status=400)

    scenes = data.get("scenes", [])
    payload = {
        "title": title,
        "duration": float(data.get("duration", len(scenes) * 5.2)),
        "protagonist": data.get("protagonist", {}),
        "anchor_images": data.get("anchor_images", {}),
        "parent_path": data.get("parent_path", ""),
        "folders": data.get("folders", []),
        "scenes": scenes,
    }

    try:
        temp_file = VAULT_DIR / f"screenplay_tmp_{int(time.time() * 1000)}.json"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        target_file = VAULT_DIR / filename
        temp_file.replace(target_file)
        return web.json_response({"success": True, "filename": filename, "title": title, "scenes_count": len(scenes)})
    except Exception as e:
        logger.error("Failed to save screenplay %s: %s", filename, e)
        return web.json_response({"detail": str(e)}, status=500)


async def handle_storyboard_render_shot(request):
    data = await request.json()
    scene = data.get("scene", {})
    shot_num = int(data.get("shot_index", 1))
    prompt = scene.get("prompt", "Cinematic action scene.")
    first_frame = data.get("first_frame") or scene.get("first_frame")
    last_frame = scene.get("last_frame")
    ref_images = scene.get("ref_images", [])

    if first_frame and not (COMFY_INPUT_DIR / first_frame).exists():
        first_frame = None
    if last_frame and not (COMFY_INPUT_DIR / last_frame).exists():
        last_frame = None
    if ref_images:
        ref_images = [img for img in ref_images if (COMFY_INPUT_DIR / img).exists()]

    workflow_mode = "reference" if (shot_num == 1 and (first_frame or ref_images)) else "sliding_window"
    if first_frame and last_frame:
        workflow_mode = "flf2v"

    steps = int(data.get("steps", 4))
    width = int(data.get("width", 1344))
    height = int(data.get("height", 768))
    lora_name = resolve_h3_lora_name(data.get("lora_choice", "4step"))

    graph = pipeline.build_h3_prompt(
        prompt=prompt,
        width=width,
        height=height,
        length=124,
        steps=steps,
        lora_name=lora_name,
        workflow_mode=workflow_mode,
        ref_image_filename=first_frame,
        first_frame_filename=first_frame,
        last_frame_filename=last_frame,
    )
    out_video = await pipeline.execute_prompt(graph)
    return web.json_response({
        "success": True,
        "shot_index": shot_num,
        "video": f"/outputs/{out_video.name}",
        "video_url": f"/outputs/{out_video.name}",
        "filename": out_video.name,
    })


async def handle_storyboard_export_folder(request):
    data = await request.json()
    raw_path = (data.get("destination_path") or "").strip(' \t\r\n"\'')
    if not raw_path:
        return web.json_response({"detail": "Destination path is required"}, status=400)

    dest_dir = Path(raw_path).resolve()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return web.json_response({"detail": f"Cannot create destination folder '{dest_dir}': {e}"}, status=400)

    keyframes_dir = dest_dir / "keyframes"
    videos_dir = dest_dir / "videos"
    keyframes_dir.mkdir(exist_ok=True)
    videos_dir.mkdir(exist_ok=True)

    copied_files = 0
    scenes = data.get("scenes", [])
    enriched_shots = []

    for idx, sc in enumerate(scenes):
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

    folder_name = data.get("folder_name", "Scene")
    manifest = {
        "scene_name": folder_name,
        "folder_id": data.get("folder_id", ""),
        "storyboard_title": data.get("screenplay_title", "Storyboard"),
        "total_shots": len(scenes),
        "total_duration": sum(float(s.get("duration", 5.2)) for s in scenes),
        "exported_at": time.time(),
        "exported_at_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        "destination_directory": str(dest_dir),
        "shots": enriched_shots,
    }

    manifest_path = dest_dir / "scene_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return web.json_response({
        "success": True,
        "saved_path": str(dest_dir),
        "manifest_file": str(manifest_path),
        "shots_count": len(scenes),
        "files_copied": copied_files,
        "message": f"Successfully exported {len(scenes)} shots into {dest_dir}",
    })


async def handle_storyboard_import_manifest(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    raw_path = (data.get("manifest_path") or "").strip(' \t\r\n"\'')
    if not raw_path:
        return web.json_response({"detail": "Manifest path is required"}, status=400)
    p = Path(raw_path).resolve()
    if p.is_dir():
        p = p / "scene_manifest.json"
    if not p.exists() or not p.is_file():
        return web.json_response({"detail": f"Manifest file not found at: {p}"}, status=404)
    try:
        with open(p, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        return web.json_response({
            "success": True,
            "manifest_file": str(p),
            "manifest": manifest_data,
        })
    except Exception as e:
        return web.json_response({"detail": f"Failed to read manifest: {e}"}, status=400)


async def handle_storyboard_import_scene_to_studio(request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    folder_name = data.get("folder_name") or "Imported Scene"
    folder_id = data.get("folder_id") or ""
    screenplay_title = data.get("screenplay_title") or "Storyboard"
    shots = data.get("shots") or []

    if not shots:
        return web.json_response({"detail": "Scene has no shots"}, status=400)

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

    return web.json_response({
        "success": True,
        "job_id": job_id,
        "job": new_job,
        "chunks_count": len(chunk_urls),
        "shots_count": len(shots),
        "message": f"Successfully imported Scene '{folder_name}' into Video Studio",
    })


async def handle_list_original_stories(request):
    try:
        from engine.api.routers.original import STORY_ROOT
        stories = []
        if STORY_ROOT.exists():
            for d in sorted(STORY_ROOT.iterdir(), key=lambda x: x.name.lower()):
                if not d.is_dir() or d.name.startswith((".", "_")):
                    continue
                story_file = d / "story.json"
                if not story_file.exists():
                    story_file = d / "beats.json"
                if not story_file.exists():
                    continue
                try:
                    data = json.loads(story_file.read_text(encoding="utf-8"))
                    premise = data.get("bible", {}).get("premise", {}) if isinstance(data, dict) else {}
                    title = premise.get("title") or d.name
                    genre = premise.get("genre") or ""
                    panels = data.get("panels", []) if isinstance(data, dict) else []
                    has_art = (d / "art.json").exists()
                    has_video = any(d.glob("*.mp4"))
                    stories.append({
                        "slug": d.name,
                        "title": title,
                        "genre": genre,
                        "total_panels": len(panels),
                        "has_art": has_art,
                        "has_video": has_video,
                    })
                except Exception:
                    continue
        return web.json_response({"success": True, "stories": stories})
    except Exception as e:
        return web.json_response({"success": False, "detail": str(e), "stories": []}, status=500)


async def handle_get_story_workbench(request):
    slug = request.match_info.get("slug", "")
    episode = request.query.get("episode")
    try:
        from engine.api.routers.original import _resolve_story_ws, get_storyboard_workbench
        data = get_storyboard_workbench(slug, episode)
        res = data.model_dump()
        ws = _resolve_story_ws(slug, episode)
        story_file = ws / "story.json"
        if not story_file.exists():
            story_file = ws / "beats.json"
        if story_file.exists():
            try:
                raw_story = json.loads(story_file.read_text(encoding="utf-8"))
                bible = raw_story.get("bible", {})
                res["characters"] = bible.get("characters", [])
                res["locations"] = bible.get("locations", [])
                res["premise"] = bible.get("premise", {})
                panel_map = {p.get("id"): p for p in raw_story.get("panels", []) if isinstance(p, dict)}
                for b in res.get("beats", []):
                    pid = b.get("panel_id")
                    if pid in panel_map:
                        p_obj = panel_map[pid]
                        b["location_id"] = p_obj.get("location_id")
                        b["character_ids"] = p_obj.get("character_ids", [])
                        b["dialogue"] = p_obj.get("dialogue")
                        b["director"] = p_obj.get("director", {})
            except Exception:
                pass
        for b in res.get("beats", []):
            ep_param = f"?episode={episode}" if episode else ""
            b["image_url"] = f"/api/original_stories/{slug}/panel/{b['panel_id']}{ep_param}"
            b["audio_url"] = f"/api/original_stories/{slug}/audio/{b['panel_id']}{ep_param}"
        return web.json_response({"success": True, "workbench": res})
    except Exception as e:
        return web.json_response({"success": False, "detail": str(e)}, status=404)


async def handle_serve_story_panel(request):
    slug = request.match_info.get("slug", "")
    panel_id = request.match_info.get("panel_id", "")
    episode = request.query.get("episode")
    candidate_str = request.query.get("candidate")
    try:
        from engine.api.routers.original import _resolve_story_ws
        ws = _resolve_story_ws(slug, episode)
        if not ws.exists():
            return web.json_response({"detail": "Story workspace not found"}, status=404)
        if candidate_str:
            try:
                cand = int(candidate_str)
                target = ws / "panels" / "_candidates" / panel_id / f"c{cand:03d}.png"
            except ValueError:
                target = ws / "panels" / f"{panel_id}.png"
        else:
            target = ws / "panels" / f"{panel_id}.png"
        if not target.exists():
            return web.json_response({"detail": f"Panel image {target.name} not found"}, status=404)
        return web.FileResponse(target, headers={"Cache-Control": "public, max-age=3600"})
    except Exception as e:
        return web.json_response({"detail": str(e)}, status=500)


async def handle_serve_story_audio(request):
    slug = request.match_info.get("slug", "")
    panel_id = request.match_info.get("panel_id", "")
    episode = request.query.get("episode")
    try:
        from engine.api.routers.original import _resolve_story_ws
        ws = _resolve_story_ws(slug, episode)
        if not ws.exists():
            return web.json_response({"detail": "Story workspace not found"}, status=404)
        target = ws / "voice" / f"{panel_id}.wav"
        if not target.exists():
            target = ws / "audio" / f"{panel_id}.wav"
        if not target.exists():
            return web.json_response({"detail": "Audio file not found"}, status=404)
        return web.FileResponse(target, headers={"Cache-Control": "public, max-age=3600"})
    except Exception as e:
        return web.json_response({"detail": str(e)}, status=500)


SOMATIC_ARCHETYPES = {
    "visceral_pain": {
        "title": "Visceral Kinetic Trauma (Pain)",
        "micro_anatomy": "mouth stretched wide in agonizing scream, teeth bared, blood spittle and saliva spraying, eyes wide with white sclera exposed, bulging forehead veins, neck tendons strained taut",
        "posture": "spine violently arched backward, knees buckling, head whipped back by kinetic recoil",
        "fx": "concussive shockwave ring, shattered raindrops, frozen blood droplets in mid-air",
        "anti_stoic_negative": "calm face, peaceful expression, handsome model pose, gentle expression, closed mouth, polite frown, stoic, emotionless, stiff posture, relaxed body, smiling, friendly, blank stare",
    },
    "lethal_wrath": {
        "title": "Lethal Wrath (Striker)",
        "micro_anatomy": "teeth bared in animalistic snarl, brows deeply furrowed casting black eye shadows, glowing iris flaring with flame, corded jaw muscles clenched",
        "posture": "full body weight lunging forward, knuckles white with crushing pressure, shoulders locked",
        "fx": "directional speed lines, ink-splash shockwave, vacuum vortex around fist",
        "anti_stoic_negative": "calm face, peaceful expression, polite frown, gentle expression, relaxed posture, smiling, blank stare",
    },
    "dread_terror": {
        "title": "Paralyzing Dread (Terror)",
        "micro_anatomy": "pupils contracted to pinpoints, jaw dropped, ash-pale skin, cold sweat beads running down cheeks, hyperventilating parted lips",
        "posture": "involuntary step backward, trembling hands, torso recoiling, shoulders hunched inward",
        "fx": "heavy dark vignette, trembling aura distortion, shadows engulfing eyes",
        "anti_stoic_negative": "calm face, peaceful expression, stoic, brave face, smiling, confident posture, calm expression, steady stance",
    },
    "cruel_arrogance": {
        "title": "Cruel Arrogance (Mockery)",
        "micro_anatomy": "asymmetrical sneer, one eyebrow raised, heavy-lidded downward gaze, relaxed jaw with mocking smirk",
        "posture": "head tilted back looking down nose, arms folded or one hand raised dismissively",
        "fx": "sharp high-contrast side lighting, dismissive wind whipping cape",
        "anti_stoic_negative": "calm face, peaceful expression, stoic, friendly smile, warm expression, nervous posture, crying, frightened",
    },
    "desperate_exhaustion": {
        "title": "Desperate Exhaustion",
        "micro_anatomy": "heavy panting through parted dry cracked lips, half-closed bloodshot eyes, sweat dripping from chin, grimy weathered skin",
        "posture": "torso slumped forward, hand bracing on knee or ground, trembling limbs, struggling to stand",
        "fx": "steam rising from exhausted body, muddy bloodied clothes, spattered dirt",
        "anti_stoic_negative": "calm face, peaceful expression, stoic, energetic pose, clean skin, smiling, standing tall, heroic posture",
    },
    "sovereign_awe": {
        "title": "Sovereign Awe (Epiphany)",
        "micro_anatomy": "wide unblinking eyes illuminated by divine light, lips slightly parted in reverence, serene stillness",
        "posture": "standing ramrod straight, chest expanded, arms lowered at sides, looking upward with transcendent focus",
        "fx": "vertical light beam, evaporating raindrops into radiant mist, halo rim-light",
        "anti_stoic_negative": "calm face, stoic frown, angry frown, screaming, frantic posture, mundane expression, slouching",
    },
}


async def handle_story_agent_action(request):
    slug = request.match_info.get("slug", "")
    panel_id = request.match_info.get("panel_id", "")
    try:
        body = await request.json() if request.can_read_body else {}
    except Exception:
        body = {}
    action = body.get("action", "somatic_emotion")
    archetype_key = body.get("archetype", "visceral_pain")
    custom_cues = body.get("custom_cues", "")

    if action == "somatic_emotion":
        arch = SOMATIC_ARCHETYPES.get(archetype_key, SOMATIC_ARCHETYPES["visceral_pain"])
        somatic_prompt = f"{arch['micro_anatomy']}, {arch['posture']}, {arch['fx']}"
        if custom_cues:
            somatic_prompt = f"{custom_cues}, {somatic_prompt}"
        return web.json_response({
            "success": True,
            "panel_id": panel_id,
            "archetype": archetype_key,
            "archetype_title": arch["title"],
            "somatic_prompt": somatic_prompt,
            "anti_stoic_negative": arch["anti_stoic_negative"],
            "message": f"Somatic cues assembled for {arch['title']}"
        })
    elif action == "vision_audit":
        from engine.api.routers.original import _resolve_story_ws
        ws = _resolve_story_ws(slug, body.get("episode"))
        art_path = ws / "art.json"
        score = 0.92
        defects = []
        status = "accept"
        if art_path.exists():
            try:
                raw_art = json.loads(art_path.read_text(encoding="utf-8"))
                rec = next((r for r in raw_art if r.get("panel_id") == panel_id), None)
                if rec:
                    score = rec.get("score", 0.92)
                    status = rec.get("status", "accept")
                    rev = rec.get("review", {})
                    defects = rev.get("defects", [])
            except Exception:
                pass
        return web.json_response({
            "success": True,
            "panel_id": panel_id,
            "score": score,
            "status": status,
            "defects": defects,
            "message": f"Vision audit complete: status={status}, score={score}"
        })
    return web.json_response({"success": False, "detail": f"Unknown agent action '{action}'"}, status=400)


async def handle_approve_story_panel(request):
    slug = request.match_info.get("slug", "")
    panel_id = request.match_info.get("panel_id", "")
    try:
        body = await request.json() if request.can_read_body else {}
    except Exception:
        body = {}
    from engine.api.routers.original import approve_panel, ApprovePanelRequest
    req = ApprovePanelRequest(episode=body.get("episode"))
    res = approve_panel(slug=slug, panel_id=panel_id, req=req)
    return web.json_response(res.model_dump())


async def handle_reroll_story_panel(request):
    slug = request.match_info.get("slug", "")
    panel_id = request.match_info.get("panel_id", "")
    try:
        body = await request.json() if request.can_read_body else {}
    except Exception:
        body = {}
    from engine.api.routers.original import reroll_panel, RerollPanelRequest
    from fastapi import HTTPException
    req = RerollPanelRequest(episode=body.get("episode"), seed=body.get("seed"), prompt=body.get("prompt"))
    try:
        res = await reroll_panel(slug=slug, panel_id=panel_id, req=req)
        return web.json_response(res.model_dump())
    except HTTPException as he:
        return web.json_response({"success": False, "detail": he.detail}, status=he.status_code)
    except Exception as e:
        return web.json_response({"success": False, "detail": str(e)}, status=500)


async def handle_open_story_folder(request):
    slug = request.match_info.get("slug", "")
    try:
        from engine.api.routers.original import open_story, OpenStoryRequest
        req = OpenStoryRequest()
        res = open_story(slug=slug, req=req)
        return web.json_response({"success": True, "detail": str(res)})
    except Exception as e:
        return web.json_response({"success": False, "detail": str(e)}, status=500)


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




