import pytest

import engine.mcp.tools  # noqa: F401  (registers every tool)
from engine.mcp.client_bridge import bridge
from engine.mcp.registry import registry
from engine.mcp.server import MCPServer

NAMES = {f"panelflow_chronoflow_audio_{n}" for n in
         ("providers", "create_plan", "get_plan", "put_plan", "spot", "source_cue", "pick", "qa", "mix", "export")}


def _exposed(profile):
    return {t["name"] for t in MCPServer(profile=profile).exposed_tools()}


def test_tools_registered_in_chronoflow_and_all_profiles_not_creative():
    assert NAMES <= _exposed("chronoflow") and NAMES <= _exposed("all")
    assert not NAMES & _exposed("creative")


@pytest.mark.parametrize("name,required", [
    ("create_plan", {"video_path"}), ("get_plan", {"plan_id"}), ("put_plan", {"plan_id"}), ("spot", {"plan_id"}),
    ("source_cue", {"plan_id", "cue_id"}), ("pick", {"plan_id", "cue_id", "candidate_id"}), ("qa", {"plan_id"}),
    ("mix", {"plan_id"}), ("export", {"plan_id"}), ("providers", set())])
def test_each_tool_has_required_ids_in_schema(name, required):
    schema = registry.get_tool(f"panelflow_chronoflow_audio_{name}").input_schema
    assert set(schema.get("required", [])) == required
    assert required <= set(schema["properties"])


@pytest.mark.asyncio
async def test_calls_hit_the_expected_endpoints(monkeypatch):
    seen = []

    async def post(endpoint, json_data=None, timeout_s=600.0):
        seen.append(("POST", endpoint, json_data, timeout_s))
        return {"ok": True}

    async def put(endpoint, json_data=None, timeout_s=60.0):
        seen.append(("PUT", endpoint, json_data))
        return {"ok": True}

    async def get(endpoint, *a, **k):
        seen.append(("GET", endpoint))
        return {"ok": True}
    monkeypatch.setattr(bridge, "post", post)
    monkeypatch.setattr(bridge, "put", put)
    monkeypatch.setattr(bridge, "get", get)
    srv = MCPServer(profile="all")
    for name, args in (("source_cue", {"plan_id": "p1", "cue_id": "c1", "mode": "ask"}), ("mix", {"plan_id": "p1", "target_lufs": -16}),
                       ("put_plan", {"plan_id": "p1", "cues": [{"id": "c1"}]}), ("get_plan", {"plan_id": "p1"}), ("providers", {})):
        await registry.call_tool(f"panelflow_chronoflow_audio_{name}", args)
    assert seen[0][:3] == ("POST", "/api/audio/studio/plans/p1/cues/c1/source", {"mode": "ask"})
    assert seen[1][:3] == ("POST", "/api/audio/studio/plans/p1/mix", {"target_lufs": -16}) and seen[1][3] >= 600
    assert seen[2] == ("PUT", "/api/audio/studio/plans/p1", {"cues": [{"id": "c1"}]})
    assert seen[3] == ("GET", "/api/audio/studio/plans/p1") and seen[4] == ("GET", "/api/audio/studio/providers")
    assert srv is not None
