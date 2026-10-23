"""
Tests for Two-Tier Hierarchical Page & Panel Story Narration and Cloud LLM Integration.
"""
import pytest
import os
from engine.story.narration import (
    build_hierarchical_story_prompt,
    format_character_roster,
    story_narration_service,
    StructuredStoryBeat,
)
from engine.llm.registry import llm_registry


def test_format_character_roster():
    chars = [
        {
            "name": "Zhou Fan",
            "canonical_name": "Zhou Fan",
            "role": "PROTAGONIST",
            "visual_traits": ["black hair", "cunning eyes", "dark robe"],
            "aliases": ["Steward Zhou", "Demon Emperor"],
            "description": "Reincarnated ruthless strategist managing the Luo Clan.",
        },
        {
            "name": "Luo Yunchang",
            "canonical_name": "Luo Yunchang",
            "role": "SUPPORTING",
            "visual_traits": ["silk dress", "gentle expression"],
            "aliases": ["Young Miss Luo"],
            "description": "Head of the Luo Clan.",
        }
    ]
    roster_str = format_character_roster(chars)
    assert "Zhou Fan" in roster_str
    assert "PROTAGONIST" in roster_str
    assert "Steward Zhou" in roster_str
    assert "Luo Yunchang" in roster_str


def test_build_hierarchical_story_prompt_contains_rules_and_page_context():
    scenes = [
        {
            "id": "scene_1",
            "sequence": 1,
            "page_id": "page_001",
            "page_sequence": 1,
            "visual_description": "Close-up on Zhou Fan smiling coldly",
            "ocr_text": "You dare oppose me?",
            "characters": ["Zhou Fan"],
        }
    ]
    pages_macro = {
        "page_001": "Thunderstorm over Black Wind Mountain; ancient carriage ambushed by assassins.",
        "1": "Thunderstorm over Black Wind Mountain; ancient carriage ambushed by assassins.",
    }
    chars = [
        {"name": "Zhou Fan", "role": "PROTAGONIST", "aliases": ["Steward Zhou"]}
    ]

    prompt = build_hierarchical_story_prompt(
        scenes_data=scenes,
        pages_data=[{"id": "page_001", "sequence": 1, "filename": "page_001.jpg"}],
        characters_data=chars,
        page_macro_analyses=pages_macro,
    )

    # Verify critical rules
    assert "STRICT NAME GROUNDING" in prompt
    assert "NEVER use generic placeholders like 'the white-haired man'" in prompt
    assert "PAGE-LEVEL MACRO CONTEXT" in prompt
    assert "Thunderstorm over Black Wind Mountain" in prompt
    assert "Zhou Fan" in prompt
    assert "You dare oppose me?" in prompt


@pytest.mark.asyncio
async def test_generate_narration_draft_fallback_with_character_name(monkeypatch):
    monkeypatch.setenv("PANELFLOW_ALLOW_MOCK_LLM", "true")

    scenes = [
        {
            "id": "scene_10",
            "sequence": 1,
            "page_id": "page_005",
            "page_sequence": 5,
            "visual_description": "Glares at enemy formation with icy intent",
            "ocr_text": "Prepare to face the consequences.",
            "characters": ["Zhou Fan"],
        }
    ]
    chars = [
        {"name": "Zhou Fan", "canonical_name": "Zhou Fan", "role": "PROTAGONIST"}
    ]
    pages = [
        {"id": "page_005", "sequence": 5, "filename": "page_005.jpg", "ocr_lines": ["Prepare to face the consequences."]}
    ]

    plan = await story_narration_service.generate_narration_draft(
        project_id="test_proj_123",
        scenes_data=scenes,
        pages_data=pages,
        characters_data=chars,
    )

    assert plan.project_id == "test_proj_123"
    assert len(plan.beats) >= 1
    beat = plan.beats[0]
    assert beat.scene_id == "scene_10"
    assert beat.character_name == "Zhou Fan"
    assert beat.page_sequence == 5
    assert "Zhou Fan" in beat.proposed_narration_text
    assert beat.observed_ocr_dialogue == "Prepare to face the consequences."


def test_cloud_llm_registry_configuration(tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "cloud_llm_config.json"
    monkeypatch.setattr(llm_registry, "_cloud_config_path", test_cfg_path)

    provider = llm_registry.configure_cloud_provider(
        endpoint_url="https://openrouter.ai/api/v1",
        api_key="sk-or-v1-test-key",
        model_name="meta-llama/llama-3.3-70b-instruct:free",
        provider_type="openrouter",
        is_active=True,
    )

    assert provider.provider_id == "cloud_llm"
    assert provider.endpoint_url == "https://openrouter.ai/api/v1"
    assert provider.api_key == "sk-or-v1-test-key"

    # Verify persistence
    cfg = llm_registry.get_cloud_config()
    assert cfg["provider_type"] == "openrouter"
    assert cfg["api_key"] == "sk-or-v1-test-key"
    assert cfg["model_name"] == "meta-llama/llama-3.3-70b-instruct:free"
    assert cfg["is_active"] is True


def test_cloud_llm_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from engine.api.app import app

    test_cfg_path = tmp_path / "cloud_llm_config.json"
    monkeypatch.setattr(llm_registry, "_cloud_config_path", test_cfg_path)

    client = TestClient(app)

    # 1. GET cloud config defaults
    res = client.get("/api/system/llm/cloud-config")
    assert res.status_code == 200
    data = res.json()
    assert "provider_type" in data
    assert "masked_api_key" in data

    # 2. POST save cloud config
    save_payload = {
        "provider_type": "openrouter",
        "endpoint_url": "https://openrouter.ai/api/v1",
        "api_key": "sk-or-v1-secret-key-12345",
        "model_name": "meta-llama/llama-3.3-70b-instruct:free",
        "custom_models": ["meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free"],
        "is_active": True,
    }
    save_res = client.post("/api/system/llm/cloud-config", json=save_payload)
    assert save_res.status_code == 200
    save_data = save_res.json()
    assert save_data["status"] == "SAVED"
    assert save_data["has_api_key"] is True
    assert "••••" in save_data["masked_api_key"]

    # 3. GET all providers
    prov_res = client.get("/api/system/llm/providers/all")
    assert prov_res.status_code == 200
    prov_data = prov_res.json()
    assert len(prov_data["providers"]) >= 2
    ids = [p["id"] for p in prov_data["providers"]]
    assert "ollama" in ids
    assert "cloud_llm" in ids

