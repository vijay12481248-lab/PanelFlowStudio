"""Projects, pages, ingestion and acquisition MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_list_projects",
    description="List all manga, comic, anime review, and original story projects in the PanelFlow workspace.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="projects",
)
async def panelflow_list_projects() -> list[dict[str, Any]]:
    return await bridge.get("/api/projects")


@registry.tool(
    name="panelflow_create_project",
    description="Create a new creative project in PanelFlow Studio.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Project title (e.g. 'Solo Leveling Ch 1')"},
            "source_type": {
                "type": "string",
                "enum": ["LOCAL_FOLDER", "ZIP_ARCHIVE", "GENERIC_AUTHORIZED_WEB", "ORIGINAL_STORY", "ANIME_EPISODE"],
                "description": "Source ingestion type",
            },
            "rights_status": {
                "type": "string",
                "enum": ["OWNED", "LICENSED", "PUBLIC_DOMAIN", "UNKNOWN"],
                "description": "Content rights declaration. Note: UNKNOWN will be held at rights gate.",
            },
            "source_url": {"type": "string", "description": "Local directory path, archive path, or URL"},
            "settings": {"type": "object", "description": "Optional project settings (e.g. target aspect ratio, reading order)"},
        },
        "required": ["title", "source_type", "rights_status"],
    },
    domain="projects",
)
async def panelflow_create_project(
    title: str,
    source_type: str,
    rights_status: str,
    source_url: str = "",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "title": title,
        "source_type": source_type,
        "rights_status": rights_status,
        "source_url": source_url,
        "settings": settings or {},
    }
    return await bridge.post("/api/projects", payload)


@registry.tool(
    name="panelflow_get_project",
    description="Retrieve full metadata, current pipeline stage, page counts, and stale timeline flags for a project ID.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The unique project ID"},
        },
        "required": ["project_id"],
    },
    domain="projects",
)
async def panelflow_get_project(project_id: str) -> dict[str, Any]:
    return await bridge.get(f"/api/projects/{project_id}")


@registry.tool(
    name="panelflow_delete_project",
    description="Delete a project and its managed workspace assets from PanelFlow Studio.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID to delete"},
            "confirm": {"type": "boolean", "description": "Must be set to true to confirm deletion"},
        },
        "required": ["project_id", "confirm"],
    },
    domain="projects",
)
async def panelflow_delete_project(project_id: str, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Deletion aborted: confirm parameter must be True.")
    await bridge.delete(f"/api/projects/{project_id}")
    return {"success": True, "message": f"Project {project_id} deleted"}


@registry.tool(
    name="panelflow_start_acquisition",
    description="Start the background ingestion job to read and unpack pages from the project's source.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="projects",
)
async def panelflow_start_acquisition(project_id: str) -> dict[str, Any]:
    return await bridge.post(f"/api/projects/{project_id}/acquire")


@registry.tool(
    name="panelflow_confirm_acquisition",
    description="Confirm ingested pages and advance the project pipeline to the normalized/panel detection stage.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="projects",
)
async def panelflow_confirm_acquisition(project_id: str) -> dict[str, Any]:
    return await bridge.post(f"/api/projects/{project_id}/confirm")


@registry.tool(
    name="panelflow_normalize_pages",
    description="Normalize, deskew, and standardize page images across a project to ensure uniform resolutions.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="projects",
)
async def panelflow_normalize_pages(project_id: str) -> dict[str, Any]:
    return await bridge.post(f"/api/projects/{project_id}/pages/normalize")


@registry.tool(
    name="panelflow_list_pages",
    description="List all imported pages in a project with sequence numbers, dimensions, and image asset URLs.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="projects",
)
async def panelflow_list_pages(project_id: str) -> list[dict[str, Any]]:
    return await bridge.get(f"/api/projects/{project_id}/pages")


@registry.tool(
    name="panelflow_reorder_pages",
    description="Reorder page sequence numbers in a project for correct storytelling flow.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "page_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of page IDs",
            },
        },
        "required": ["project_id", "page_ids"],
    },
    domain="projects",
)
async def panelflow_reorder_pages(project_id: str, page_ids: list[str]) -> list[dict[str, Any]]:
    return await bridge.post(f"/api/projects/{project_id}/pages/reorder", {"page_ids": page_ids})
