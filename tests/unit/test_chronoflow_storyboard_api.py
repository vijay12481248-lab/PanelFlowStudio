"""Unit tests for ChronoFlow Storyboard & Screenplay APIs and MCP tools."""

import pytest
from fastapi.testclient import TestClient
from engine.api.app import app
from engine.mcp.registry import registry
import engine.mcp.tools


@pytest.fixture
def client():
    return TestClient(app)


def test_list_screenplays(client):
    """Verify listing screenplays from vault."""
    resp = client.get("/api/chronoflow/screenplays")
    assert resp.status_code == 200
    data = resp.json()
    assert "screenplays" in data
    assert len(data["screenplays"]) >= 2
    filenames = [s["filename"] for s in data["screenplays"]]
    assert "screenplay_avalon_prime_2min.json" in filenames
    assert "screenplay_agent_whiskers_3shot.json" in filenames


def test_get_screenplay_avalon_prime(client):
    """Verify loading and normalizing the 24-shot Avalon Prime master screenplay."""
    resp = client.get("/api/chronoflow/screenplay/screenplay_avalon_prime_2min.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "CHRONO RELIC: AVALON PRIME"
    assert len(data["scenes"]) == 24
    
    # Check shot normalization
    shot1 = data["scenes"][0]
    assert shot1["shot_index"] == 1
    assert "The Threshold of Eternity" in shot1["title"]
    assert shot1["shot_type"] == "Wide Establishing"
    assert shot1["duration"] == 5.2
    assert "prompt" in shot1 and len(shot1["prompt"]) > 50


def test_get_screenplay_agent_whiskers(client):
    """Verify loading the Agent Whiskers 3-shot screenplay."""
    resp = client.get("/api/chronoflow/screenplay/screenplay_agent_whiskers_3shot.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "AGENT WHISKERS" in data["title"]
    assert len(data["scenes"]) == 3
    assert data["protagonist"]["name"] == "Agent Whiskers"


def test_screenplay_path_traversal_blocked(client):
    """Verify security check blocks directory traversal attempts."""
    resp = client.get("/api/chronoflow/screenplay/..%2fevil.json")
    assert resp.status_code in (400, 404)
    resp2 = client.get("/api/chronoflow/screenplay/not_a_json_file.txt")
    assert resp2.status_code == 400


def test_ai_director_plan_endpoint(client):
    """Verify AI Director creates structured 6-heading storyboard beats."""
    payload = {
        "idea": "Cyberpunk infiltrator hacks an orbital space station",
        "duration": 15,
        "genre": "cyberpunk",
        "protagonist_name": "Ghost-9",
        "protagonist_tag": "<Picture 3>",
    }
    resp = client.post("/api/chronoflow/ai_director/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["scenes"]) == 3
    assert data["scenes"][0]["shot_type"] == "Wide Establishing"
    assert "camera_movement" in data["scenes"][0]["prompt"]
    assert "Ghost-9" in data["scenes"][0]["prompt"]


def test_save_and_retrieve_screenplay(client):
    """Verify saving a custom storyboard blueprint and reading it back."""
    from engine.chronoflow.supervisor import VAULT_DIR

    custom_title = "Unit Test Cyber Odyssey"
    temp_filename = "screenplay_unit_test_temp.json"
    save_payload = {
        "title": custom_title,
        "duration": 10.4,
        "protagonist": {"name": "Test Hero", "role": "Protagonist"},
        "scenes": [
            {
                "shot_index": 1,
                "title": "Shot 1: Genesis",
                "shot_type": "Wide Establishing",
                "duration": 5.2,
                "workflow": "reference",
                "prompt": "summary: Genesis shot\n\ndetailed_description: camera_movement: Wide push.",
            },
            {
                "shot_index": 2,
                "title": "Shot 2: Climax",
                "shot_type": "Dynamic Climax",
                "duration": 5.2,
                "workflow": "sliding_window",
                "prompt": "summary: Climax shot\n\ndetailed_description: camera_movement: Whip pan.",
            },
        ],
        "filename": temp_filename,
    }

    try:
        # Save
        resp = client.post("/api/chronoflow/screenplay/save", json=save_payload)
        assert resp.status_code == 200
        saved = resp.json()
        assert saved["success"] is True
        assert saved["filename"] == temp_filename

        # Retrieve
        get_resp = client.get(f"/api/chronoflow/screenplay/{temp_filename}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["title"] == custom_title
        assert len(data["scenes"]) == 2
    finally:
        temp_file = VAULT_DIR / temp_filename
        if temp_file.exists():
            temp_file.unlink()


@pytest.mark.asyncio
async def test_mcp_screenplay_tools():
    """Verify the MCP tools for screenplays execute cleanly."""
    from unittest.mock import patch

    with patch("engine.mcp.client_bridge.bridge.get") as mock_get:
        mock_get.side_effect = [
            {"screenplays": [{"filename": "screenplay_avalon_prime_2min.json", "title": "CHRONO RELIC: AVALON PRIME"}]},
            {"title": "CHRONO RELIC: AVALON PRIME", "scenes": [{"shot_index": 1}] * 24},
        ]
        # List
        list_res = await registry.call_tool("panelflow_chronoflow_list_screenplays", {})
        assert "screenplays" in list_res
        assert len(list_res["screenplays"]) >= 1

        # Get
        get_res = await registry.call_tool("panelflow_chronoflow_get_screenplay", {
            "filename": "screenplay_avalon_prime_2min.json"
        })
        assert get_res["title"] == "CHRONO RELIC: AVALON PRIME"
        assert len(get_res["scenes"]) == 24


# ---- New Video wizard endpoints
def test_storyboard_plan_builds_cards(client):
    r = client.post("/api/chronoflow/storyboard/plan", json={"mode": "first_last", "length_seconds": 300, "title": "T"})
    assert r.status_code == 200 and len(r.json()["scenes"]) == 58 and r.json()["scenes"][0]["start_mode"] == "first_last"


@pytest.mark.parametrize("body", [{"mode": "first", "length_seconds": 0}, {"mode": "sideways", "length_seconds": 15}, {"mode": "text", "length_seconds": 5000}])
def test_storyboard_plan_rejects_bad_input(client, body):
    assert client.post("/api/chronoflow/storyboard/plan", json=body).status_code == 400


def _fake_llm(monkeypatch, reply):
    from engine.llm.providers.ollama import OllamaProvider

    async def fake(self, prompt, system_prompt=None, **kw):
        return reply

    monkeypatch.setattr(OllamaProvider, "generate_text", fake)


def test_draft_prompts_returns_exactly_count(client, monkeypatch):
    _fake_llm(monkeypatch, '["a", "b", "c"]')
    r = client.post("/api/chronoflow/storyboard/draft_prompts", json={"idea": "x", "count": 3, "mode": "text"})
    assert r.status_code == 200 and r.json()["prompts"] == ["a", "b", "c"]


def test_draft_prompts_wrong_count_is_502_not_padded(client, monkeypatch):
    _fake_llm(monkeypatch, '["a", "b", "c"]')
    r = client.post("/api/chronoflow/storyboard/draft_prompts", json={"idea": "x", "count": 4, "mode": "text"})
    assert r.status_code == 502 and "4" in r.json()["detail"]


def test_tail_frame_rejects_paths_and_missing_clips(client, monkeypatch, tmp_path):
    from engine.api.routers import chronoflow as router

    monkeypatch.setattr(router, "STUDIO_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(router, "COMFY_INPUT_DIR", tmp_path)
    assert client.post("/api/chronoflow/storyboard/tail_frame", json={"video": "../x.mp4"}).status_code == 400
    assert client.post("/api/chronoflow/storyboard/tail_frame", json={"video": "nope.mp4"}).status_code == 404
    (tmp_path / "clip.mp4").write_bytes(b"x")
    monkeypatch.setattr(router.pipeline, "extract_tail_frame", lambda v, o: (open(o, "wb").write(b"png"), True)[1])
    r = client.post("/api/chronoflow/storyboard/tail_frame", json={"video": "clip.mp4"})
    assert r.status_code == 200 and (tmp_path / r.json()["filename"]).exists()


def test_screenplay_round_trip_keeps_wizard_card_fields(client, monkeypatch, tmp_path):
    """A plan saved by the New Video wizard must come back with its start mode, frames-to-be, approval state and size intact."""
    from engine.api.routers import chronoflow as router

    monkeypatch.setattr(router, "VAULT_DIR", tmp_path)
    plan = client.post("/api/chronoflow/storyboard/plan", json={"mode": "first_last", "length_seconds": 15, "title": "Round trip"}).json()
    plan["scenes"][0].update(prompt="a door opens", first_frame="a.png", last_frame="b.png", approved=True, state="approved", tail_frame="t.png", width=768, height=1344, lora_choice="8step")
    saved = client.post("/api/chronoflow/screenplay/save", json={"title": "Round trip", "duration": plan["duration"], "scenes": plan["scenes"]}).json()
    back = client.get(f"/api/chronoflow/screenplay/{saved['filename']}").json()["scenes"][0]
    for key, want in {"start_mode": "first_last", "inherits_tail": False, "approved": True, "state": "approved", "tail_frame": "t.png", "width": 768, "height": 1344,
                      "lora_choice": "8step", "first_prompt": "", "last_frame": "b.png"}.items():
        assert back[key] == want, key
