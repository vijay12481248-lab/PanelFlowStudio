import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
from engine.config.settings import settings
from engine.llm.providers.base import LLMProvider
from engine.llm.providers.mock import MockLLMProvider
from engine.llm.providers.ollama import OllamaProvider
from engine.llm.providers.openai_compatible import OpenAICompatibleProvider, LMStudioProvider

logger = logging.getLogger("panelflow.llm.registry")

DEFAULT_FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "deepseek/deepseek-r1:free",
    "qwen/qwen-2.5-vl-72b-instruct:free",
    "google/gemini-2.0-pro-exp-02-05:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
]

class LLMRegistry:
    """Central registry of LLM providers for PanelFlow story understanding."""

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._cloud_config_path = settings.app_data_dir / "config" / "cloud_llm_config.json"
        self._global_settings_path = settings.app_data_dir / "config" / "global_llm_settings.json"

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
            if pid in ("cloud_llm", "openrouter", "groq", "openai_compatible") and "cloud_llm" in self._providers:
                cp = self._providers["cloud_llm"]
                if await cp.health_check():
                    return cp

            if pid in self._providers:
                p = self._providers[pid]
                if pid == "mock_llm":
                    return p
                if await p.health_check():
                    return p

        # Probe real local/compatible/cloud providers automatically.
        for pid in ["cloud_llm", "ollama", "lmstudio", "openai_compatible"]:
            if pid in self._providers:
                p = self._providers[pid]
                if await p.health_check():
                    return p

        allow_mock = os.environ.get("PANELFLOW_ALLOW_MOCK_LLM", "").lower() in ("1", "true", "yes")
        if allow_mock and "mock_llm" in self._providers:
            return self._providers["mock_llm"]
        raise RuntimeError("No healthy real LLM provider is configured. Enable Ollama/compatible/cloud provider or explicitly set PANELFLOW_ALLOW_MOCK_LLM for tests.")

    def get_ollama_provider(self) -> OllamaProvider:
        p = self._providers.get("ollama")
        if isinstance(p, OllamaProvider):
            return p
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

    def get_cloud_config(self) -> dict:
        """Returns the persisted or default Cloud LLM configuration."""
        defaults = {
            "provider_type": "openrouter",
            "endpoint_url": "https://openrouter.ai/api/v1",
            "api_key": "",
            "model_name": "meta-llama/llama-3.3-70b-instruct:free",
            "custom_models": list(DEFAULT_FREE_MODELS),
            "is_active": False,
        }
        try:
            if self._cloud_config_path.exists():
                saved = json.loads(self._cloud_config_path.read_text(encoding="utf-8"))
                defaults.update(saved)
        except Exception as e:
            logger.warning(f"Failed to read cloud LLM config: {e}")
        return defaults

    def get_global_settings(self) -> dict:
        """Returns the centralized global LLM settings and flow overrides."""
        defaults = {
            "global_default_provider": "ollama",
            "global_default_model": "qwen3.5:9b",
            "flow_overrides": {
                "story_narration": {"provider_id": "global", "model_name": ""},
                "story_script": {"provider_id": "global", "model_name": ""},
                "character_analysis": {"provider_id": "global", "model_name": ""},
                "vision_inspection": {"provider_id": "global", "model_name": ""},
            },
        }
        try:
            if self._global_settings_path.exists():
                saved = json.loads(self._global_settings_path.read_text(encoding="utf-8"))
                defaults.update(saved)
                if "flow_overrides" in saved and isinstance(saved["flow_overrides"], dict):
                    merged_flows = dict(defaults["flow_overrides"])
                    merged_flows.update(saved["flow_overrides"])
                    defaults["flow_overrides"] = merged_flows
        except Exception as e:
            logger.warning(f"Failed to read global LLM settings: {e}")
        return defaults

    def update_global_settings(
        self,
        global_default_provider: str,
        global_default_model: str,
        flow_overrides: Optional[dict] = None,
    ) -> dict:
        """Updates and persists centralized global LLM defaults and flow-level routing."""
        current = self.get_global_settings()
        current["global_default_provider"] = global_default_provider
        current["global_default_model"] = global_default_model
        if flow_overrides is not None:
            current_flows = current.get("flow_overrides", {})
            current_flows.update(flow_overrides)
            current["flow_overrides"] = current_flows

        try:
            self._global_settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._global_settings_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to persist global LLM settings: {e}")

        return current

    async def resolve_provider_and_model(
        self,
        flow_id: Optional[str] = None,
        requested_provider_id: Optional[str] = None,
        requested_model: Optional[str] = None,
    ) -> tuple[LLMProvider, str]:
        """
        Resolves the effective provider and model according to the hierarchy:
        1. Explicit user request (if requested_provider_id != 'global' and requested_provider_id is set)
        2. Flow override (if flow_id is set and has an override != 'global')
        3. Global default provider & model
        4. Healthy fallback
        """
        global_cfg = self.get_global_settings()
        flow_overrides = global_cfg.get("flow_overrides", {})

        effective_provider_id = "global"
        effective_model = ""

        # 1. User explicit request
        if requested_provider_id and requested_provider_id != "global":
            effective_provider_id = requested_provider_id
            effective_model = requested_model or ""
        # 2. Flow override
        elif flow_id and flow_id in flow_overrides:
            fo = flow_overrides[flow_id]
            if fo.get("provider_id") and fo.get("provider_id") != "global":
                effective_provider_id = fo.get("provider_id")
                effective_model = fo.get("model_name") or ""

        # 3. Global defaults
        if effective_provider_id == "global":
            effective_provider_id = global_cfg.get("global_default_provider", "ollama")
            if not effective_model:
                effective_model = global_cfg.get("global_default_model", "")

        alias_map = {
            "freellmapi": "cloud_llm",
            "openrouter": "cloud_llm",
            "groq": "cloud_llm",
            "custom": "cloud_llm",
        }
        resolved_pid = alias_map.get(effective_provider_id, effective_provider_id)

        provider = None
        if resolved_pid in self._providers:
            provider = self._providers[resolved_pid]
        elif resolved_pid == "cloud_llm":
            provider = self.get_cloud_provider()
        elif resolved_pid == "ollama":
            provider = self.get_ollama_provider()

        if not provider:
            try:
                provider = await self.get_active_provider(resolved_pid)
            except Exception:
                allow_mock = os.environ.get("PANELFLOW_ALLOW_MOCK_LLM", "").lower() in ("1", "true", "yes")
                if allow_mock and "mock_llm" in self._providers:
                    provider = self._providers["mock_llm"]
                else:
                    raise

        if not effective_model:
            if hasattr(provider, "narration_model") and provider.narration_model:
                effective_model = provider.narration_model
            elif hasattr(provider, "model_name") and provider.model_name:
                effective_model = provider.model_name
            elif hasattr(provider, "text_model") and provider.text_model:
                effective_model = provider.text_model
            else:
                effective_model = "default"

        return provider, effective_model

    def get_cloud_provider(self) -> Optional[OpenAICompatibleProvider]:
        p = self._providers.get("cloud_llm")
        if isinstance(p, OpenAICompatibleProvider):
            return p
        return None

    def configure_cloud_provider(
        self,
        endpoint_url: str = "https://openrouter.ai/api/v1",
        api_key: str = "",
        model_name: str = "meta-llama/llama-3.3-70b-instruct:free",
        provider_type: str = "openrouter",
        custom_models: Optional[List[str]] = None,
        is_active: bool = True,
    ) -> OpenAICompatibleProvider:
        """Configures, persists, and registers a Cloud/Free OpenAI-compatible LLM provider."""
        display_name = f"Cloud LLM ({provider_type.capitalize()}: {model_name})"
        provider = OpenAICompatibleProvider(
            endpoint_url=endpoint_url,
            model_name=model_name,
            api_key=api_key,
            provider_id="cloud_llm",
            display_name=display_name,
        )
        self.register(provider)
        if is_active:
            self._providers["openai_compatible"] = provider

        try:
            self._cloud_config_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_to_save = {
                "provider_type": provider_type,
                "endpoint_url": endpoint_url,
                "api_key": api_key,
                "model_name": model_name,
                "custom_models": custom_models or list(DEFAULT_FREE_MODELS),
                "is_active": is_active,
            }
            self._cloud_config_path.write_text(json.dumps(cfg_to_save, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to persist cloud LLM config: {e}")

        return provider

    def load_persisted_cloud_provider(self) -> None:
        """Loads and registers cloud provider if configured."""
        try:
            if self._cloud_config_path.exists():
                cfg = json.loads(self._cloud_config_path.read_text(encoding="utf-8"))
                endpoint = cfg.get("endpoint_url", "https://openrouter.ai/api/v1")
                api_key = cfg.get("api_key", "")
                model = cfg.get("model_name", "meta-llama/llama-3.3-70b-instruct:free")
                ptype = cfg.get("provider_type", "openrouter")
                provider = OpenAICompatibleProvider(
                    endpoint_url=endpoint,
                    model_name=model,
                    api_key=api_key,
                    provider_id="cloud_llm",
                    display_name=f"Cloud LLM ({ptype.capitalize()}: {model})",
                )
                self.register(provider)
                if cfg.get("is_active", False):
                    self._providers["openai_compatible"] = provider
        except Exception as e:
            logger.debug(f"Could not load persisted cloud LLM config: {e}")

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

    registry.load_persisted_cloud_provider()

    return registry

llm_registry = get_default_llm_registry()
