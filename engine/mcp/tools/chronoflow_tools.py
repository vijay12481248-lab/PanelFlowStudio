"""ChronoFlow Pro Studio MiniMax H3 video chaining and AI cinematography MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_chronoflow_status",
    description="Check GPU VRAM availability, installed MiniMax H3 DiT & Turbo LoRAs, and ComfyUI connection.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_status() -> dict[str, Any]:
    return await bridge.get("/api/chronoflow/status")


@registry.tool(
    name="panelflow_chronoflow_list_characters",
    description="List all actor profiles and turnaround reference sheets stored in the Character Vault for cross-shot visual consistency.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_list_characters() -> dict[str, Any]:
    return await bridge.get("/api/chronoflow/characters")


@registry.tool(
    name="panelflow_chronoflow_save_character",
    description="Save or update an actor profile in the Character Vault with reference turnaround image, name, role, and visual description.",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Character name (e.g. 'Commander Maya Voss')"},
            "role": {"type": "string", "description": "Story role (e.g. 'Protagonist', 'Villain')"},
            "image": {"type": "string", "description": "Filename of character reference in ComfyUI input/ folder"},
            "description": {"type": "string", "description": "Visual traits, clothing, facial details"},
            "id": {"type": "string", "description": "Optional existing character ID to update"},
        },
        "required": ["name", "image"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_save_character(
    name: str,
    image: str,
    role: str = "Protagonist",
    description: str = "",
    id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "image": image,
        "role": role,
        "description": description,
    }
    if id:
        payload["id"] = id
    return await bridge.post("/api/chronoflow/characters", payload)


@registry.tool(
    name="panelflow_chronoflow_generate_model_sheet",
    description="Generate a canonical 4-view character turnaround model sheet using FLUX.2 Klein (flux2_klein_4b), slice views, and extract face embeddings.",
    input_schema={
        "type": "object",
        "properties": {
            "character_id": {"type": "string", "description": "Character ID in Character Vault (e.g. 'char_c16d64')"},
            "seed": {"type": "integer", "description": "Optional random seed for generation"},
        },
        "required": ["character_id"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_generate_model_sheet(character_id: str, seed: int | None = None) -> dict[str, Any]:
    url = f"/api/chronoflow/characters/{character_id}/model_sheet"
    if seed is not None:
        url += f"?seed={seed}"
    return await bridge.post(url, {})


@registry.tool(
    name="panelflow_chronoflow_verify_face",
    description="Verify face identity match between a generated shot image and a character reference image using local 512-dim ArcFace embeddings.",
    input_schema={
        "type": "object",
        "properties": {
            "query_image": {"type": "string", "description": "Filename of query/generated image"},
            "reference_image": {"type": "string", "description": "Filename of canonical character reference image"},
            "threshold": {"type": "number", "description": "Cosine similarity match threshold (default 0.72)"},
        },
        "required": ["query_image", "reference_image"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_verify_face(
    query_image: str,
    reference_image: str,
    threshold: float = 0.72,
) -> dict[str, Any]:
    return await bridge.post(
        "/api/chronoflow/characters/verify_face",
        {"query_image": query_image, "reference_image": reference_image, "threshold": threshold},
    )


@registry.tool(
    name="panelflow_chronoflow_pin_references",
    description="Automatically select and bind up to 4 character turnaround views for a shot to prevent character face drift in flux2_klein_4b_ref.",
    input_schema={
        "type": "object",
        "properties": {
            "scene": {"type": "object", "description": "Storyboard scene or shot object containing prompt, title, or character_ids"},
            "max_references": {"type": "integer", "description": "Maximum references to bind (default 4)"},
        },
        "required": ["scene"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_pin_references(scene: dict[str, Any], max_references: int = 4) -> dict[str, Any]:
    return await bridge.post(
        "/api/chronoflow/characters/pin_references",
        {"scene": scene, "max_references": max_references},
    )



@registry.tool(
    name="panelflow_chronoflow_ai_director_plan",
    description=(
        "Generate a multi-scene storyboard breakdown from a high-level story idea, automatically compiling native 6-heading MiniMax H3 prompts. "
        "Directs agents to establish clear subject_definitions and enforce shallow depth-of-field (background bokeh) to prevent distant face distortion."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "idea": {"type": "string", "description": "High-level story idea or scene synopsis"},
            "duration": {"type": "integer", "description": "Target video duration in seconds (e.g. 15, 30, 60)"},
        },
        "required": ["idea"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_ai_director_plan(
    idea: str,
    duration: int = 15,
) -> dict[str, Any]:
    return await bridge.post("/api/chronoflow/ai_director/plan", {"idea": idea, "duration": duration})


@registry.tool(
    name="panelflow_chronoflow_generate_video",
    description=(
        "Dispatch video generation using MiniMax Fast H3. Workflows: 'sliding_window' (continuation chaining), "
        "'flf2v' (first & last keyframe bridging), 'reference' (character turnaround sheet locking), or 'storyboard' (multi-scene production).\n\n"
        "Agent Prompting Guidelines:\n"
        "1. Avoid Facial Drift: In wide or crowded shots, always include 'shallow depth of field, sharp foreground protagonist, soft background bokeh' to blur distant extras.\n"
        "2. Face Refinement: Set face_refine=True to automatically activate per-frame H3FaceTrackCrop & H3FaceStitch to restore distorted faces.\n"
        "3. High Resolution: Set upscale_mode='2k_latent' to run high-definition upscale on final frames."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Video prompt or compiled 6-heading description"},
            "workflow_mode": {
                "type": "string",
                "enum": ["sliding_window", "flf2v", "reference", "storyboard"],
                "description": "Conditioning mode",
            },
            "total_duration": {"type": "number", "description": "Target duration in seconds (e.g. 15.6, 31.2)"},
            "first_frame": {"type": "string", "description": "Starting image filename in input/ folder"},
            "last_frame": {"type": "string", "description": "Ending image filename in input/ folder for FLF2V mode"},
            "ref_images": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of character sheet filenames in input/ folder for reference locking",
            },
            "scenes": {
                "type": "array",
                "description": "List of scene beat objects for storyboard mode",
            },
            "face_refine": {
                "type": "boolean",
                "description": "Enable per-frame H3 face tracking and crop refinement to eliminate face distortion",
            },
            "upscale_mode": {
                "type": "string",
                "enum": ["none", "2k_latent"],
                "description": "Secondary upscale mode (e.g. '2k_latent' for crisp 2K video output)",
            },
            "width": {"type": "integer", "description": "Frame width (default 1344). Use the aspect of your first frames: 768 x 768 for square pictures, so nothing is cropped."},
            "height": {"type": "integer", "description": "Frame height (default 768)"},
            "steps": {"type": "integer", "description": "Sampling steps (default 4 with the 4step turbo LoRA)"},
            "lora_choice": {"type": "string", "enum": ["4step", "8step"], "description": "Turbo LoRA (default 4step: fastest)"},
        },
        "required": ["prompt"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_generate_video(
    prompt: str,
    workflow_mode: str = "sliding_window",
    total_duration: float = 15.6,
    first_frame: str | None = None,
    last_frame: str | None = None,
    ref_images: list[str] | None = None,
    scenes: list[dict[str, Any]] | None = None,
    face_refine: bool = False,
    upscale_mode: str = "none",
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
    lora_choice: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "workflow_mode": workflow_mode,
        "total_duration": total_duration,
        "first_frame": first_frame,
        "last_frame": last_frame,
        "ref_images": ref_images or [],
        "scenes": scenes or [],
        "face_refine": face_refine,
        "upscale_mode": upscale_mode,
    }
    payload.update({k: v for k, v in (("width", width), ("height", height), ("steps", steps), ("lora_choice", lora_choice)) if v is not None})
    return await bridge.post("/api/chronoflow/generate", payload)


@registry.tool(
    name="panelflow_chronoflow_get_job",
    description="Progress and results of a ChronoFlow video job started with panelflow_chronoflow_generate_video: status, current/total shot, "
                "step progress, the finished shot files (chunks) and the stitched master video. Poll this; shots take minutes each.",
    input_schema={
        "type": "object",
        "properties": {"job_id": {"type": "string", "description": "The job_id returned by panelflow_chronoflow_generate_video"}},
        "required": ["job_id"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_get_job(job_id: str) -> dict[str, Any]:
    return await bridge.get(f"/api/chronoflow/job/{job_id}")


@registry.tool(
    name="panelflow_chronoflow_cancel_job",
    description=(
        "Cancel a running ChronoFlow video or image job (the job_id returned by panelflow_chronoflow_generate_video). "
        "ChronoFlow jobs run in their own supervisor, so panelflow_cancel_job does not reach them."
    ),
    input_schema={
        "type": "object",
        "properties": {"job_id": {"type": "string", "description": "The ChronoFlow job ID to cancel"}},
        "required": ["job_id"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_cancel_job(job_id: str) -> dict[str, Any]:
    return await bridge.post("/api/chronoflow/cancel", {"job_id": job_id})


@registry.tool(
    name="panelflow_chronoflow_regenerate_shot",
    description="Trigger micro-regeneration of a specific shot using director critique notes, custom anchor image, or adjusted duration.",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "The active job ID"},
            "chunk_index": {"type": "integer", "description": "1-based shot index to regenerate"},
            "notes": {"type": "string", "description": "Director critique feedback (e.g. 'faster camera pan, sharper foreground')"},
            "anchor_image": {"type": "string", "description": "Custom starting keyframe filename"},
            "prompt": {"type": "string", "description": "Optional customized prompt for this shot"},
            "duration": {"type": "number", "description": "Shot duration in seconds (default: 5.17)"},
        },
        "required": ["job_id", "chunk_index"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_regenerate_shot(
    job_id: str,
    chunk_index: int,
    notes: str = "",
    anchor_image: str | None = None,
    prompt: str | None = None,
    duration: float = 5.17,
) -> dict[str, Any]:
    payload = {
        "job_id": job_id,
        "chunk_index": chunk_index,
        "notes": notes,
        "anchor_image": anchor_image,
        "prompt": prompt,
        "duration": duration,
    }
    return await bridge.post("/api/chronoflow/regenerate_chunk", payload)


@registry.tool(
    name="panelflow_chronoflow_generate_image",
    description=(
        "Generate a high-resolution reference image, character turnaround, or keyframe with PanelFlow's single art workflow "
        "(FLUX.2 klein 4B, flux2_klein_4b) - the same engine the Original Stories art step uses. Width and height must be multiples of 16, 256-2048. "
        "Character lock: pass character_ids (Character Vault ids) and/or ref_images (sheet filenames, paths, or base64 data URLs) to bind "
        "approved reference sheets to the generation so faces follow the locked identity. Never generate an identifiable character's face without it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Detailed image generation prompt"},
            "negative_prompt": {"type": "string", "description": "What to avoid (optional)"},
            "width": {"type": "integer", "description": "Image width, multiple of 16 (default 1024)"},
            "height": {"type": "integer", "description": "Image height, multiple of 16 (default 1024)"},
            "refine": {"type": "boolean", "description": "Currently unavailable (the refine loop was built on the retired Qwen model); leave false"},
            "ref_images": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Character-lock reference images (max 4): vault sheet filenames, file paths, or base64 data URLs (optional)",
            },
            "character_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Character-lock by vault id (max 4): resolves each Character Vault member to its locked reference sheet (optional)",
            },
            "workflow_id": {
                "type": "string",
                "enum": ["flux2_klein_4b", "minimax_h3_image_edit"],
                "description": "Image model: flux2_klein_4b (default; ~7 s, Apache-2.0, supports character lock up to 4 pictures, no refine) or "
                               "minimax_h3_image_edit (MiniMax H3-Image; ~50 s, painted/illustrated look, no refine; its licence excludes the US, EU, UK and South Korea)",
            },
        },
        "required": ["prompt"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_generate_image(
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted, bad anatomy",
    width: int | None = None,
    height: int | None = None,
    refine: bool = False,
    ref_images: list[str] | None = None,
    character_ids: list[str] | None = None,
    workflow_id: str = "flux2_klein_4b",
) -> dict[str, Any]:
    payload = {
        "workflow_id": workflow_id,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "refine": refine,
        "ref_images": ref_images or [],
        "character_ids": character_ids or [],
    }
    return await bridge.post("/api/chronoflow/generate_image", payload, timeout_s=3600.0)


@registry.tool(
    name="panelflow_chronoflow_inpaint_image",
    description="Inpaint a masked region on an image using FLUX.1 Schnell for costume fixes, prop modification, or face consistency.",
    input_schema={
        "type": "object",
        "properties": {
            "image_filename": {"type": "string", "description": "Source image filename in ComfyUI input/ folder"},
            "mask_data": {"type": "string", "description": "Base64 encoded black & white mask image"},
            "prompt": {"type": "string", "description": "Prompt describing the desired inpainted region"},
            "denoise": {"type": "number", "description": "Denoise strength (default: 0.85)"},
        },
        "required": ["image_filename", "mask_data", "prompt"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_inpaint_image(
    image_filename: str,
    mask_data: str,
    prompt: str,
    denoise: float = 0.85,
) -> dict[str, Any]:
    payload = {
        "image_filename": image_filename,
        "mask_data": mask_data,
        "prompt": prompt,
        "denoise": denoise,
    }
    return await bridge.post("/api/chronoflow/inpaint_image", payload)


@registry.tool(
    name="panelflow_chronoflow_export_timeline",
    description="Render a multi-track NLE timeline sequence into a final mastered video cut with in/out trimming, speed ramps, and atempo audio.",
    input_schema={
        "type": "object",
        "properties": {
            "clips": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of clip objects with filename, in_point, out_point, speed, volume",
            },
        },
        "required": ["clips"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_export_timeline(clips: list[dict[str, Any]]) -> dict[str, Any]:
    return await bridge.post("/api/chronoflow/timeline/export", {"clips": clips})


@registry.tool(
    name="panelflow_chronoflow_list_screenplays",
    description="List all available master screenplays and storyboard blueprints in the ChronoFlow vault (e.g. Avalon Prime 24-shot, Agent Whiskers).",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_list_screenplays() -> dict[str, Any]:
    return await bridge.get("/api/chronoflow/screenplays")


@registry.tool(
    name="panelflow_chronoflow_get_screenplay",
    description="Retrieve full storyboard screenplay breakdown by filename, including all scene beats, 6-heading prompts, protagonist, and anchor frames.",
    input_schema={
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Screenplay JSON filename (e.g. 'screenplay_avalon_prime_2min.json')"},
        },
        "required": ["filename"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_get_screenplay(filename: str) -> dict[str, Any]:
    return await bridge.get(f"/api/chronoflow/screenplay/{filename}")


@registry.tool(
    name="panelflow_chronoflow_save_screenplay",
    description="Save or update a multi-scene storyboard screenplay in the ChronoFlow vault.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Screenplay title"},
            "duration": {"type": "number", "description": "Total duration in seconds"},
            "scenes": {"type": "array", "description": "List of scene beat objects"},
            "protagonist": {"type": "object", "description": "Protagonist metadata"},
            "anchor_images": {"type": "object", "description": "Keyframe anchors"},
            "filename": {"type": "string", "description": "Optional specific filename to save as"},
        },
        "required": ["title", "scenes"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_save_screenplay(
    title: str,
    scenes: list[dict[str, Any]],
    duration: float = 15.6,
    protagonist: dict[str, Any] | None = None,
    anchor_images: dict[str, Any] | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "scenes": scenes,
        "duration": duration,
        "protagonist": protagonist or {},
        "anchor_images": anchor_images or {},
    }
    if filename:
        payload["filename"] = filename
    return await bridge.post("/api/chronoflow/screenplay/save", payload)



# ---------------------------------------------------------------------------
# Timeline: colour grading and Fusion effects an agent can apply.
# The studio mirrors its timeline to the engine; these tools change that copy and the open studio shows the change within ~2 s
# (undoable with Ctrl+Z there). The export renders exactly the same grade and effects. Clips are 1-based in timeline order.
# ---------------------------------------------------------------------------
_CLIP = {"description": "Which clip: 1-based position in the timeline, a clip id, or 'all' (default 'all')",
         "anyOf": [{"type": "integer"}, {"type": "string"}]}


@registry.tool(
    name="panelflow_chronoflow_color_guide",
    description=(
        "READ FIRST before grading. Returns every colour control (range, neutral value, what it does), how the lift/gamma/gain/offset "
        "wheels take a colour + amount, the named looks, and the Fusion effects with their parameters."
    ),
    input_schema={"type": "object", "properties": {}},
    domain="chronoflow",
)
async def panelflow_chronoflow_color_guide() -> dict[str, Any]:
    return await bridge.get("/api/chronoflow/timeline/describe")


@registry.tool(
    name="panelflow_chronoflow_timeline_get",
    description=(
        "The studio timeline of a ChronoFlow job: each clip's position, label, start, duration, current grade (only the controls that "
        "differ from neutral, per node) and Fusion effects. Use it to see what is there before and after changing it. "
        "version 0 means the job was never opened in the Video Studio (open it once so its timeline exists)."
    ),
    input_schema={"type": "object", "properties": {"job_id": {"type": "string", "description": "ChronoFlow job id"}}, "required": ["job_id"]},
    domain="chronoflow",
)
async def panelflow_chronoflow_timeline_get(job_id: str) -> dict[str, Any]:
    rec = await bridge.get(f"/api/chronoflow/timeline/{job_id}")
    return {"version": rec.get("version", 0), "source": rec.get("source"), "clips": rec.get("clips", [])}


async def _op(job_id: str, op: str, args: dict[str, Any]) -> dict[str, Any]:
    return await bridge.post(f"/api/chronoflow/timeline/{job_id}/op", {"op": op, "args": {k: v for k, v in args.items() if v is not None}})


@registry.tool(
    name="panelflow_chronoflow_color_set",
    description=(
        "Grade one clip or all clips. Give `controls`, e.g. {\"saturation\": 0.8, \"contrast\": 1.15, \"temp\": 12, "
        "\"gain\": {\"color\": \"orange\", \"amount\": 0.3}, \"lift\": {\"color\": \"teal\", \"amount\": 0.4, \"master\": -0.02}}, "
        "and/or a named `look` (Teal & Orange, Warm film, Cold night, Bleach bypass, Faded matte, Vivid pop, Noir). "
        "`node` picks the serial node (1 = first; number of nodes + 1 adds a new node on top - use that for a look over a correction). "
        "Out-of-range values are refused with the allowed range. See panelflow_chronoflow_color_guide."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "string"},
            "clip": _CLIP,
            "controls": {"type": "object", "description": "Colour controls to set (see the guide)"},
            "look": {"type": "string", "description": "A named look to apply to the node"},
            "node": {"type": "integer", "description": "1-based node (default 1)"},
        },
        "required": ["job_id"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_color_set(job_id: str, clip: int | str | None = None, controls: dict[str, Any] | None = None,
                                         look: str | None = None, node: int = 1) -> dict[str, Any]:
    return await _op(job_id, "color_set", {"clip": clip, "controls": controls or {}, "look": look, "node": node})


@registry.tool(
    name="panelflow_chronoflow_color_copy",
    description="Copy one clip's whole grade (all nodes) to another clip or to every clip - the quick way to make a scene consistent.",
    input_schema={
        "type": "object",
        "properties": {"job_id": {"type": "string"}, "from_clip": _CLIP, "to_clip": _CLIP},
        "required": ["job_id", "from_clip"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_color_copy(job_id: str, from_clip: int | str, to_clip: int | str | None = None) -> dict[str, Any]:
    return await _op(job_id, "color_copy", {"from_clip": from_clip, "to_clip": to_clip})


@registry.tool(
    name="panelflow_chronoflow_color_reset",
    description="Remove the grade from one clip or all clips (back to the original picture).",
    input_schema={"type": "object", "properties": {"job_id": {"type": "string"}, "clip": _CLIP}, "required": ["job_id"]},
    domain="chronoflow",
)
async def panelflow_chronoflow_color_reset(job_id: str, clip: int | str | None = None) -> dict[str, Any]:
    return await _op(job_id, "color_reset", {"clip": clip})


@registry.tool(
    name="panelflow_chronoflow_fusion_add",
    description=(
        "Add a Fusion effect to one clip or all clips, applied before the grade: vignette, film_grain, glow, blur, text_plus "
        "(titles, e.g. {\"text\": \"Chapter 1\", \"posY\": 0.85, \"fontSize\": 56}), color_corrector, transform, camera_shake, chroma_keyer. "
        "Params you leave out use the effect's defaults (see the guide)."
    ),
    input_schema={
        "type": "object",
        "properties": {"job_id": {"type": "string"}, "effect": {"type": "string"}, "clip": _CLIP, "params": {"type": "object"}},
        "required": ["job_id", "effect"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_fusion_add(job_id: str, effect: str, clip: int | str | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _op(job_id, "fusion_add", {"clip": clip, "effect": effect, "params": params or {}})


@registry.tool(
    name="panelflow_chronoflow_fusion_clear",
    description="Remove every Fusion effect from one clip or all clips.",
    input_schema={"type": "object", "properties": {"job_id": {"type": "string"}, "clip": _CLIP}, "required": ["job_id"]},
    domain="chronoflow",
)
async def panelflow_chronoflow_fusion_clear(job_id: str, clip: int | str | None = None) -> dict[str, Any]:
    return await _op(job_id, "fusion_clear", {"clip": clip})


@registry.tool(
    name="panelflow_chronoflow_assemble_storyboard",
    description=(
        "Concatenate rendered storyboard shots into a unified master timeline video. "
        "Normalizes mixed-aspect-ratio and mixed-resolution clips with letterbox/pillarbox padding to a uniform canvas, "
        "and auto-creates an Audio Studio Sound Plan populated with dialogue/foley cues for immediate scoring."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "scenes": {"type": "array", "description": "List of storyboard scenes/shots to assemble"},
            "title": {"type": "string", "description": "Sequence title (e.g. 'Opening Scene Master')"},
            "target_width": {"type": "integer", "description": "Target video width (default 1920)"},
            "target_height": {"type": "integer", "description": "Target video height (default 1080)"},
            "fps": {"type": "number", "description": "Target frame rate (default 24.0)"},
            "approved_only": {"type": "boolean", "description": "Assemble only cards marked approved=True"},
            "create_sound_plan": {"type": "boolean", "description": "Auto-create Audio Studio Sound Plan (default true)"},
        },
        "required": ["scenes"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_assemble_storyboard(
    scenes: list[dict[str, Any]],
    title: str = "Assembled Sequence",
    target_width: int = 1920,
    target_height: int = 1080,
    fps: float = 24.0,
    approved_only: bool = False,
    create_sound_plan: bool = True,
) -> dict[str, Any]:
    payload = {
        "scenes": scenes,
        "title": title,
        "target_width": target_width,
        "target_height": target_height,
        "fps": fps,
        "approved_only": approved_only,
        "create_sound_plan": create_sound_plan,
    }
    return await bridge.post("/api/chronoflow/storyboard/assemble", payload)

