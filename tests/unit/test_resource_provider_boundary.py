import httpx
import pytest

from engine.llm.providers.ollama import OllamaEndpointAuthorization
from engine.system import resources


@pytest.mark.asyncio
async def test_telemetry_rejects_unvalidated_endpoint_without_network(monkeypatch):
    calls = []

    def no_client(*args, **kwargs):
        calls.append(kwargs)
        raise AssertionError("unvalidated endpoint reached HTTP client")

    monkeypatch.setattr(resources.httpx, "AsyncClient", no_client)
    result = await resources.SystemResourceManager().get_ollama_runtime("http://169.254.169.254")
    assert result["online"] is False
    assert calls == []


@pytest.mark.asyncio
async def test_benchmark_rejects_unvalidated_endpoint_without_network(monkeypatch):
    def no_client(*args, **kwargs):
        raise AssertionError("unvalidated endpoint reached HTTP client")

    monkeypatch.setattr(resources.httpx, "AsyncClient", no_client)
    with pytest.raises(ValueError, match="Ollama endpoint"):
        await resources.SystemResourceManager().benchmark_concurrency("http://127.0.0.1:11434@169.254.169.254")


@pytest.mark.asyncio
async def test_telemetry_rejects_unapproved_public_ip_without_network(monkeypatch):
    calls = []

    def no_client(*args, **kwargs):
        calls.append(kwargs)
        raise AssertionError("unapproved endpoint reached HTTP client")

    monkeypatch.setattr(resources.httpx, "AsyncClient", no_client)
    result = await resources.SystemResourceManager().get_ollama_runtime(
        "https://8.8.8.8:11434",
        authorization=OllamaEndpointAuthorization.create(set()),
    )
    assert result["online"] is False
    assert calls == []


@pytest.mark.asyncio
async def test_telemetry_accepts_approved_public_ip(monkeypatch):
    seen = []
    original_client = httpx.AsyncClient

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"models": []})

    def make_client(*args, **kwargs):
        return original_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(resources.httpx, "AsyncClient", make_client)
    authorization = OllamaEndpointAuthorization.create({"8.8.8.8"})
    result = await resources.SystemResourceManager().get_ollama_runtime(
        "https://8.8.8.8:11434",
        authorization=authorization,
    )
    assert result["online"] is True
    assert seen == ["https://8.8.8.8:11434/api/ps"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["telemetry", "benchmark"])
async def test_resource_requests_never_follow_provider_redirects(monkeypatch, operation):
    seen = []
    original_client = httpx.AsyncClient

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    def make_client(*args, **kwargs):
        # Simulate a redirect-following client default to require an explicit policy.
        return original_client(*args, transport=httpx.MockTransport(handler), follow_redirects=kwargs.pop("follow_redirects", True), **kwargs)

    monkeypatch.setattr(resources.httpx, "AsyncClient", make_client)
    manager = resources.SystemResourceManager()
    if operation == "telemetry":
        assert (await manager.get_ollama_runtime())["online"] is False
    else:
        with pytest.raises(RuntimeError, match="HTTP 302"):
            await manager.benchmark_concurrency()
    assert seen == ["http://127.0.0.1:11434/api/ps" if operation == "telemetry" else "http://127.0.0.1:11434/api/generate"] * (1 if operation == "telemetry" else 1)
