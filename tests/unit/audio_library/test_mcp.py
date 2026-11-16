import pytest

import engine.mcp.tools  # noqa: F401  (registers every tool)
from engine.mcp.client_bridge import bridge
from engine.mcp.registry import registry
from engine.mcp.server import MCPServer

NAMES = {f"panelflow_audio_library_{n}" for n in ("list", "ops", "make_voice", "make_music", "find_effects", "keep_effect", "import", "edit", "undo", "split", "delete")}


def test_library_tools_are_in_the_chronoflow_and_all_profiles():
    for prof in ("chronoflow", "all"):
        assert NAMES <= {t["name"] for t in MCPServer(profile=prof).exposed_tools()}
    assert set(registry.get_tool("panelflow_audio_library_edit").input_schema["required"]) == {"sound_id", "op"}


@pytest.mark.asyncio
async def test_edit_undo_and_delete_hit_the_library_endpoints(monkeypatch):
    seen = []

    async def post(endpoint, json_data=None, timeout_s=600.0):
        seen.append(("POST", endpoint, json_data))
        return {}

    async def delete(endpoint, timeout_s=30.0):
        seen.append(("DELETE", endpoint, None))
        return {}
    monkeypatch.setattr(bridge, "post", post)
    monkeypatch.setattr(bridge, "delete", delete)
    await registry.get_tool("panelflow_audio_library_edit").handler(sound_id="snd_1", op="trim", a=0.0, b=1.0)
    await registry.get_tool("panelflow_audio_library_undo").handler(sound_id="snd_1", redo=True)
    await registry.get_tool("panelflow_audio_library_delete").handler(sound_id="snd_1")
    assert seen == [("POST", "/api/audio/library/sounds/snd_1/edit", {"op": "trim", "params": {}, "a": 0.0, "b": 1.0}),
                    ("POST", "/api/audio/library/sounds/snd_1/redo", None), ("DELETE", "/api/audio/library/sounds/snd_1", None)]
