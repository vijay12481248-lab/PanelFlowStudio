"""
Unit tests for Centralized Global and Flow-Wise LLM Provider and Model Configuration.
"""
import pytest
from fastapi.testclient import TestClient
from engine.api.app import app
from engine.llm.registry import LLMRegistry
from engine.llm.providers.mock import MockLLMProvider
from engine.llm.providers.ollama import OllamaProvider
from engine.llm.providers.openai_compatible import OpenAICompatibleProvider


@pytest.fixture
def clean_registry(tmp_path):
    reg = LLMRegistry()
    reg._global_settings_path = tmp_path / "global_llm_settings.json"
    reg._cloud_config_path = tmp_path / "cloud_llm_config.json"

    # Register providers
    mock_prov = MockLLMProvider()
    reg.register(mock_prov)

    ollama_prov = OllamaProvider(
        endpoint_url="http://127.0.0.1:11434",
        text_model="qwen2.5:7b",
        vision_model="llama3.2-vision",
        narration_model="qwen2.5:7b",
    )
    reg.register(ollama_prov)

    cloud_prov = OpenAICompatibleProvider(
        endpoint_url="http://localhost:3001/v1",
        model_name="gemini-2.0-flash",
        provider_id="cloud_llm",
        display_name="FreeLLMAPI Gateway",
    )
    reg.register(cloud_prov)

    return reg


@pytest.mark.asyncio
async def test_global_settings_defaults_and_update(clean_registry):
    defaults = clean_registry.get_global_settings()
    assert defaults["global_default_provider"] == "ollama"
    assert "story_narration" in defaults["flow_overrides"]

    updated = clean_registry.update_global_settings(
        global_default_provider="freellmapi",
        global_default_model="gemini-2.0-flash",
        flow_overrides={
            "story_narration": {"provider_id": "groq", "model_name": "llama-3.3-70b-versatile"},
            "vision_inspection": {"provider_id": "ollama", "model_name": "llama3.2-vision"},
        }
    )

    assert updated["global_default_provider"] == "freellmapi"
    assert updated["global_default_model"] == "gemini-2.0-flash"
    assert updated["flow_overrides"]["story_narration"]["provider_id"] == "groq"
    assert updated["flow_overrides"]["vision_inspection"]["model_name"] == "llama3.2-vision"

    # Verify reloaded from disk
    reloaded = clean_registry.get_global_settings()
    assert reloaded["global_default_provider"] == "freellmapi"
    assert reloaded["flow_overrides"]["story_narration"]["model_name"] == "llama-3.3-70b-versatile"


@pytest.mark.asyncio
async def test_resolve_provider_and_model_hierarchy(clean_registry, monkeypatch):
    monkeypatch.setenv("PANELFLOW_ALLOW_MOCK_LLM", "true")

    # Set up global settings
    clean_registry.update_global_settings(
        global_default_provider="ollama",
        global_default_model="qwen2.5:7b",
        flow_overrides={
            "story_narration": {"provider_id": "freellmapi", "model_name": "gemini-2.0-flash"},
            "character_analysis": {"provider_id": "global", "model_name": ""},
        }
    )

    # 1. Flow override resolution (story_narration -> freellmapi, which maps to cloud_llm)
    prov, model = await clean_registry.resolve_provider_and_model(flow_id="story_narration")
    assert prov.provider_id == "cloud_llm"
    assert model == "gemini-2.0-flash"

    # 2. Global default resolution (character_analysis has provider_id="global" -> falls back to global default ollama)
    prov, model = await clean_registry.resolve_provider_and_model(flow_id="character_analysis")
    assert prov.provider_id == "ollama"
    assert model == "qwen2.5:7b"

    # 3. Explicit request override takes highest priority
    prov, model = await clean_registry.resolve_provider_and_model(
        flow_id="story_narration",
        requested_provider_id="mock_llm",
        requested_model="mock-custom-v1",
    )
    assert prov.provider_id == "mock_llm"
    assert model == "mock-custom-v1"


def test_global_llm_settings_rest_api(monkeypatch):
    client = TestClient(app)

    # Test GET
    res = client.get("/api/system/llm/global-settings")
    assert res.status_code == 200
    data = res.json()
    assert "global_default_provider" in data
    assert "flow_overrides" in data
    assert "providers" in data
    assert len(data["providers"]) >= 3

    # Test POST
    payload = {
        "global_default_provider": "freellmapi",
        "global_default_model": "gemini-2.0-flash",
        "flow_overrides": {
            "story_narration": {
                "provider_id": "freellmapi",
                "model_name": "gemini-2.0-flash",
            },
            "story_script": {
                "provider_id": "global",
                "model_name": "",
            }
        }
    }
    save_res = client.post("/api/system/llm/global-settings", json=payload)
    assert save_res.status_code == 200
    saved_data = save_res.json()
    assert saved_data["status"] == "SAVED"
    assert saved_data["global_default_provider"] == "freellmapi"
    assert saved_data["flow_overrides"]["story_narration"]["provider_id"] == "freellmapi"


def test_cloud_connection_test_verifies_selected_model(monkeypatch):
    async def fake_models(self):
        return ["gemini-test"]

    async def fake_generate(self, prompt, **kwargs):
        assert kwargs["model"] == "gemini-test"
        assert kwargs["max_tokens"] == 12
        return "PANELFLOW_OK"

    monkeypatch.setattr(OpenAICompatibleProvider, "list_available_models", fake_models)
    monkeypatch.setattr(OpenAICompatibleProvider, "generate_text", fake_generate)

    response = TestClient(app).post(
        "/api/system/llm/cloud-test",
        json={
            "endpoint_url": "http://localhost:3001/v1",
            "api_key": "test-key",
            "model_name": "gemini-test",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["connected"] is True
    assert result["model_verified"] is True
    assert result["response_preview"] == "PANELFLOW_OK"


def test_cloud_chat_uses_saved_active_provider(monkeypatch):
    from engine.llm.registry import llm_registry

    class FakeProvider:
        model_name = "auto"

        async def generate_text(self, prompt, **kwargs):
            assert prompt == "Explain this panel"
            assert kwargs["model"] == "auto"
            return "The hero enters the ruined hall."

    monkeypatch.setattr(llm_registry, "get_cloud_config", lambda: {
        "is_active": True,
        "provider_type": "freellmapi",
        "model_name": "auto",
    })
    monkeypatch.setattr(llm_registry, "get_cloud_provider", lambda: FakeProvider())

    response = TestClient(app).post(
        "/api/system/llm/cloud-chat",
        json={"prompt": "Explain this panel", "model_name": "auto"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "OK"
    assert result["provider_type"] == "freellmapi"
    assert result["model_name"] == "auto"
    assert result["response"] == "The hero enters the ruined hall."
