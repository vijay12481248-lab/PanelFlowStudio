"""YouTube publishing and multi-channel MCP tools for AI Agents."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_youtube_status",
    description="Check YouTube channel connection status, active channel profile, and agent upload permissions.",
    input_schema={
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "description": "Optional channel profile ID to inspect (defaults to active channel)"}
        },
    },
    domain="youtube",
)
async def panelflow_youtube_status(channel_id: str | None = None) -> dict[str, Any]:
    params = f"?channel_id={channel_id}" if channel_id else ""
    return await bridge.get(f"/api/youtube/status{params}")


@registry.tool(
    name="panelflow_youtube_list_channels",
    description="List all configured YouTube channels and see which channel is currently active for uploads.",
    input_schema={"type": "object", "properties": {}},
    domain="youtube",
)
async def panelflow_youtube_list_channels() -> dict[str, Any]:
    return await bridge.get("/api/youtube/channels")


@registry.tool(
    name="panelflow_youtube_upload_episode",
    description="Upload a finished story episode to YouTube using the active channel profile (honoring agent upload permissions configured in Settings).",
    input_schema={
        "type": "object",
        "properties": {
            "series_id": {"type": "string", "description": "Series ID"},
            "episode_number": {"type": "integer", "description": "Episode number to upload (must have status 'done')"},
            "made_for_kids": {"type": "boolean", "description": "COPPA legal declaration: whether video is made for kids"},
            "privacy": {"type": "string", "enum": ["private", "unlisted", "public"], "description": "Upload privacy (defaults to 'private')"},
            "schedule": {"type": "boolean", "description": "Whether to schedule release according to episode publish slot"},
            "confirm_public": {"type": "boolean", "description": "Must be true if privacy is 'public' or schedule is true"},
        },
        "required": ["series_id", "episode_number", "made_for_kids"],
    },
    domain="youtube",
)
async def panelflow_youtube_upload_episode(
    series_id: str,
    episode_number: int,
    made_for_kids: bool,
    privacy: str = "private",
    schedule: bool = False,
    confirm_public: bool = False,
) -> dict[str, Any]:
    # Check agent settings first
    status = await bridge.get("/api/youtube/status")
    agent_settings = status.get("agent_settings", {})
    if not agent_settings.get("enabled", True):
        return {
            "error": "Agent YouTube uploads are disabled in PanelFlow Settings. Please enable 'Allow AI Agents to upload' in the YouTube Settings panel.",
            "status": "refused",
        }

    payload = {
        "made_for_kids": made_for_kids,
        "privacy": privacy,
        "schedule": schedule,
        "confirm_public": confirm_public,
    }
    return await bridge.post(
        f"/api/original/series/{series_id}/episodes/{episode_number}/upload",
        payload,
    )
