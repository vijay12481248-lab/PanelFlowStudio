"""Original Story Studio (premise, character art, comic pages, video) MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge

LONG_JOB_S = 4 * 3600.0  # story, art and video calls block for many minutes; the bridge default (10 min) would drop the result


@registry.tool(
    name="panelflow_original_list_genres",
    description="List supported original story genres (fantasy, sci-fi, horror, comedy, shonen, romance) with tones and default scene counts.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="original",
)
async def panelflow_original_list_genres() -> dict[str, Any]:
    return await bridge.get("/api/original/genres")


@registry.tool(
    name="panelflow_original_create_story",
    description="Generate premise, character bible, story outline, and panel script with local LLM (qwen3.5:9b).",
    input_schema={
        "type": "object",
        "properties": {
            "genre": {"type": "string", "description": "Story genre (e.g. 'fantasy', 'cyberpunk', 'comedy')"},
            "idea": {"type": "string", "description": "High-level premise or prompt for the story"},
            "scenes": {"type": "integer", "description": "Number of scenes (default: 5, range: 3-14)"},
        },
        "required": ["genre"],
    },
    domain="original",
)
async def panelflow_original_create_story(
    genre: str,
    idea: str = "",
    scenes: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"genre": genre, "idea": idea}
    if scenes:
        payload["scenes"] = scenes
    return await bridge.post("/api/original/story", payload, timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_direct_shots",
    description=(
        "Shot director: splits each panel's narration into beats (<= ~24 words) and writes a structured shot spec per beat "
        "(who is on screen, pose, expression, place, key visuals) so every picture follows the spoken words. "
        "Run this after create_story and BEFORE generate_art; without it art is drawn from the plain panel 'action' text, "
        "with no per-beat review."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_direct_shots(slug: str) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/beats", timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_generate_art",
    description="Generate character turnaround sheets and comic panel art using ComfyUI (Animagine XL 4.0 / FLUX.1). Run panelflow_original_direct_shots first so pictures follow the narration.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug returned by panelflow_original_create_story"},
            "limit": {"type": "integer", "description": "Optional limit on panels to generate"},
            "check": {"type": "boolean", "description": "Run consistency verification check with local vision LLM (default: true)"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_generate_art(
    slug: str,
    limit: int | None = None,
    check: bool = True,
) -> dict[str, Any]:
    query_parts = []
    if limit is not None:
        query_parts.append(f"limit={limit}")
    query_parts.append(f"check={str(check).lower()}")
    query = f"?{'&'.join(query_parts)}" if query_parts else ""
    return await bridge.post(f"/api/original/story/{slug}/art{query}", timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_render_video",
    description="Render a fully voiced, animated 1080p episode video (Ken Burns motion, speech narration, music, captions) and generate YouTube packaging.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug"},
            "burn_captions": {"type": "boolean", "description": "Burn in stylized subtitle captions (default: true)"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_render_video(
    slug: str,
    burn_captions: bool = True,
) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/video?burn_captions={str(burn_captions).lower()}", timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_compose_pages",
    description="Letter the panels (balloons, narrator boxes, SFX) and compose print-ready comic book pages and PDF.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_compose_pages(slug: str) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/pages")
