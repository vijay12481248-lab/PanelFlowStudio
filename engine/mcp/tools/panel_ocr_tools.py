"""Panel detection, polygon geometry, OCR detection, and balloon inpainting MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_detect_panels",
    description="Run automated AI contour polygon panel detection across a comic page or the entire project.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "page_id": {"type": "string", "description": "Optional specific page ID to detect panels on"},
        },
        "required": ["project_id"],
    },
    domain="panels",
)
async def panelflow_detect_panels(project_id: str, page_id: str | None = None) -> list[dict[str, Any]]:
    if page_id:
        return await bridge.post(f"/api/projects/{project_id}/pages/{page_id}/detect-panels")
    # Detect for all pages
    pages = await bridge.get(f"/api/projects/{project_id}/pages")
    results = []
    for p in pages:
        pid = p.get("id")
        if pid:
            res = await bridge.post(f"/api/projects/{project_id}/pages/{pid}/detect-panels")
            results.extend(res)
    return results


@registry.tool(
    name="panelflow_list_panels",
    description="List all segmented panels for a project with bounding boxes, polygon vertices, sequence, and crop asset URLs.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="panels",
)
async def panelflow_list_panels(project_id: str) -> list[dict[str, Any]]:
    return await bridge.get(f"/api/projects/{project_id}/panels")


@registry.tool(
    name="panelflow_save_panel_selections",
    description="Update or replace panel crop geometry / polygon boundaries on a page or panel.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "panel_id": {"type": "string", "description": "Target panel ID"},
            "selections": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of panel selection bounding boxes and polygons",
            },
        },
        "required": ["project_id", "panel_id", "selections"],
    },
    domain="panels",
)
async def panelflow_save_panel_selections(
    project_id: str,
    panel_id: str,
    selections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return await bridge.put(
        f"/api/projects/{project_id}/panels/{panel_id}/selections",
        {"selections": selections},
    )


@registry.tool(
    name="panelflow_blur_panel_text",
    description="Inpaint or blur speech balloons on a panel crop to prepare clean background art for video.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "panel_id": {"type": "string", "description": "Target panel ID"},
            "region_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of text region IDs to redact (leave empty for all detected regions)",
            },
            "blur_radius": {"type": "integer", "description": "Blur kernel radius in pixels (default: 15)"},
            "feather": {"type": "integer", "description": "Edge feathering in pixels (default: 8)"},
        },
        "required": ["project_id", "panel_id"],
    },
    domain="panels",
)
async def panelflow_blur_panel_text(
    project_id: str,
    panel_id: str,
    region_ids: list[str] | None = None,
    blur_radius: int = 15,
    feather: int = 8,
) -> dict[str, Any]:
    payload = {
        "region_ids": region_ids,
        "blur_radius": blur_radius,
        "feather": feather,
    }
    return await bridge.post(f"/api/projects/{project_id}/panels/{panel_id}/blur-text", payload)


@registry.tool(
    name="panelflow_reset_panel_image",
    description="Reset a redacted/blurred panel back to its original unedited crop.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "panel_id": {"type": "string", "description": "Target panel ID"},
        },
        "required": ["project_id", "panel_id"],
    },
    domain="panels",
)
async def panelflow_reset_panel_image(project_id: str, panel_id: str) -> dict[str, Any]:
    return await bridge.post(f"/api/projects/{project_id}/panels/{panel_id}/reset-image")


@registry.tool(
    name="panelflow_detect_text_regions",
    description="Detect speech balloons, dialogue boxes, and SFX across panels in a project using Windows OCR / local vision.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "page_id": {"type": "string", "description": "Optional specific page ID"},
        },
        "required": ["project_id"],
    },
    domain="ocr",
)
async def panelflow_detect_text_regions(project_id: str, page_id: str | None = None) -> list[dict[str, Any]]:
    query = f"?page_id={page_id}" if page_id else ""
    return await bridge.post(f"/api/projects/{project_id}/detect-text-regions{query}")


@registry.tool(
    name="panelflow_list_text_regions",
    description="List all recognized text regions with OCR text, confidence scores, bounding coordinates, and speaker attributions.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
        },
        "required": ["project_id"],
    },
    domain="ocr",
)
async def panelflow_list_text_regions(project_id: str) -> list[dict[str, Any]]:
    return await bridge.get(f"/api/projects/{project_id}/text-regions")


@registry.tool(
    name="panelflow_update_text_region",
    description="Correct, translate, or adjust dialogue text and speaker character assignment for an OCR region.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "The project ID"},
            "region_id": {"type": "string", "description": "Target text region ID"},
            "corrected_text": {"type": "string", "description": "The corrected or translated dialogue text"},
            "speaker_character_id": {"type": "string", "description": "Character ID of the speaker"},
        },
        "required": ["project_id", "region_id", "corrected_text"],
    },
    domain="ocr",
)
async def panelflow_update_text_region(
    project_id: str,
    region_id: str,
    corrected_text: str,
    speaker_character_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"corrected_text": corrected_text}
    if speaker_character_id:
        payload["speaker_character_id"] = speaker_character_id
    return await bridge.put(f"/api/projects/{project_id}/text-regions/{region_id}", payload)
