"""Motion director, video rendering, YouTube packaging, and upload MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_plan_motion_timeline",
    description="Generate 2.5D camera choreography (push-in, pan, tilt, Dutch angle, parallax shake, zoom burst) for each panel.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "style_preset": {"type": "string", "description": "Motion style preset (e.g. 'cinematic', 'dynamic_action', 'calm')"},
            "overrides": {"type": "object", "description": "Optional panel-by-panel camera motion overrides"},
        },
        "required": ["project_id"],
    },
    domain="motion",
)
async def panelflow_plan_motion_timeline(
    project_id: str,
    style_preset: str = "cinematic",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "style_preset": style_preset,
        "overrides": overrides,
    }
    return await bridge.post(f"/api/projects/{project_id}/motion/plan", payload)


@registry.tool(
    name="panelflow_get_motion_timeline",
    description="Retrieve the visual motion timeline containing panel shot durations, camera keyframes, transitions, and effects.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="motion",
)
async def panelflow_get_motion_timeline(project_id: str) -> dict[str, Any]:
    return await bridge.get(f"/api/projects/{project_id}/motion/timeline")


@registry.tool(
    name="panelflow_get_render_profiles",
    description="List available production rendering profiles (standard_1080p, vertical_shorts, square_feed, draft_720p).",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="render",
)
async def panelflow_get_render_profiles() -> dict[str, Any]:
    return await bridge.get("/api/render/profiles")


@registry.tool(
    name="panelflow_create_render_job",
    description="Enqueue a high-bitrate video render job producing mastered MP4 video with synced voiceover, BGM, and camera motion.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "profile_name": {
                "type": "string",
                "enum": ["standard_1080p", "vertical_shorts", "square_feed", "draft_720p"],
                "description": "Render profile (default: standard_1080p for 16:9, vertical_shorts for 9:16 Shorts)",
            },
            "is_draft": {"type": "boolean", "description": "Render fast draft preview"},
            "subtitle_enabled": {"type": "boolean", "description": "Burn in subtitles/captions"},
            "bgm_volume_db": {"type": "number", "description": "BGM volume in dB (default: -10.0)"},
        },
        "required": ["project_id"],
    },
    domain="render",
)
async def panelflow_create_render_job(
    project_id: str,
    profile_name: str = "standard_1080p",
    is_draft: bool = False,
    subtitle_enabled: bool = False,
    bgm_volume_db: float = -10.0,
) -> dict[str, Any]:
    payload = {
        "profile_name": profile_name,
        "is_draft": is_draft,
        "subtitle_enabled": subtitle_enabled,
        "bgm_volume_db": bgm_volume_db,
    }
    return await bridge.post(f"/api/projects/{project_id}/render/jobs", payload)


@registry.tool(
    name="panelflow_generate_youtube_packaging",
    description="Generate high-CTR YouTube title, description, SEO tags, timestamped chapters, and thumbnail prompt.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "style_tone": {
                "type": "string",
                "enum": ["dramatic", "action", "mysterious", "hype", "emotional"],
                "description": "Packaging style tone (default: dramatic)",
            },
            "custom_hook": {"type": "string", "description": "Optional custom hook line for title/description"},
        },
        "required": ["project_id"],
    },
    domain="youtube",
)
async def panelflow_generate_youtube_packaging(
    project_id: str,
    style_tone: str = "dramatic",
    custom_hook: str | None = None,
) -> dict[str, Any]:
    payload = {
        "style_tone": style_tone,
        "custom_hook": custom_hook,
    }
    return await bridge.post(f"/api/projects/{project_id}/youtube/packaging/generate", payload)


@registry.tool(
    name="panelflow_youtube_status",
    description="Check YouTube OAuth authentication and channel connection status.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="youtube",
)
async def panelflow_youtube_status() -> dict[str, Any]:
    return await bridge.get("/api/youtube/status")


@registry.tool(
    name="panelflow_upload_youtube",
    description="Publish a rendered video to YouTube via authenticated OAuth API. Safe publishing rules: privacyStatus strictly defaults to 'private'.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "title": {"type": "string", "description": "Video title"},
            "description": {"type": "string", "description": "Video description text"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "SEO tags"},
            "privacy_status": {
                "type": "string",
                "enum": ["private", "unlisted", "public"],
                "description": "Upload visibility (strictly 'private' by default)",
            },
            "made_for_kids": {"type": "boolean", "description": "Owner COPPA declaration (no default)"},
        },
        "required": ["project_id", "title", "made_for_kids"],
    },
    domain="youtube",
)
async def panelflow_upload_youtube(
    project_id: str,
    title: str,
    made_for_kids: bool,
    description: str = "",
    tags: list[str] | None = None,
    privacy_status: str = "private",
) -> dict[str, Any]:
    payload = {
        "title": title,
        "description": description,
        "tags": tags or [],
        "privacyStatus": privacy_status,
        "madeForKids": made_for_kids,
    }
    return await bridge.post(f"/api/projects/{project_id}/youtube/upload", payload)
