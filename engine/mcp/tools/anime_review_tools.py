"""Anime Episode Review video production pipeline MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_anime_ingest_episode",
    description="Ingest an anime video episode into the review pipeline through the rights gate (UNKNOWN rights refused).",
    input_schema={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Local video file path or URL"},
            "title": {"type": "string", "description": "Anime series title and episode (e.g. 'Frieren Ep 1')"},
            "rights_status": {
                "type": "string",
                "enum": ["OWNED", "LICENSED", "PUBLIC_DOMAIN", "UNKNOWN"],
                "description": "Declared rights status",
            },
        },
        "required": ["source", "title", "rights_status"],
    },
    domain="anime_review",
)
async def panelflow_anime_ingest_episode(
    source: str,
    title: str,
    rights_status: str,
) -> dict[str, Any]:
    payload = {
        "source": source,
        "title": title,
        "rights": {"status": rights_status},
    }
    return await bridge.post("/api/anime/review/ingest", payload)


@registry.tool(
    name="panelflow_anime_analyze_episode",
    description="Run scene detection and audio speech recognition (ASR) to extract timestamps and transcript.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Episode workspace slug (e.g. 'frieren-ep-1')"},
            "use_asr": {"type": "boolean", "description": "Run audio speech recognition (default: true)"},
        },
        "required": ["slug"],
    },
    domain="anime_review",
)
async def panelflow_anime_analyze_episode(slug: str, use_asr: bool = True) -> dict[str, Any]:
    return await bridge.post(f"/api/anime/review/{slug}/analyze?use_asr={str(use_asr).lower()}")


@registry.tool(
    name="panelflow_anime_write_review_script",
    description="Generate conversational anime review script grounded in visual plot beats and fact-checked against episode transcript.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Episode workspace slug"},
            "tone": {"type": "string", "description": "Review tone (default: 'warm, witty, honest fan reviewer')"},
            "language": {"type": "string", "description": "Output language (default: 'English')"},
        },
        "required": ["slug"],
    },
    domain="anime_review",
)
async def panelflow_anime_write_review_script(
    slug: str,
    tone: str = "warm, witty, honest fan reviewer",
    language: str = "English",
) -> dict[str, Any]:
    payload = {"tone": tone, "language": language}
    return await bridge.post(f"/api/anime/review/{slug}/script", payload)


@registry.tool(
    name="panelflow_anime_render_review",
    description="Render final 1080p anime review video with synchronized commentary, capped clip highlights, and YouTube packaging.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Episode workspace slug"},
            "burn_captions": {"type": "boolean", "description": "Burn in stylized subtitles (default: true)"},
        },
        "required": ["slug"],
    },
    domain="anime_review",
)
async def panelflow_anime_render_review(slug: str, burn_captions: bool = True) -> dict[str, Any]:
    return await bridge.post(f"/api/anime/review/{slug}/render?burn_captions={str(burn_captions).lower()}")
