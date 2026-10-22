"""Adapter factory for the Universal AI Gateway.

Manages provider adapter instantiation, registration, and discovery.
Enables the gateway to dynamically route requests to the appropriate
provider adapter based on capability, availability, and policy.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Type

from engine.ai_gateway.adapters.base import ProviderAdapter, NormalizedRequest, NormalizedResponse, CapabilityType
from engine.ai_gateway.adapters.ollama_adapter import OllamaAdapter
from engine.ai_gateway.adapters.openai_adapter import OpenAIAdapter

# Import other adapters when available
try:
    from engine.ai_gateway.adapters.anthropic_adapter import AnthropicAdapter
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from engine.ai_gateway.adapters.gemini_adapter import GeminiAdapter
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from engine.ai_gateway.adapters.groq_adapter import GroqAdapter
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

try:
    from engine.ai_gateway.adapters.openrouter_adapter import OpenRouterAdapter
    HAS_OPENROUTER = True
except ImportError:
    HAS_OPENROUTER = False


class AdapterFactory:
    """Factory for creating and managing ProviderAdapter instances.

    Responsibilities:
    - Register adapter classes by provider_id
    - Instantiate adapters from configuration
    - Cache adapter instances
    - Provide adapter lookup by capability
    - Track adapter health and status
    """

    def __init__(self):
        self._adapter_classes: Dict[str, Type[ProviderAdapter]] = {}
        self._instances: Dict[str, ProviderAdapter] = {}
        self._init_adapter_classes()

    def _init_adapter_classes(self) -> None:
        """Register built-in adapter classes."""
        # Core adapters always available
        self.register("ollama", OllamaAdapter)
        self.register("openai", OpenAIAdapter)

        # Conditional adapters (available if installed/configured)
        if HAS_ANTHROPIC:
            self.register("anthropic", AnthropicAdapter)
        if HAS_GEMINI:
            self.register("gemini", GeminiAdapter)
        if HAS_GROQ:
            self.register("groq", GroqAdapter)
        if HAS_OPENROUTER:
            self.register("openrouter", OpenRouterAdapter)

    def register(self, provider_id: str, adapter_class: Type[ProviderAdapter]) -> None:
        """Register an adapter class for a given provider."""
        self._adapter_classes[provider_id] = adapter_class
        # Clear cached instance if re-registering
        if provider_id in self._instances:
            del self._instances[provider_id]

    def get_adapter_class(self, provider_id: str) -> Optional[Type[ProviderAdapter]]:
        """Get the adapter class for a given provider."""
        return self._adapter_classes.get(provider_id)

    def get_instance(self, provider_id: str, **kwargs) -> Optional[ProviderAdapter]:
        """Get or create an adapter instance for the given provider.

        Args:
            provider_id: The provider identifier (e.g., 'ollama', 'openai')
            **kwargs: Additional arguments to pass to the adapter constructor

        Returns:
            Adapter instance or None if provider not configured
        """
        if provider_id not in self._instances:
            adapter_class = self._adapter_classes.get(provider_id)
            if adapter_class is None:
                logger.warning(f"Adapter class not registered for provider: {provider_id}")
                return None

            try:
                self._instances[provider_id] = adapter_class(**kwargs)
            except Exception as e:
                logger.error(f"Failed to instantiate adapter for {provider_id}: {e}")
                del self._instances[provider_id]
                return None

        return self._instances[provider_id]

    def list_providers(self) -> List[str]:
        """List all registered provider IDs."""
        return sorted(self._adapter_classes.keys())

    def has_provider(self, provider_id: str) -> bool:
        """Check if a provider is registered."""
        return provider_id in self._adapter_classes

    async def health_check_all(self) -> Dict[str, dict]:
        """Health check all registered adapters.

        Returns dict of provider_id -> health status info.
        """
        results: Dict[str, dict] = {}
        for provider_id in self._adapter_classes:
            adapter = self.get_instance(provider_id)
            if adapter:
                health = await adapter.health_check()
                results[provider_id] = {
                    "status": health.status.value,
                    "display_name": health.details,
                    "latency_ms": health.latency_ms,
                }
            else:
                results[provider_id] = {
                    "status": "not_configured",
                    "display_name": f"{provider_id} (not configured)",
                }
        return results

    async def check_capability(
        self, provider_id: str, capability: CapabilityType
    ) -> bool:
        """Check if a specific provider supports a capability."""
        adapter = self.get_instance(provider_id)
        if adapter:
            return adapter.supports_capability(capability)
        return False

    async def execute_request(
        self,
        provider_id: str,
        request: NormalizedRequest,
    ) -> NormalizedResponse:
        """Execute a request against a specific provider.

        Routes to the adapter's safe_execute method for proper
        error handling, retry, and circuit breaker behavior.
        """
        adapter = self.get_instance(provider_id)
        if adapter is None:
            from engine.ai_gateway.contracts import FinishStatus
            return NormalizedResponse(
                request_id=request.request_id,
                status=FinishStatus.FAILED,
                result=None,
                artifact_refs=[],
                provider_used=provider_id,
                model_used="unknown",
                attempt_history=[],
                latency_ms=0,
            )

        return await adapter.safe_execute(request)


# Global factory instance
adapter_factory = AdapterFactory()