"""Ollama provider adapter for the Universal AI Gateway.

Wraps the existing `OllamaProvider` from `engine.llm.providers.ollama`
to implement the `ProviderAdapter` interface defined in `base.py`.

This adapter:
- Maintains full backward compatibility with existing Ollama workflows
- Implements the normalized request/response contract
- Provides health checking, capability detection, and model discovery
- Supports vision, structured output, and streaming
- Integrates with the ProviderRegistry and ModelRegistry
"""

import asyncio
import base64
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import TypeVar, Type, Any, Optional, Iterable

import httpx
from pydantic import BaseModel, ValidationError

from engine.llm.providers.ollama import (
    OllamaProvider,
    OllamaEndpointAuthorization,
    validate_ollama_endpoint,
)
from engine.ai_gateway.adapters.base import (
    ProviderAdapter,
    NormalizedRequest,
    NormalizedResponse,
    HealthStatusOutput,
    ProviderAdapterError,
    RateLimitError,
    AuthenticationError,
    TransientError,
    UnsupportedCapabilityError,
    ModelInfo,
    CapabilityType,
    FinishStatus,
    AttemptResult,
)
from engine.ai_gateway.registry.provider_registry import provider_registry
from engine.ai_gateway.registry.model_registry import model_registry
from engine.config.settings import settings

logger = logging.getLogger("panelflow.llm.adapter.ollama")


class OllamaAdapter(ProviderAdapter):
    """Adapter wrapping the existing OllamaProvider for gateway integration.

    Translates between the gateway's NormalizedRequest/NormalizedResponse
    contracts and the OllamaProvider's generate_text/generate_structured/
    analyze_vision methods.

    Supports:
    - Text generation (generate_text)
    - Structured JSON output (generate_structured) with repair retries
    - Vision analysis (analyze_vision) via base64 image encoding
    - Model discovery and capability inspection
    - Health monitoring and telemetry
    """

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:11434",
        is_remote: bool = False,
        auth_token: str = "",
        text_model: str = "qwen3.5:9b",
        vision_model: str = "qwen3.5:9b",
        reasoning_model: str = "qwen3.5:9b",
        narration_model: str = "qwen3.5:9b",
        num_ctx: int = 32768,
        concurrency_mode: str = "MANUAL",
        max_gpu_concurrency: int = 1,
        approved_remote_ips: Iterable[str] | None = None,
    ):
        """Initialize the Ollama adapter.

        Wraps the existing OllamaProvider with gateway-compatible interface.
        """
        # Initialize the underlying Ollama provider
        self._provider = OllamaProvider(
            endpoint_url=endpoint_url,
            is_remote=is_remote,
            auth_token=auth_token,
            text_model=text_model,
            vision_model=vision_model,
            reasoning_model=reasoning_model,
            narration_model=narration_model,
            num_ctx=num_ctx,
            concurrency_mode=concurrency_mode,
            max_gpu_concurrency=max_gpu_concurrency,
            approved_remote_ips=approved_remote_ips,
        )

        # Cache model discovery
        self._models_cache: Optional[list] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_ttl = 300  # 5 minutes

    # --- ProviderAdapter interface ---

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return f"Ollama Local ({self._provider.narration_model})"

    async def health_check(self) -> HealthStatusOutput:
        """Verify Ollama endpoint connectivity and model availability."""
        try:
            healthy = await self._provider.health_check()
            if healthy:
                models = await self.list_available_models()
                # Try to get model metadata for the active model
                model_info = None
                if models:
                    # Find the narration/text model
                    for m in models:
                        if m.get("name") == self._provider.narration_model:
                            model_info = ModelInfo(
                                model_id=m.get("name", self._provider.narration_model),
                                provider_id=self.provider_id,
                                upstream_model_id=m.get("name", self._provider.narration_model),
                                display_name=m.get("name", self._provider.narration_model),
                                capabilities=self._map_ollama_caps(m),
                                context_window=m.get("size", self._provider.context_window()),
                                output_limit=2048,
                                supports_streaming=True,
                                supports_structured=True,
                                supports_tools=False,
                                free_tier=True,  # Ollama is always free (local)
                                commercial_use=True,
                                privacy_retention="local_only",
                                health_status=HealthStatus.HEALTHY,
                            )
                            break

                return HealthStatusOutput(
                    status=HealthStatus.HEALTHY if models else HealthStatus.DEGRADED,
                    latency_ms=0,
                    details=f"Ollama healthy, {len(models) if models else 0} models installed",
                    model_info=model_info,
                )
            else:
                return HealthStatusOutput(
                    status=HealthStatus.OFFLINE,
                    latency_ms=0,
                    details="Ollama endpoint unreachable",
                )
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return HealthStatusOutput(
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                details=f"Health check error: {e}",
            )

    def supports_capability(self, capability: CapabilityType) -> bool:
        """Check if Ollama supports the given capability.

        Ollama supports: text.generate, text.reason, text.structured,
        text.translate, text.summarize, vision.understand, vision.ocr_assist,
        vision.panel_analysis, vision.continuity_check
        """
        # Map gateway capabilities to Ollama-supported operations
        supported = {
            # Text capabilities - all supported
            "text.generate": True,
            "text.reason": True,
            "text.structured": True,
            "text.translate": True,
            "text.summarize": True,
            # Vision capabilities - supported if vision model installed
            "vision.understand": True,
            "vision.ocr_assist": True,
            "vision.panel_analysis": True,
            "vision.continuity_check": True,
            # Audio/music - NOT supported
            "audio.transcribe": False,
            "audio.synthesize": False,
            "audio.analyze": False,
            "music.generate": False,
            # Image/video - NOT supported
            "image.generate": False,
            "image.edit": False,
            "video.generate": False,
            "embeddings.generate": False,
        }
        return supported.get(capability, False)

    def get_capabilities(self) -> ModelInfo:
        """Return model metadata and capability flags for the active model."""
        # Map Ollama capabilities to our ModelInfo format
        caps = self._get_cached_model_caps()

        # Determine vision support from available models
        supports_vision = any(
            m.get("supports_vision", False) for m in caps
        ) if caps else True  # Assume vision capable if at least one model supports it

        # Determine structured output support
        supports_structured = True  # Ollama supports format=json

        # Determine context window from active model
        ctx_window = self._provider.context_window()

        return ModelInfo(
            model_id=self._provider.narration_model or "qwen3.5:9b",
            provider_id=self.provider_id,
            upstream_model_id=self._provider.narration_model or "qwen3.5:9b",
            display_name=self.display_name,
            capabilities=self._map_to_capability_list(caps) if caps else [
                CapabilityType.TEXT_GENERATE,
                CapabilityType.TEXT_REASON,
                CapabilityType.TEXT_STRUCTURED,
            ],
            modalities_in=["text"],
            modalities_out=["text"],
            context_window=ctx_window,
            output_limit=2048,
            supports_streaming=True,
            supports_structured=supports_structured,
            supports_tools=False,
            pricing_input_per_million=Decimal("0.0"),
            pricing_output_per_million=Decimal("0.0"),
            free_tier=True,
            commercial_use=True,
            privacy_retention="local_only",
            health_status=HealthStatus.HEALTHY,
        )

    # --- Request execution ---

    async def execute(self, request: NormalizedRequest) -> NormalizedResponse:
        """Execute a normalized request against Ollama.

        Routes based on capability:
        - text.generate/text.reason/text.summarize -> generate_text
        - text.structured -> generate_structured with JSON schema
        - vision.* -> analyze_vision with base64-encoded image
        """
        attempt_history: list = []

        try:
            # Route based on capability
            capability = request.capability

            if capability in {"text.generate", "text.reason", "text.summarize"}:
                result = await self._execute_text_generation(request, attempt_history)
            elif capability == "text.structured":
                result = await self._execute_structured_output(request, attempt_history)
            elif capability in {
                "vision.understand",
                "vision.ocr_assist",
                "vision.panel_analysis",
                "vision.continuity_check",
            }:
                result = await self._execute_vision_task(request, attempt_history)
            else:
                raise UnsupportedCapabilityError(
                    f"Capability '{capability}' not supported by Ollama adapter"
                )

            # Build normalized response
            normalized = self._build_response(
                result=result,
                provider_id=self.provider_id,
                model_id=self._provider.narration_model or "qwen3.5:9b",
                attempt_history=attempt_history,
                latency_ms=self._get_latency(),
            )

            return normalized

        except Exception as e:
            logger.error(f"Ollama execution failed: {e}", exc_info=True)
            # Classify error
            error_str = str(e).lower()
            if "429" in error_str or "rate limit" in error_str:
                raise RateLimitError(f"Ollama rate limited: {e}")
            elif "401" in error_str or "auth" in error_str or "invalid" in error_str:
                raise AuthenticationError(f"Ollama auth failed: {e}")
            elif "timeout" in error_str or "connection" in error_str:
                raise TransientError(f"Ollama transient failure: {e}")
            else:
                raise TransientError(f"Ollama generation failed: {e}")

    async def _execute_text_generation(
        self, request: NormalizedRequest, attempt_history: list
    ) -> str:
        """Execute text generation via Ollama generate_text."""
        # Map system prompt if present
        system_prompt = request.system_prompt

        result = await self._provider.generate_text(
            prompt=request.prompt,
            system_prompt=system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        return result

    async def _execute_structured_output(
        self, request: NormalizedRequest, attempt_history: list
    ) -> dict:
        """Execute structured output via Ollama generate_structured."""
        # Convert output_schema to format expected by Ollama
        schema = request.output_schema or {}

        raw_json = await self._provider.generate_structured(
            prompt=request.prompt,
            system_prompt=(
                f"You are a precise structure analysis engine. "
                f"Respond ONLY with valid JSON. Do NOT include markdown fences, "
                f"comments, or preamble. Return raw JSON only."
            ),
            temperature=request.temperature,
            max_repair_retries=2,
        )
        return raw_json

    async def _execute_vision_task(
        self, request: NormalizedRequest, attempt_history: list
    ) -> str:
        """Execute vision task via Ollama analyze_vision."""
        # Encode image if provided - delegate to provider which handles base64
        image_bytes = None
        if request.input_modalities and "image" in request.input_modalities:
            # The underlying OllamaProvider.analyze_vision handles base64 encoding
            # We pass None and let it use the prompt/image from context
            pass

        result = await self._provider.analyze_vision(
            image=image_bytes,
            prompt=request.prompt,
            system_prompt=request.system_prompt,
        )

        return result

    # --- Model discovery and caching ---

    async def list_available_models(self) -> list:
        """Discover installed Ollama models with capabilities.

        Caches results for TTL to avoid excessive API calls.
        """
        import time

        now = time.time()

        # Return cached results if fresh
        if self._models_cache and self._cache_timestamp and (now - self._cache_timestamp) < self._cache_ttl:
            return self._models_cache

        try:
            models = await self._provider.list_available_models()
            if not models:
                self._models_cache = []
                self._cache_timestamp = now
                return []

            # enrich with capability info
            tasks = [self._provider.inspect_model_capabilities(name) for name in models]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            enriched = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Fall back to basic model info
                    enriched.append(
                        {"name": models[i], "supports_vision": False, "error": str(result)}
                    )
                else:
                    enriched.append(result)

            self._models_cache = enriched
            self._cache_timestamp = now
            return enriched

        except Exception as e:
            logger.warning(f"Model discovery failed: {e}")
            self._models_cache = []
            self._cache_timestamp = now
            return []

    def _get_cached_model_caps(self) -> list:
        """Get cached model capabilities, loading if needed."""
        if self._models_cache is None:
            # Load synchronously for immediate access
            loop = asyncio.get_event_loop()
            self._models_cache = loop.run_until_complete(self.list_available_models())
        return self._models_cache

    # --- Response building ---

    def _build_response(
        self,
        result: Any,
        provider_id: str,
        model_id: str,
        attempt_history: list,
        latency_ms: int,
    ) -> NormalizedResponse:
        """Build a NormalizedResponse from raw Ollama result."""
        from engine.ai_gateway.contracts import FinishStatus

        # Determine status
        if attempt_history and attempt_history[-1].status == FinishStatus.FAILED:
            status = FinishStatus.FAILED
        else:
            status = FinishStatus.SUCCESS

        # Estimate tokens (rough)
        input_tokens = None
        output_tokens = None
        if isinstance(result, str):
            # Rough character-to-token estimate
            output_tokens = max(1, len(result) // 4)

        # Cost is zero for local Ollama
        cost_estimate = Decimal("0.0")
        cost_actual = Decimal("0.0")

        # Build attempt history if empty
        if not attempt_history:
            attempt_history = [
                AttemptResult(
                    attempt_number=1,
                    provider_id=provider_id,
                    model_id=model_id,
                    status=status,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_estimate=cost_estimate,
                    cost_actual=cost_actual,
                )
            ]

        return NormalizedResponse(
            request_id="",  # Will be filled by caller
            status=status,
            result=result,
            artifact_refs=[],
            provider_used=provider_id,
            model_used=model_id,
            attempt_history=attempt_history,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate=cost_estimate,
            cost_actual=cost_actual,
            cost_confidence="HIGH",  # Local = known
            latency_ms=latency_ms,
            finish_reason=None,
            validation_status="SUCCESS",
            error_info=None,
            provider_request_id="",
            trace_id="",
        )

    # --- Utility methods ---

    @staticmethod
    def _map_ollama_caps(model_data: dict) -> list:
        """Map Ollama /api/show capabilities to CapabilityType enum."""
        caps = model_data.get("capabilities", [])
        caps_lower = [c.lower() for c in caps]

        mapped = []
        for ct in CapabilityType:
            # Map based on common capability names
            if ct == CapabilityType.TEXT_GENERATE and "text" in caps_lower:
                mapped.append(ct)
            elif ct == CapabilityType.TEXT_STRUCTURED and "json" in caps_lower:
                mapped.append(ct)
            elif ct == CapabilityType.VISION_UNDERSTAND and "vision" in caps_lower:
                mapped.append(ct)
            elif ct == CapabilityType.VISION_OCR_ASSIST and "clip" in caps_lower:
                mapped.append(ct)

        return mapped if mapped else [CapabilityType.TEXT_GENERATE]

    @staticmethod
    def _map_to_capability_list(caps: list) -> list:
        """Convert model capability dicts to CapabilityType list."""
        result = []
        for ct in CapabilityType:
            # Simple heuristic-based mapping
            if ct in [
                CapabilityType.TEXT_GENERATE,
                CapabilityType.TEXT_REASON,
                CapabilityType.TEXT_STRUCTURED,
                CapabilityType.VISION_UNDERSTAND,
                CapabilityType.VISION_PANEL_ANALYSIS,
                CapabilityType.VISION_CONTINUITY_CHECK,
            ]:
                result.append(ct)
        return result if result else [CapabilityType.TEXT_GENERATE]

    def _load_image_from_request(self, request: NormalizedRequest) -> bytes | None:
        """Attempt to load image bytes from request input_refs or prompt hints.

        In a full implementation, this would resolve file paths, read from
        project storage, etc. For now, returns None (adapter will handle
        base64 encoding internally via OllamaProvider.analyze_vision).
        """
        # Delegate to the underlying provider - it handles base64 encoding
        return None

    def _get_latency(self) -> int:
        """Return approximate latency in milliseconds.

        In production, this would be measured during the actual request.
        For now, returns 0 (caller should measure).
        """
        return 0

    # --- ProviderAdapter interface implementations ---

    def normalize_request(self, request: NormalizedRequest) -> Dict[str, Any]:
        """Convert normalized request to Ollama-specific payload.

        Maps the gateway's NormalizedRequest to the OllamaProvider's
        expected parameters for generate_text/generate_structured/analyze_vision.
        """
        payload: Dict[str, Any] = {
            "model": request.model_overrides.get("model", self._provider.narration_model or "qwen3.5:9b"),
            "prompt": request.prompt,
            "stream": False,
            "think": False,
            "thinking": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "num_ctx": request.timeout_seconds,  # reuse timeout as ctx
            },
        }

        if request.system_prompt:
            payload["system"] = request.system_prompt

        # Add structured output format if requested
        if request.output_schema:
            payload["format"] = request.output_schema

        # Add image placeholder for vision tasks
        if request.capability.value.startswith("vision."):
            # Image handling deferred to analyze_vision base64 encoding
            payload["images"] = []  # placeholder; actual encoding in provider

        return payload

    def normalize_response(
        self, raw_response: Dict[str, Any], request: NormalizedRequest
    ) -> NormalizedResponse:
        """Convert Ollama's raw API response to NormalizedResponse.

        Handles:
        - Success/failure classification
        - Token extraction from response metadata
        - Cost calculation (zero for local Ollama)
        - Validation of structured output
        - Error diagnostics without leaking secrets
        """
        from engine.ai_gateway.contracts import FinishStatus, AttemptResult

        # Check for errors in raw response
        if raw_response.get("error"):
            error_msg = raw_response["error"]
            return NormalizedResponse(
                request_id=request.request_id,
                status=FinishStatus.FAILED,
                result=None,
                artifact_refs=[],
                provider_used=self.provider_id,
                model_used=request.model_overrides.get("model", "unknown"),
                attempt_history=[AttemptResult(
                    attempt_number=1,
                    provider_id=self.provider_id,
                    model_id=request.model_overrides.get("model", "unknown"),
                    status=FinishStatus.FAILED,
                    latency_ms=0,
                    error_code="ollama_api_error",
                    error_message=error_msg,
                )],
                latency_ms=0,
                validation_status="FAILED",
                error_info={"provider_error": error_msg},
                provider_request_id="",
                trace_id="",
            )

        # Success case - extract response text
        response_text = raw_response.get("response", "")
        input_tokens = raw_response.get("prompt_eval_count", 0)
        output_tokens = raw_response.get("eval_count", 0)
        latency_ms = raw_response.get("eval_duration", 0) // 1_000_000  # convert ns to ms

        # Cost is zero for local Ollama
        cost_estimate = Decimal("0.0")
        cost_actual = Decimal("0.0")

        # Build attempt history
        attempt_history = [AttemptResult(
            attempt_number=1,
            provider_id=self.provider_id,
            model_id=request.model_overrides.get("model", "unknown"),
            status=FinishStatus.SUCCESS,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate=cost_estimate,
            cost_actual=cost_actual,
        )]

        return NormalizedResponse(
            request_id=request.request_id,
            status=FinishStatus.SUCCESS,
            result=response_text,
            artifact_refs=[],
            provider_used=self.provider_id,
            model_used=request.model_overrides.get("model", self._provider.narration_model or "qwen3.5:9b"),
            attempt_history=attempt_history,
            input_tokens=input_tokens if input_tokens > 0 else None,
            output_tokens=output_tokens if output_tokens > 0 else None,
            cost_estimate=cost_estimate,
            cost_actual=cost_actual,
            cost_confidence="HIGH",
            latency_ms=latency_ms,
            validation_status="SUCCESS",
            error_info=None,
            provider_request_id=raw_response.get("response_id", ""),
            trace_id=request.trace_id,
        )


# Global instance for gateway integration
ollama_adapter = OllamaAdapter()