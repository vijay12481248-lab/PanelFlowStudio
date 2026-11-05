"""Autonomous 1-Click Pipeline Auto-Pilot MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_run_autopilot",
    description="Trigger the 1-Click autonomous pipeline runner to advance a project from raw imported comic pages to final rendered master video.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID to run autopilot on"},
            "target_profile": {
                "type": "string",
                "enum": ["standard_1080p", "vertical_shorts", "square_feed"],
                "description": "Render profile (default: standard_1080p)",
            },
            "skip_existing_stages": {
                "type": "boolean",
                "description": "Skip stages that have already been generated and approved (default: true)",
            },
            "voice_preset": {"type": "string", "description": "Optional default voice preset ID"},
            "enable_thumbnails": {"type": "boolean", "description": "Generate YouTube thumbnail candidate (default: true)"},
        },
        "required": ["project_id"],
    },
    domain="autopilot",
)
async def panelflow_run_autopilot(
    project_id: str,
    target_profile: str = "standard_1080p",
    skip_existing_stages: bool = True,
    voice_preset: str | None = None,
    enable_thumbnails: bool = True,
) -> dict[str, Any]:
    payload = {
        "target_profile": target_profile,
        "skip_existing_stages": skip_existing_stages,
        "voice_preset": voice_preset,
        "enable_thumbnails": enable_thumbnails,
    }
    return await bridge.post(f"/api/projects/{project_id}/autopilot/run", payload)


@registry.tool(
    name="panelflow_get_autopilot_status",
    description="Query current autopilot progress, active stage, and completed milestones for a project.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="autopilot",
)
async def panelflow_get_autopilot_status(project_id: str) -> dict[str, Any]:
    return await bridge.get(f"/api/projects/{project_id}/autopilot/status")
