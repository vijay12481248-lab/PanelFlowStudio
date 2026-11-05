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
    description="Generate a multi-scene storyboard breakdown from a high-level story idea, automatically compiling native 6-heading MiniMax H3 prompts.",
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
    description="Dispatch video generation using MiniMax Fast H3. Workflows: 'sliding_window' (continuation chaining), 'flf2v' (first & last keyframe bridging), 'reference' (character turnaround sheet locking), or 'storyboard' (multi-scene production).",
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
) -> dict[str, Any]:
    payload = {
        "prompt": prompt,
        "workflow_mode": workflow_mode,
        "total_duration": total_duration,
        "first_frame": first_frame,
        "last_frame": last_frame,
        "ref_images": ref_images or [],
        "scenes": scenes or [],
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
    description="Generate high-resolution reference image, character turnaround, or keyframe using FLUX.1 Schnell fp8 or Qwen-Image-2.1 Turbo.",
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Detailed image generation prompt"},
            "model": {"type": "string", "enum": ["flux", "qwen"], "description": "Model to use (default: flux)"},
            "width": {"type": "integer", "description": "Image width (e.g. 1344 or 1024)"},
            "height": {"type": "integer", "description": "Image height (e.g. 768 or 1024)"},
            "steps": {"type": "integer", "description": "Sampling steps (default: 4 for flux, 8 for qwen)"},
        },
        "required": ["prompt"],
    },
    domain="chronoflow",
)
async def panelflow_chronoflow_generate_image(
    prompt: str,
    model: str = "flux",
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
) -> dict[str, Any]:
    payload = {
        "prompt": prompt,
        "model": model,
        "width": width,
        "height": height,
        "steps": steps,
    }
    return await bridge.post("/api/chronoflow/generate_image", payload)


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
