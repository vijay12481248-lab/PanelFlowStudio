"""Unit tests for PanelFlow Dedicated Creative Agents MCP Server."""

import json
import pytest
from engine.mcp.creative_mcp_server import CreativeMCPServer


@pytest.fixture
def mcp_server():
    return CreativeMCPServer(filter_creative_only=True)


@pytest.mark.asyncio
async def test_mcp_initialize(mcp_server: CreativeMCPServer):
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "antigravity-swarm", "version": "1.0"},
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "panelflow-creative-agents"
    assert "tools" in resp["result"]["capabilities"]


@pytest.mark.asyncio
async def test_mcp_ping(mcp_server: CreativeMCPServer):
    req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 2
    assert resp["result"] == {}


@pytest.mark.asyncio
async def test_mcp_notifications_ack(mcp_server: CreativeMCPServer):
    req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    resp = await mcp_server.handle_request(req)
    assert resp is None


@pytest.mark.asyncio
async def test_mcp_tools_list(mcp_server: CreativeMCPServer):
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    tools = resp["result"]["tools"]
    assert len(tools) >= 20

    tool_names = {t["name"] for t in tools}
    assert "panelflow_creative_showrunner_create_bible" in tool_names
    assert "panelflow_creative_novelist_write_chapter" in tool_names
    assert "panelflow_creative_critic_refine_chapter" in tool_names
    assert "panelflow_creative_cinematographer_create_storyboard" in tool_names
    assert "panelflow_creative_compiler_build_tool_prompts" in tool_names
    assert "panelflow_creative_manhua_direct_episode" in tool_names
    assert "panelflow_creative_knowledge_query" in tool_names
    assert "panelflow_creative_knowledge_add" in tool_names
    assert "panelflow_creative_knowledge_delete" in tool_names
    assert "panelflow_creative_analyze_manhua" in tool_names
    assert "panelflow_creative_forge_agent" in tool_names
    assert "panelflow_creative_forge_delete_agent" in tool_names
    assert "panelflow_creative_synthesize_skill" in tool_names
    assert "panelflow_creative_skill_delete" in tool_names
    assert "panelflow_creative_list_dynamic_agents" in tool_names
    assert "panelflow_creative_self_improve_audit" in tool_names
    assert "panelflow_creative_mistake_delete" in tool_names
    assert "panelflow_configure_freellmapi" in tool_names
    assert "panelflow_get_llm_status" in tool_names
    assert "panelflow_reset_to_local_llm" in tool_names


@pytest.mark.asyncio
async def test_mcp_call_knowledge_query(mcp_server: CreativeMCPServer):
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_knowledge_query",
            "arguments": {"query_text": "vertical scroll", "limit": 3},
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert not resp["result"]["isError"]
    content = json.loads(resp["result"]["content"][0]["text"])
    assert "entries" in content
    assert content["count"] >= 1


@pytest.mark.asyncio
async def test_mcp_call_knowledge_add(mcp_server: CreativeMCPServer):
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_knowledge_add",
            "arguments": {
                "title": "Dual Cultivation Qi Resonance Pattern",
                "content": "Aura collision produces dual-tone spiral waves across negative space.",
                "category": "cultivation_xianxia",
                "tags": ["qi", "resonance", "aura"],
            },
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert not resp["result"]["isError"]
    entry = json.loads(resp["result"]["content"][0]["text"])
    assert entry["title"] == "Dual Cultivation Qi Resonance Pattern"


@pytest.mark.asyncio
async def test_mcp_call_analyze_manhua(mcp_server: CreativeMCPServer):
    req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_analyze_manhua",
            "arguments": {
                "source_title": "Martial Peak",
                "chapter_identifier": "Ch. 500",
                "panels_manifest": [
                    {"aspect_ratio": "16:9", "gutter_spacing_px": 40, "dialogue_count": 4, "action_type": "punch"},
                    {"aspect_ratio": "9:16", "gutter_spacing_px": 200, "dialogue_count": 1, "action_type": "reveal"},
                ],
            },
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert not resp["result"]["isError"]
    report = json.loads(resp["result"]["content"][0]["text"])
    assert report["source_title"] == "Martial Peak"
    assert report["total_panels"] == 2


@pytest.mark.asyncio
async def test_mcp_call_manhua_direct_episode(mcp_server: CreativeMCPServer):
    req = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_manhua_direct_episode",
            "arguments": {
                "title": "Shattered Cauldron Awaken",
                "summary": "Lin Feng confronts the disciple who framed him at the Spirit Spring.",
                "target_panel_count": 4,
            },
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert not resp["result"]["isError"]
    episode = json.loads(resp["result"]["content"][0]["text"])
    assert episode["title"] == "Shattered Cauldron Awaken"
    assert len(episode["panels"]) >= 4
    # Check panel attributes
    first_panel = episode["panels"][0]
    assert "gutter_spacing_px" in first_panel
    assert "layout_type" in first_panel
    assert "art_prompt" in first_panel


@pytest.mark.asyncio
async def test_mcp_call_compiler_build_prompts(mcp_server: CreativeMCPServer):
    req = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_compiler_build_tool_prompts",
            "arguments": {
                "scenes_data": [
                    {
                        "scene_index": 1,
                        "name": "The Precipice",
                        "description": "Lin Feng at the cliff edge",
                        "shots": [
                            {
                                "shot_index": 1,
                                "scene_index": 1,
                                "title": "Establishing Cliff",
                                "shot_type": "Wide Establishing",
                                "duration": 5.0,
                                "workflow": "reference",
                                "camera_movement": "Slow pull back",
                                "subject_description": "Lin Feng looking over misty abyss",
                                "environmental_details": "Stone monoliths and cold fog",
                                "lighting_and_atmosphere": "Dramatic sunset chiaroscuro",
                                "soundscape": "Wind howling. Strict rule: absolutely no human speech or dialogue.",
                                "non_diegetic_music": "Low cello drone",
                            }
                        ],
                    }
                ]
            },
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert not resp["result"]["isError"]
    scenes = json.loads(resp["result"]["content"][0]["text"])["scenes"]
    shot = scenes[0]["shots"][0]
    assert "subject_definitions:" in shot["prompt"]
    assert "Masterpiece cinematic" in shot["art_prompt"]


@pytest.mark.asyncio
async def test_mcp_call_self_improve_audit(mcp_server: CreativeMCPServer):
    req = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_self_improve_audit",
            "arguments": {
                "agent_name": "NovelistAgent",
                "domain": "narrative",
                "content_to_audit": "The hero felt very sad and wept aloud.",
            },
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert not resp["result"]["isError"]
    audit = json.loads(resp["result"]["content"][0]["text"])
    assert "passed" in audit
    assert "violations_found" in audit


@pytest.mark.asyncio
async def test_mcp_call_knowledge_delete(mcp_server: CreativeMCPServer):
    # First add an entry
    add_req = {
        "jsonrpc": "2.0",
        "id": 20,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_knowledge_add",
            "arguments": {
                "title": "Ephemeral Entry to Delete",
                "content": "To be removed.",
            },
        },
    }
    add_resp = await mcp_server.handle_request(add_req)
    assert not add_resp["result"]["isError"]
    entry_id = json.loads(add_resp["result"]["content"][0]["text"])["entry_id"]

    # Now delete it
    del_req = {
        "jsonrpc": "2.0",
        "id": 21,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_knowledge_delete",
            "arguments": {"entry_id": entry_id},
        },
    }
    del_resp = await mcp_server.handle_request(del_req)
    assert not del_resp["result"]["isError"]
    res = json.loads(del_resp["result"]["content"][0]["text"])
    assert res["status"] == "deleted"


@pytest.mark.asyncio
async def test_mcp_call_forge_and_delete_agent(mcp_server: CreativeMCPServer):
    # Forge
    forge_req = {
        "jsonrpc": "2.0",
        "id": 22,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_forge_agent",
            "arguments": {
                "role_name": "TemporaryTestAgent",
                "domain": "testing",
                "description": "Ephemeral test agent",
                "system_prompt": "You are a test agent.",
            },
        },
    }
    f_resp = await mcp_server.handle_request(forge_req)
    assert not f_resp["result"]["isError"]

    # Delete
    del_req = {
        "jsonrpc": "2.0",
        "id": 23,
        "method": "tools/call",
        "params": {
            "name": "panelflow_creative_forge_delete_agent",
            "arguments": {"role_name": "TemporaryTestAgent"},
        },
    }
    d_resp = await mcp_server.handle_request(del_req)
    assert not d_resp["result"]["isError"]
    assert json.loads(d_resp["result"]["content"][0]["text"])["status"] == "deleted"


@pytest.mark.asyncio
async def test_mcp_call_configure_and_reset_freellmapi(mcp_server: CreativeMCPServer):
    # Configure Free LLM API
    cfg_req = {
        "jsonrpc": "2.0",
        "id": 24,
        "method": "tools/call",
        "params": {
            "name": "panelflow_configure_freellmapi",
            "arguments": {
                "api_key": "sk-mcp-test-freellmapi-key-9999",
                "endpoint_url": "https://openrouter.ai/api/v1",
                "model_name": "meta-llama/llama-3.3-70b-instruct:free",
                "set_as_global_default": True,
            },
        },
    }
    cfg_resp = await mcp_server.handle_request(cfg_req)
    assert not cfg_resp["result"]["isError"]
    res = json.loads(cfg_resp["result"]["content"][0]["text"])
    assert res["status"] == "configured"
    assert res["is_global_default"] is True

    # Get status
    stat_req = {
        "jsonrpc": "2.0",
        "id": 25,
        "method": "tools/call",
        "params": {"name": "panelflow_get_llm_status", "arguments": {}},
    }
    stat_resp = await mcp_server.handle_request(stat_req)
    assert not stat_resp["result"]["isError"]
    status_data = json.loads(stat_resp["result"]["content"][0]["text"])
    assert status_data["active_provider_id"] == "cloud_llm"

    # Reset back to local
    reset_req = {
        "jsonrpc": "2.0",
        "id": 26,
        "method": "tools/call",
        "params": {"name": "panelflow_reset_to_local_llm", "arguments": {}},
    }
    reset_resp = await mcp_server.handle_request(reset_req)
    assert not reset_resp["result"]["isError"]
    reset_data = json.loads(reset_resp["result"]["content"][0]["text"])
    assert reset_data["status"] == "switched_to_local"


@pytest.mark.asyncio
async def test_mcp_error_handling(mcp_server: CreativeMCPServer):
    # Method not found
    resp = await mcp_server.handle_request({"jsonrpc": "2.0", "id": 10, "method": "invalid/method"})
    assert resp["error"]["code"] == -32601

    # Missing tool name
    resp = await mcp_server.handle_request({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {}})
    assert resp["error"]["code"] == -32602

    # Reject non-creative tool on dedicated creative server
    resp = await mcp_server.handle_request({
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {"name": "panelflow_system_health", "arguments": {}},
    })
    assert resp["error"]["code"] == -32601
