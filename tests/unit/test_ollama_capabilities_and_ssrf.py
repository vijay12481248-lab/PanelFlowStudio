import pytest
from unittest.mock import patch, MagicMock
from engine.llm.providers.ollama import OllamaProvider, validate_ollama_endpoint


def test_validate_ollama_endpoint_localhost_valid():
    """Localhost endpoints must be accepted without is_remote."""
    valid, msg = validate_ollama_endpoint("http://127.0.0.1:11434")
    assert valid is True
    assert msg == ""

    valid2, msg2 = validate_ollama_endpoint("http://localhost:11434")
    assert valid2 is True

    valid3, msg3 = validate_ollama_endpoint("http://[::1]:11434")
    assert valid3 is True


def test_validate_ollama_endpoint_ssrf_rejections():
    """Cloud metadata, link-local, multicast, and invalid schemes must be rejected."""
    # Cloud metadata service (169.254.x.x)
    valid, msg = validate_ollama_endpoint("http://169.254.169.254/latest/meta-data/", is_remote=True)
    assert valid is False
    assert "link-local" in msg.lower() or "metadata" in msg.lower()

    # Multicast
    valid, msg = validate_ollama_endpoint("http://224.0.0.1:11434", is_remote=True)
    assert valid is False
    assert "multicast" in msg.lower()

    # Loopback or unroutable when is_remote=True
    valid, msg = validate_ollama_endpoint("http://127.0.0.1:11434", is_remote=True)
    assert valid is False
    assert "loopback" in msg.lower()

    # Invalid scheme
    valid, msg = validate_ollama_endpoint("file:///etc/passwd")
    assert valid is False
    assert "unsupported scheme" in msg.lower()

    valid, msg = validate_ollama_endpoint("ftp://example.com:11434")
    assert valid is False
    assert "unsupported scheme" in msg.lower()


def test_validate_ollama_endpoint_remote_flag():
    """Remote non-loopback addresses must be rejected unless is_remote=True."""
    # Remote rejected without is_remote
    valid, msg = validate_ollama_endpoint("http://192.168.1.100:11434", is_remote=False)
    assert valid is False
    assert "local endpoint must be localhost" in msg.lower()

    # Allowed when is_remote=True
    valid, msg = validate_ollama_endpoint("http://192.168.1.100:11434", is_remote=True)
    assert valid is True
    assert msg == ""


def test_ollama_auth_headers():
    """Verify that bearer token is properly injected into HTTP headers."""
    provider_unauth = OllamaProvider(endpoint_url="http://127.0.0.1:11434")
    assert "Authorization" not in provider_unauth._get_headers()

    provider_auth = OllamaProvider(
        endpoint_url="https://ollama.mycorp.internal:11434",
        auth_token="secret-ollama-token-12345",
        is_remote=True,
    )
    headers = provider_auth._get_headers()
    assert headers.get("Authorization") == "Bearer secret-ollama-token-12345"


@pytest.mark.asyncio
async def test_ollama_capability_inspection():
    """Verify /api/show capability discovery parses vision, tools, and thinking correctly."""
    provider = OllamaProvider()

    # Mock response from Ollama /api/show for a vision model
    mock_vision_show = {
        "capabilities": ["completion", "vision", "tools"],
        "details": {
            "family": "qwen2.5",
            "parameter_size": "9B",
            "quantization_level": "Q4_K_M",
            "format": "gguf",
        },
        "model_info": {
            "general.architecture": "qwen2",
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_vision_show

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        cap = await provider.inspect_model_capabilities("qwen3.5:9b")
        assert cap["name"] == "qwen3.5:9b"
        assert cap["supports_vision"] is True
        assert cap["supports_tools"] is True
        assert cap["supports_thinking"] is False
        assert cap["family"] == "qwen2.5"
        assert cap["parameter_size"] == "9B"


def test_ollama_recommend_models():
    """Verify recommendation heuristic assigns vision, reasoning, and narration roles."""
    provider = OllamaProvider()

    available_models = [
        {
            "name": "qwen3.5:9b",
            "supports_vision": True,
            "supports_tools": True,
            "supports_thinking": False,
            "family": "qwen2.5",
            "parameter_size": "9B",
            "quantization_level": "Q4_K_M",
            "format": "gguf",
            "capabilities": ["completion", "vision"],
        },
        {
            "name": "qwen3-coder:30b",
            "supports_vision": False,
            "supports_tools": True,
            "supports_thinking": True,
            "family": "qwen2.5",
            "parameter_size": "30B",
            "quantization_level": "Q4_K_M",
            "format": "gguf",
            "capabilities": ["completion", "thinking"],
        },
        {
            "name": "llama3.2:3b",
            "supports_vision": False,
            "supports_tools": True,
            "supports_thinking": False,
            "family": "llama",
            "parameter_size": "3B",
            "quantization_level": "Q4_K_M",
            "format": "gguf",
            "capabilities": ["completion"],
        },
    ]

    recs = provider.recommend_models(available_models)
    assert recs["vision_model"] == "qwen3.5:9b"
    assert recs["reasoning_model"] in ["qwen3-coder:30b", "qwen3.5:9b"]
    assert recs["narration_model"] != ""
