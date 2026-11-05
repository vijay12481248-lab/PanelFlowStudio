"""Story analysis, script adaptation, speech synthesis, and music director MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_analyze_story",
    description="Run local LLM (qwen3.5:9b) to extract narrative premise, emotional arcs, character dynamics, and scene boundaries from panels.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "provider_id": {"type": "string", "description": "Optional LLM provider ID (default: ollama)"},
        },
        "required": ["project_id"],
    },
    domain="story",
)
async def panelflow_analyze_story(project_id: str, provider_id: str | None = None) -> dict[str, Any]:
    payload = {"provider_id": provider_id} if provider_id else {}
    return await bridge.post(f"/api/projects/{project_id}/story/analyze", payload)


@registry.tool(
    name="panelflow_get_story_narrative",
    description="Retrieve the Narrative IR document containing premise, themes, character arcs, and scene breakdowns.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="story",
)
async def panelflow_get_story_narrative(project_id: str) -> dict[str, Any]:
    return await bridge.get(f"/api/projects/{project_id}/narrative")


@registry.tool(
    name="panelflow_generate_script",
    description="Generate a video narration script with spoken dialogues, character voice assignments, and pacing cues.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "tone": {"type": "string", "description": "Narrative tone (e.g. 'cinematic', 'comedic', 'dramatic')"},
            "target_duration_seconds": {"type": "number", "description": "Target video duration in seconds"},
        },
        "required": ["project_id"],
    },
    domain="story",
)
async def panelflow_generate_script(
    project_id: str,
    tone: str = "cinematic",
    target_duration_seconds: float = 60.0,
) -> dict[str, Any]:
    payload = {
        "tone": tone,
        "target_duration_seconds": target_duration_seconds,
    }
    return await bridge.post(f"/api/projects/{project_id}/scripts/generate", payload)


@registry.tool(
    name="panelflow_list_characters",
    description="List all detected characters in a project with canonical names, roles, visual traits, and reference panels.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="story",
)
async def panelflow_list_characters(project_id: str) -> list[dict[str, Any]]:
    return await bridge.get(f"/api/projects/{project_id}/characters")


@registry.tool(
    name="panelflow_generate_audio_job",
    description="Enqueue speech synthesis (TTS) to generate voiceover narration and character audio clips.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "voice_casting": {
                "type": "object",
                "description": "Mapping from character ID to voice model name",
            },
        },
        "required": ["project_id"],
    },
    domain="audio",
)
async def panelflow_generate_audio_job(
    project_id: str,
    voice_casting: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = {"voice_casting": voice_casting} if voice_casting else {}
    return await bridge.post(f"/api/projects/{project_id}/audio/generate-job", payload)


@registry.tool(
    name="panelflow_get_audio_timeline",
    description="Retrieve the audio timeline containing synthesized voice clips, start times, durations, and word alignments.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="audio",
)
async def panelflow_get_audio_timeline(project_id: str) -> dict[str, Any]:
    return await bridge.get(f"/api/projects/{project_id}/audio/timeline")


@registry.tool(
    name="panelflow_music_health",
    description="Check health and GPU VRAM availability of the local neural music engine (ACE-Step 1.5 DiT).",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="audio",
)
async def panelflow_music_health() -> dict[str, Any]:
    return await bridge.get("/api/music/health")


@registry.tool(
    name="panelflow_get_music_plan",
    description="Retrieve or generate the story-aware soundtrack plan (BGM cues, BPM, intensity, mood transitions).",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "force_replan": {"type": "boolean", "description": "Force recalculating music cues"},
        },
        "required": ["project_id"],
    },
    domain="audio",
)
async def panelflow_get_music_plan(project_id: str, force_replan: bool = False) -> dict[str, Any]:
    return await bridge.get(f"/api/projects/{project_id}/music/plan?force_replan={str(force_replan).lower()}")
