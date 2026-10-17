import os
from typing import Dict, List
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
        """Returns the requested provider if healthy, or falls back to first available or mock."""
        if preferred_id:
            pid = "mock_llm" if preferred_id in ("mock", "mock_llm") else preferred_id
            if pid in self._providers:
                p = self._providers[pid]
                if await p.health_check():
                    return p

        # Check real local providers if explicitly enabled via environment
        if os.environ.get("USE_REAL_LLM", "").lower() in ("1", "true", "yes"):
            for pid in ["ollama", "lmstudio", "openai_compatible"]:
                if pid in self._providers:
                    p = self._providers[pid]
                    if await p.health_check():
                        return p

        # Fallback to deterministic mock
        return self._providers.get("mock_llm", list(self._providers.values())[0])

def get_default_llm_registry() -> LLMRegistry:
    registry = LLMRegistry()
    registry.register(MockLLMProvider())

    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_text = os.environ.get("OLLAMA_TEXT_MODEL", "qwen3.5:9b")
    ollama_vision = os.environ.get("OLLAMA_VISION_MODEL", "qwen3.5:9b")
    ollama_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
    registry.register(OllamaProvider(endpoint_url=ollama_url, text_model=ollama_text, vision_model=ollama_vision, num_ctx=ollama_ctx))

    lmstudio_url = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234/v1")
    registry.register(LMStudioProvider(endpoint_url=lmstudio_url))

    openai_compat_url = os.environ.get("OPENAI_COMPAT_URL", "http://127.0.0.1:8000/v1")
    registry.register(OpenAICompatibleProvider(endpoint_url=openai_compat_url))

    return registry

llm_registry = get_default_llm_registry()
