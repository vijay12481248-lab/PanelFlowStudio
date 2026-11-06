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
) -> dict[str, Any]:
    payload = {
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
    return await bridge.post("/api/chronoflow/generate", payload)


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
        "(Qwen Image 2.1 Turbo, qwen_image_21) - the same engine the Original Stories art step uses. Width and height must be multiples of 16, 256-2048."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Detailed image generation prompt"},
            "negative_prompt": {"type": "string", "description": "What to avoid (optional)"},
            "width": {"type": "integer", "description": "Image width, multiple of 16 (default 1024)"},
            "height": {"type": "integer", "description": "Image height, multiple of 16 (default 1024)"},
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
) -> dict[str, Any]:
    payload = {"prompt": prompt, "negative_prompt": negative_prompt, "width": width, "height": height}
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

