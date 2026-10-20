import os
from typing import Dict, List
from urllib.parse import urlparse
from engine.llm.providers.base import LLMProvider
from engine.llm.providers.mock import MockLLMProvider
from engine.llm.providers.ollama import OllamaProvider
from engine.llm.providers.openai_compatible import OpenAICompatibleProvider, LMStudioProvider

class LLMRegistry:
    """Central registry of LLM providers for PanelFlow story understanding."""

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get_provider(self, provider_id: str) -> LLMProvider:
        if provider_id not in self._providers:
            raise KeyError(f"LLM Provider '{provider_id}' not found in registry.")
        return self._providers[provider_id]

    def list_providers(self) -> List[dict]:
        results = []
        for pid, p in self._providers.items():
            results.append({
                "provider_id": pid,
                "display_name": p.display_name,
                "context_window": p.context_window(),
                "metadata": p.model_metadata().model_dump(),
            })
        return results

    async def get_active_provider(self, preferred_id: str | None = None) -> LLMProvider:
        """Resolve a healthy provider without silently fabricating production content."""
        if preferred_id:
            pid = "mock_llm" if preferred_id in ("mock", "mock_llm") else preferred_id
            if pid in self._providers:
                p = self._providers[pid]
                if pid == "mock_llm":
                    # Explicit mock selection remains available for tests and fixtures.
                    return p
                if await p.health_check():
                    return p

        # Probe real local/compatible providers automatically. Production should not
        # require a hidden USE_REAL_LLM switch just to avoid mock content.
        for pid in ["ollama", "lmstudio", "openai_compatible"]:
            if pid in self._providers:
                p = self._providers[pid]
                if await p.health_check():
                    return p

        # Mock fallback is opt-in only; otherwise fail closed so generated story
        # content cannot be mistaken for analysis of real source material.
        allow_mock = os.environ.get("PANELFLOW_ALLOW_MOCK_LLM", "").lower() in ("1", "true", "yes")
        if allow_mock and "mock_llm" in self._providers:
            return self._providers["mock_llm"]
        raise RuntimeError("No healthy real LLM provider is configured. Enable Ollama/compatible provider or explicitly set PANELFLOW_ALLOW_MOCK_LLM for tests.")

    def get_ollama_provider(self) -> OllamaProvider:
        p = self._providers.get("ollama")
        if isinstance(p, OllamaProvider):
            return p
        # Default fallback
        provider = OllamaProvider()
        self.register(provider)
        return provider

    def configure_ollama(
        self,
        endpoint_url: str = "http://127.0.0.1:11434",
        is_remote: bool = False,
        auth_token: str = "",
        vision_model: str = "qwen3.5:9b",
        reasoning_model: str = "qwen3.5:9b",
        narration_model: str = "qwen3.5:9b",
        num_ctx: int = 32768,
        concurrency_mode: str = "MANUAL",
        max_gpu_concurrency: int = 1,
    ) -> OllamaProvider:
        provider = OllamaProvider(
            endpoint_url=endpoint_url,
            is_remote=is_remote,
            auth_token=auth_token,
            text_model=narration_model,
            vision_model=vision_model,
            reasoning_model=reasoning_model,
            narration_model=narration_model,
            num_ctx=num_ctx,
            concurrency_mode=concurrency_mode,
            max_gpu_concurrency=max_gpu_concurrency,
        )
        self.register(provider)
        return provider

def get_default_llm_registry() -> LLMRegistry:
    registry = LLMRegistry()
    registry.register(MockLLMProvider())

    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_text = os.environ.get("OLLAMA_TEXT_MODEL", "qwen3.5:9b")
    ollama_vision = os.environ.get("OLLAMA_VISION_MODEL", "qwen3.5:9b")
    ollama_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "32768"))
    ollama_host = (urlparse(ollama_url).hostname or "").lower()
    ollama_is_remote = ollama_host not in {"localhost", "127.0.0.1", "::1"}
    registry.register(OllamaProvider(endpoint_url=ollama_url, is_remote=ollama_is_remote, text_model=ollama_text, vision_model=ollama_vision, num_ctx=ollama_ctx))

    lmstudio_url = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234/v1")
    registry.register(LMStudioProvider(endpoint_url=lmstudio_url))

    openai_compat_url = os.environ.get("OPENAI_COMPAT_URL", "http://127.0.0.1:8000/v1")
    registry.register(OpenAICompatibleProvider(endpoint_url=openai_compat_url))

    return registry

llm_registry = get_default_llm_registry()

