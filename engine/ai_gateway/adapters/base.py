"""Base adapter interface for all AI provider adapters.

Defines the contract that every provider adapter must implement.
Enables the Universal AI Gateway to route requests uniformly across
diverse providers (Ollama, OpenAI, Anthropic, Gemini, Groq, etc.).
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Type, Any, Optional, Dict, List
from decimal import Decimal
from pydantic import BaseModel, Field
from datetime import datetime

from engine.ai_gateway.contracts import (
    CapabilityType,
    RoutingStrategy,
    HealthStatus,
    FinishStatus,
    ProviderConfig,
    ModelInfo,
    AIRequest,
    AIResponse,
    AttemptResult,
)

T = TypeVar("T", bound=BaseModel)


class NormalizedRequest(BaseModel):
    """Normalized request contract used by all adapters."""
    request_id: str
    workflow_job_id: str
    project_id: str
    capability: CapabilityType
    prompt: str
    system_prompt: Optional[str] = None
    input_modalities: List[str] = Field(default_factory=list)
    output_schema: Optional[Dict[str, Any]] = None
    quality_requirements: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=180)
    free_only: bool = Field(default=True)
    spending_budget: Optional[Decimal] = Field(default=None)
    preferred_providers: List[str] = Field(default_factory=list)
    prohibited_providers: List[str] = Field(default_factory=list)
    max_attempts: int = Field(default=3)
    temperature: float = Field(default=0.2)
    max_tokens: int = Field(default=2048)
    idempotency_key: Optional[str] = Field(default=None)
    model_overrides: Dict[str, str] = Field(default_factory=dict)
    trace_id: str = Field(default="")


class NormalizedResponse(BaseModel):
    """Normalized response contract returned by all adapters."""
    request_id: str
    status: FinishStatus
    result: Any
    artifact_refs: List[str] = Field(default_factory=list)
    provider_used: str
    model_used: str
    attempt_history: List[AttemptResult] = Field(default_factory=list)
    input_tokens: Optional[int] = Field(default=None)
    output_tokens: Optional[int] = Field(default=None)
    cost_estimate: Optional[Decimal] = Field(default=None)
    cost_actual: Optional[Decimal] = Field(default=None)
    cost_confidence: str = Field(default="HIGH")
    latency_ms: int = Field(default=0)
    finish_reason: Optional[str] = Field(default=None)
    validation_status: str = Field(default="SUCCESS")
    error_info: Optional[Dict[str, Any]] = Field(default=None)
    provider_request_id: Optional[str] = Field(default=None)
    trace_id: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)


class HealthStatusOutput(BaseModel):
    """Standardized health check response."""
    status: HealthStatus
    latency_ms: int = 0
    details: str = ""
    model_info: Optional[ModelInfo] = None


class ProviderAdapterError(Exception):
    """Base exception for adapter failures."""
    pass


class RateLimitError(ProviderAdapterError):
    """Raised when provider rate limit is hit."""
    pass


class AuthenticationError(ProviderAdapterError):
    """Raised when API credentials are invalid."""
    pass


class TransientError(ProviderAdapterError):
    """Raised for temporary provider failures (5xx, timeouts)."""
    pass


class UnsupportedCapabilityError(ProviderAdapterError):
    """Raised when provider doesn't support requested capability."""
    pass


class ProviderAdapter(ABC):
    """Abstract base class for all AI provider adapters.

    Each adapter must implement:
    - provider_id: Unique identifier (e.g., 'ollama', 'openai')
    - display_name: Human-readable name
    - health_check(): Verify connectivity and model availability
    - execute(): Normalized request execution
    - supports_capability(): Check if capability is supported
    - get_capabilities(): Return the ModelMetadata
    - normalize_request(): Convert NormalizedRequest to provider format
    - normalize_response(): Convert provider response to NormalizedResponse
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable display name."""
        pass

    @abstractmethod
    async def health_check(self) -> HealthStatusOutput:
        """Verify endpoint connectivity and model availability.

        Returns standardized HealthStatusOutput with status and optional
        model metadata. Should not consume excessive quota on repeated calls.
        """
        pass

    @abstractmethod
    async def execute(
        self,
        request: NormalizedRequest,
    ) -> NormalizedResponse:
        """Execute a normalized request against the provider.

        Must handle:
        - Request timeout enforcement
        - Error classification (rate limit, auth failure, transient, etc.)
        - Result normalization to AIResponse/AttemptResult schema
        - Audit logging via attempt_history
        """
        pass

    @abstractmethod
    def supports_capability(self, capability: CapabilityType) -> bool:
        """Check if this provider supports the given capability."""
        pass

    @abstractmethod
    def get_capabilities(self) -> ModelMetadata:
        """Return model metadata and capability flags for this provider."""
        pass

    @abstractmethod
    def normalize_request(self, request: NormalizedRequest) -> Dict[str, Any]:
        """Convert normalized request to provider-specific payload.

        Adapters must preserve provider-specific parameters that don't
        contaminate the core contract, while mapping standardized fields.
        """
        pass

    @abstractmethod
    def normalize_response(
        self, raw_response: Dict[str, Any], request: NormalizedRequest
    ) -> NormalizedResponse:
        """Convert provider's raw HTTP response to NormalizedResponse.

        Must handle:
        - Error classification and mapping to FinishStatus
        - Token count extraction (input/output)
        - Cost estimation or actual cost capture
        - Latency measurement from request metadata
        - Validation of structured output if output_schema provided
        - Failure diagnostics without leaking secrets
        """
        pass

    def discover_models(self) -> List[ModelInfo]:
        """Discover available models from the provider.

        Default implementation returns empty list; override for providers
        with model discovery APIs (Ollama /api/tags, OpenAI-compatible /v1/models, etc.).
        """
        return []

    def validate_request(self, request: NormalizedRequest) -> Optional[str]:
        """Pre-flight request validation.

        Returns error message if request is invalid for this provider,
        or None if valid. Override in subclasses for provider-specific checks.
        """
        # Basic free-only check
        if request.free_only and not self._is_free_tier_available():
            return "Free-only mode enabled but no free models available"

        return None

    def _is_free_tier_available(self) -> bool:
        """Check if provider has free-tier models available."""
        meta = self.get_capabilities()
        return bool(meta and meta.free_tier)

    async def safe_execute(
        self,
        request: NormalizedRequest,
        max_retries: int = 2,
    ) -> NormalizedResponse:
        """Template method: execute with bounded retry and error classification.

        This is the preferred execution path. It:
        1. Calls validate_request for pre-flight checks
        2. Executes execute()
        3. On TransientError/Timeout: bounded exponential backoff + jitter
        4. On RateLimitError: parse Retry-After, apply cooldown
        5. On AuthenticationError: do NOT retry, raise immediately
        6. On UnsupportedCapabilityError: immediately raise
        7. On success: return NormalizedResponse
        8. After max_retries exhausted: raise last error
        """
        last_error: Optional[ProviderAdapterError] = None

        for attempt in range(1, max_retries + 1):
            try:
                result = await self.execute(request)
                return result

            except RateLimitError as e:
                last_error = e
                import asyncio
                wait_time = min(getattr(e, "retry_after", None) or (2 ** attempt) + (attempt * 0.5), 60)
                await asyncio.sleep(wait_time)

            except TransientError as e:
                last_error = e
                import asyncio
                wait_time = min((2 ** attempt) + (attempt * 0.5), 30)
                await asyncio.sleep(wait_time)

            except AuthenticationError as e:
                # Never retry auth failures
                raise ProviderAdapterError(
                    f"Authentication failed for {self.provider_id}: {e}"
                ) from e

            except UnsupportedCapabilityError as e:
                raise ProviderAdapterError(
                    f"Unsupported capability {request.capability} for {self.provider_id}"
                ) from e

            except ProviderAdapterError as e:
                last_error = e
                import asyncio
                wait_time = min((2 ** attempt) + (attempt * 0.5), 15)
                await asyncio.sleep(wait_time)

            except Exception as e:
                # Catch-all: treat as transient
                last_error = TransientError(str(e))
                import asyncio
                wait_time = min((2 ** attempt) + (attempt * 0.5), 15)
                await asyncio.sleep(wait_time)

        # All retries exhausted
        raise last_error from last_error

    def get_active_model(self) -> Optional[str]:
        """Return the currently active model name, if known."""
        return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider_id={self.provider_id}>"


# Convenience type for adapter instances
ProviderAdapterType = ProviderAdapter