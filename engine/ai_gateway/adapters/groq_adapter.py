"""Groq provider adapter for the Universal AI Gateway.

Implements the ProviderAdapter interface for GroqCloud, supporting:
- Llama 3.1 70B, 8B, 70B Instruct models
- Mixtral 8x7B model
- Fast text generation with low latency
- OpenAI-compatible API structure
"""

import asyncio
import json
import logging
from decimal import Decimal
from typing import TypeVar, Type, Any, Optional, Dict, List

import httpx
from pydantic import BaseModel, ValidationError

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

logger = logging.getLogger("panelflow.llm.adapter.groq")


class GroqAdapter(ProviderAdapter):
    """Adapter for GroqCloud API, offering fast inference with Llama 3.1 models.

    Wraps the Groq API and provides normalized request/response contracts
    compatible with the Universal AI Gateway.
    """

    def __init__(
        self,
        endpoint_url: str = "https://api.groq.com/openai/v1",
        api_key: str = "",
        model_name: str = "llama-3.1-70b-versatile",
        timeout: float = 30.0,
    ):
        """Initialize the Groq adapter.

        Args:
            endpoint_url: Groq API base URL
            api_key: Groq API key. If not provided, reads from GROQ_API_KEY env var.
            model_name: Default model to use
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or ""
        self.endpoint_url = endpoint_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

        if not self.api_key:
            import os
            self.api_key = os.environ.get("GROQ_API_KEY", "")

    # --- ProviderAdapter interface ---

    @property
    def provider_id(self) -> str:
        return "groq"

    @property
    def display_name(self) -> str:
        return f"GroqCloud ({self.model_name})"

    async def health_check(self) -> HealthStatusOutput:
        """Verify Groq API connectivity and model availability."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                res = await client.get(
                    f"{self.endpoint_url}/models", headers=headers
                )
                if res.status_code == 200:
                    models_data = res.json().get("data", [])
                    model_ids = [m.get("id", "") for m in models_data]
                    model_available = any(self.model_name in mid for mid in model_ids)
                    status = (
                        HealthStatus.HEALTHY
                        if model_available
                        else HealthStatus.DEGRADED
                    )
                    return HealthStatusOutput(
                        status=status,
                        latency_ms=res.elapsed.total_seconds() * 1000,
                        details=f"Groq API reachable, model={self.model_name}",
                    )
                else:
                    return HealthStatusOutput(
                        status=HealthStatus.UNHEALTHY,
                        latency_ms=0,
                        details=f"Groq API returned {res.status_code}",
                    )
        except Exception as e:
            logger.warning(f"Groq health check failed: {e}")
            return HealthStatusOutput(
                status=HealthStatus.OFFLINE,
                latency_ms=0,
                details=f"Health check error: {e}",
            )

    def supports_capability(self, capability: CapabilityType) -> bool:
        """Check if Groq supports the given capability."""
        # Groq is text-only, focused on fast inference
        supported = {
            "text.generate": True,
            "text.reason": True,
            "text.structured": True,
            "text.translate": True,
            "text.summarize": True,
            # Groq is text-only
            "vision.understand": False,
            "vision.ocr_assist": False,
            "vision.panel_analysis": False,
            "vision.continuity_check": False,
            "audio.transcribe": False,
            "audio.synthesize": False,
            "audio.analyze": False,
            "music.generate": False,
            "image.generate": False,
            "image.edit": False,
            "video.generate": False,
            "embeddings.generate": False,
        }
        return supported.get(capability, False)

    def get_capabilities(self) -> ModelInfo:
        """Return model metadata and capability flags."""
        # Groq models: llama-3.1-70b-versatile, llama-3.1-8b, mixtral-8x7b
        return ModelInfo(
            model_id=self.model_name,
            provider_id=self.provider_id,
            upstream_model_id=self.model_name,
            display_name=self.display_name,
            capabilities=[
                "text.generate",
                "text.reason",
                "text.structured",
                "text.translate",
                "text.summarize",
            ],
            modalities_in=["text"],
            modalities_out=["text"],
            context_window=self._get_context_window(),
            output_limit=4096,
            supports_streaming=True,
            supports_structured=True,
            supports_tools=False,
            pricing_input_per_million=Decimal("0.25"),  # Approximate Groq pricing
            pricing_output_per_million=Decimal("0.25"),  # Approximate Groq pricing
            free_tier=False,
            commercial_use=True,  # Groq aims to be commercial-friendly
            privacy_retention="groq_policy",
            health_status=HealthStatus.HEALTHY,
        )

    # --- Request execution ---

    async def execute(self, request: NormalizedRequest) -> NormalizedResponse:
        """Execute a normalized request against Groq API."""
        attempt_history: list = []

        try:
            capability = request.capability

            if capability in {
                "text.generate",
                "text.reason",
                "text.summarize",
            }:
                result = await self._execute_text_generation(request, attempt_history)
            elif capability == "text.structured":
                result = await self._execute_structured_output(request, attempt_history)
            else:
                raise UnsupportedCapabilityError(
                    f"Capability '{capability}' not supported by Groq adapter"
                )

            normalized = self._build_response(
                result=result,
                provider_id=self.provider_id,
                model_id=self.model_name,
                attempt_history=attempt_history,
                latency_ms=self._get_latency(),
            )

            return normalized

        except Exception as e:
            logger.error(f"Groq execution failed: {e}", exc_info=True)
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                raise RateLimitError(f"Groq rate limited: {e}")
            elif "authentication" in error_str or "invalid" in error_str or "401" in error_str:
                raise AuthenticationError(f"Groq auth failed: {e}")
            elif "timeout" in error_str:
                raise TransientError(f"Groq timeout: {e}")
            else:
                raise TransientError(f"Groq generation failed: {e}")

    async def _execute_text_generation(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute text generation via Groq API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {
                "model": request.model_overrides.get("model", self.model_name),
                "messages": [
                    {"role": "user", "content": request.prompt}
                ],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": False,
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            if res.status_code != 200:
                error_detail = res.text
                if "429" in str(res.status_code) or "rate" in error_detail.lower():
                    raise RateLimitError(f"Groq rate limited: {error_detail}")
                raise TransientError(f"Groq generation failed: HTTP {res.status_code}: {error_detail}")

            data = res.json()
            return data["choices"][0]["message"]["content"].strip()

    async def _execute_structured_output(self, request: NormalizedRequest, attempt_history: list) -> dict:
        """Execute structured output via Groq."""
        schema = request.output_schema or {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {
                "model": request.model_overrides.get("model", self.model_name),
                "messages": [
                    {"role": "user", "content": request.prompt}
                ],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "response_format": {"type": "json_object"},
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            if res.status_code != 200:
                raise TransientError(f"Groq structured failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            raw_json = data["choices"][0]["message"]["content"].strip()
            return json.loads(raw_json)

    # --- Response building ---

    def _build_response(
        self,
        result: Any,
        provider_id: str,
        model_id: str,
        attempt_history: list,
        latency_ms: int,
    ) -> NormalizedResponse:
        """Build a NormalizedResponse from raw Groq result."""
        from engine.ai_gateway.contracts import FinishStatus

        # Determine status
        if attempt_history and attempt_history[-1].status == FinishStatus.FAILED:
            status = FinishStatus.FAILED
        else:
            status = FinishStatus.SUCCESS

        # Extract tokens and usage
        input_tokens = None
        output_tokens = None
        cost_estimate = Decimal("0.0")
        cost_actual = Decimal("0.0")

        if isinstance(result, str):
            output_tokens = max(1, len(result) // 4)

        # Cost calculation (approximate Groq pricing)
        if input_tokens and output_tokens:
            cost_actual = Decimal(
                str(round((input_tokens / 1_000_000) * 0.25 + (output_tokens / 1_000_000) * 0.25, 6))
            )

        cost_estimate = cost_actual

        # Build attempt history
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
            request_id="",
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
            cost_confidence="MEDIUM",
            latency_ms=latency_ms,
            validation_status="SUCCESS",
            error_info=None,
            provider_request_id="",
            trace_id="",
        )

    # --- Utility methods ---

    def _get_context_window(self) -> int:
        """Return context window in tokens based on model."""
        windows = {
            "llama-3.1-70b-versatile": 131_000,
            "llama-3.1-8b-instant": 8_192,
            "mixtral-8x7b-32768": 32_768,
        }
        return windows.get(self.model_name, 131_000)

    def _get_latency(self) -> int:
        return 0

    def normalize_request(self, request: NormalizedRequest) -> Dict[str, Any]:
        """Convert normalized request to Groq-specific payload."""
        payload: Dict[str, Any] = {
            "model": request.model_overrides.get("model", self.model_name),
            "messages": [
                {"role": "user", "content": request.prompt}
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        # Add structured output format if requested
        if request.output_schema:
            payload["response_format"] = {"type": "json_object"}

        return payload

    def normalize_response(self, raw_response: Dict[str, Any], request: NormalizedRequest) -> NormalizedResponse:
        """Convert Groq's raw API response to NormalizedResponse."""
        from engine.ai_gateway.contracts import FinishStatus, AttemptResult

        # Check for errors
        if raw_response.get("error"):
            error_msg = raw_response["error"].get("message", "Unknown Groq error")
            if "429" in str(raw_response["error"].get("status", "")) or "rate" in error_msg.lower():
                raise RateLimitError(f"Groq rate limited: {error_msg}")
            raise AuthenticationError(f"Groq auth failed: {error_msg}")

        # Success case
        response_text = raw_response["choices"][0]["message"]["content"].strip()
        usage = raw_response.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        # Estimate latency
        latency_ms = 0

        # Calculate cost
        cost_estimate = Decimal("0.0")
        cost_actual = self._calculate_cost(input_tokens, output_tokens, self.model_name)

        attempt_history = [AttemptResult(
            attempt_number=1,
            provider_id=self.provider_id,
            model_id=request.model_overrides.get("model", self.model_name),
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
            model_used=request.model_overrides.get("model", self.model_name),
            attempt_history=attempt_history,
            input_tokens=input_tokens if input_tokens > 0 else None,
            output_tokens=output_tokens if output_tokens > 0 else None,
            cost_estimate=cost_estimate,
            cost_actual=cost_actual,
            cost_confidence="MEDIUM",
            latency_ms=latency_ms,
            validation_status="SUCCESS",
            error_info=None,
            provider_request_id=raw_response.get("id", ""),
            trace_id=request.trace_id,
        )

    @staticmethod
    def _calculate_cost(input_tokens: int, output_tokens: int, model: str) -> Decimal:
        """Estimate cost for Groq model usage."""
        # Approximate Groq pricing
        return Decimal("0.0")  # Groq is very cost-effective


# Global instance for gateway integration
groq_adapter = GroqAdapter()