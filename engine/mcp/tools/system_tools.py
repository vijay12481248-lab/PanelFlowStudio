"""System, hardware resources, models, and durable background jobs MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge


@registry.tool(
    name="panelflow_system_health",
    description="Check PanelFlow Studio engine health, application version, database integrity, and workspace root.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="system",
)
async def panelflow_system_health() -> dict[str, Any]:
    return await bridge.get("/api/system/health")


@registry.tool(
    name="panelflow_system_resources",
    description="Check local host hardware metrics: RTX 5060 Ti GPU VRAM free/total, system RAM, CPU load, and workspace disk space.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="system",
)
async def panelflow_system_resources() -> dict[str, Any]:
    return await bridge.get("/api/system/resources")


@registry.tool(
    name="panelflow_models_status",
    description="Inspect availability and health of local AI backends (Ollama qwen3.5:9b vision/text, ComfyUI :8188, ACE-Step :8001, MiniMax H3, Qwen Image 2.1).",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="system",
)
async def panelflow_models_status() -> dict[str, Any]:
    return await bridge.get("/api/system/models")


@registry.tool(
    name="panelflow_list_jobs",
    description="List all active and historical durable background jobs with status (QUEUED, PROCESSING, COMPLETED, FAILED), lease expiry, and step progress.",
    input_schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Maximum number of jobs to return (default: 50)"},
        },
    },
    domain="system",
)
async def panelflow_list_jobs(limit: int = 50) -> dict[str, Any]:
    return await bridge.get(f"/api/jobs?limit={limit}")


@registry.tool(
    name="panelflow_get_job",
    description="Retrieve detailed step progress, logs, payload parameters, error messages, and output artifacts for a specific background job ID.",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "The unique job ID (e.g. 'job_451ec694')"},
        },
        "required": ["job_id"],
    },
    domain="system",
)
async def panelflow_get_job(job_id: str) -> dict[str, Any]:
    return await bridge.get(f"/api/jobs/{job_id}")


@registry.tool(
    name="panelflow_cancel_job",
    description="Gracefully abort or cancel an active durable background job.",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "The unique job ID to cancel"},
        },
        "required": ["job_id"],
    },
    domain="system",
)
async def panelflow_cancel_job(job_id: str) -> dict[str, Any]:
    return await bridge.post(f"/api/jobs/{job_id}/cancel")
