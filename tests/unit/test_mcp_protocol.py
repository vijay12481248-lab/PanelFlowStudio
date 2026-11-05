import pytest
import asyncio
from unittest.mock import patch, MagicMock
from engine.mcp.server import MCPServer
from engine.mcp.registry import registry
import engine.mcp.tools


@pytest.mark.asyncio
async def test_mcp_initialize():
    server = MCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = await server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "panelflow-studio-mcp"
    assert "tools" in resp["result"]["capabilities"]


@pytest.mark.asyncio
async def test_mcp_ping():
    server = MCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "ping",
    }
    resp = await server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 2
    assert resp["result"] == {}


@pytest.mark.asyncio
async def test_mcp_tools_list():
    server = MCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/list",
    }
    resp = await server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 3
    tools = resp["result"]["tools"]
    assert len(tools) >= 40

    tool_names = {t["name"] for t in tools}
    # System
    assert "panelflow_system_health" in tool_names
    assert "panelflow_system_resources" in tool_names
    assert "panelflow_models_status" in tool_names
    assert "panelflow_list_jobs" in tool_names
    # Projects
    assert "panelflow_list_projects" in tool_names
    assert "panelflow_create_project" in tool_names
    assert "panelflow_list_pages" in tool_names
    # Panels & OCR
    assert "panelflow_detect_panels" in tool_names
    assert "panelflow_list_panels" in tool_names
    assert "panelflow_detect_text_regions" in tool_names
    # Story & Audio
    assert "panelflow_analyze_story" in tool_names
    assert "panelflow_generate_script" in tool_names
    assert "panelflow_generate_audio_job" in tool_names
    assert "panelflow_get_music_plan" in tool_names
    # Motion & Render
    assert "panelflow_plan_motion_timeline" in tool_names
    assert "panelflow_create_render_job" in tool_names
    assert "panelflow_generate_youtube_packaging" in tool_names
    # Original Stories
    assert "panelflow_original_create_story" in tool_names
    assert "panelflow_original_generate_art" in tool_names
    assert "panelflow_original_render_video" in tool_names
    # Anime Review
    assert "panelflow_anime_ingest_episode" in tool_names
    assert "panelflow_anime_render_review" in tool_names
    # ChronoFlow MiniMax H3
    assert "panelflow_chronoflow_status" in tool_names
    assert "panelflow_chronoflow_generate_video" in tool_names
    assert "panelflow_chronoflow_generate_image" in tool_names
    assert "panelflow_chronoflow_inpaint_image" in tool_names
    assert "panelflow_chronoflow_export_timeline" in tool_names
    # Autopilot
    assert "panelflow_run_autopilot" in tool_names
    assert "panelflow_get_autopilot_status" in tool_names

    # Check that each tool has complete schema
    for t in tools:
        assert "name" in t
        assert "description" in t
        assert "inputSchema" in t
        assert t["inputSchema"].get("type") == "object"


@pytest.mark.asyncio
async def test_mcp_tool_execution():
    server = MCPServer()

    with patch("engine.mcp.client_bridge.bridge.get") as mock_get:
        mock_get.return_value = {"status": "healthy", "version": "1.0.0"}
        call_req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "panelflow_system_health",
                "arguments": {},
            },
        }
        resp = await server.handle_request(call_req)
        assert resp is not None
        assert resp["id"] == 4
        assert resp["result"]["isError"] is False
        content = resp["result"]["content"]
        assert len(content) == 1
        assert "healthy" in content[0]["text"]


@pytest.mark.asyncio
async def test_mcp_unknown_tool():
    server = MCPServer()
    call_req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "panelflow_nonexistent_tool",
            "arguments": {},
        },
    }
    resp = await server.handle_request(call_req)
    assert resp is not None
    assert resp["id"] == 5
    assert resp["result"]["isError"] is True
    assert "Tool execution failed" in resp["result"]["content"][0]["text"]
