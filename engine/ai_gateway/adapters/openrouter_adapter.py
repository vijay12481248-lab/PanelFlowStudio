"""OpenRouter provider adapter for the Universal AI Gateway.

Implements the ProviderAdapter interface for OpenRouter, which aggregates
multiple AI providers through a single API, providing:
- Access to 100+ different models from various providers
- Native routing capabilities with custom headers
- Fallback and load balancing support
- Cost-effective access to many models
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

logger = logging.getLogger("panelflow.llm.adapter.openrouter")


class OpenRouterAdapter(ProviderAdapter):
    """Adapter for OpenRouter API, an aggregator of multiple AI providers.

    OpenRouter provides access to hundreds of AI models from different
    providers through a single API endpoint, with native routing
    capabilities and fallbacks.
    """

    def __init__(
        self,
        endpoint_url: str = "https://openrouter.ai/api/v1",
        api_key: str = "",
        model_name: str = "auto",
        timeout: float = 60.0,
    ):
        """Initialize the OpenRouter adapter.

        Args:
            endpoint_url: OpenRouter API base URL
            api_key: OpenRouter API key. If not provided, reads from OPENROUTER_API_KEY env var.
            model_name: Default model to use ("auto" for automatic selection)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or ""
        self.endpoint_url = endpoint_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

        if not self.api_key:
            import os
            self.api_key = os.environ.get("OPENROUTER_API_KEY", "")

    # --- ProviderAdapter interface ---

    @property
    def provider_id(self) -> str:
        return "openrouter"

    @property
    def display_name(self) -> str:
        return f"OpenRouter (auto-model)"

    async def health_check(self) -> HealthStatusOutput:
        """Verify OpenRouter API connectivity."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                res = await client.get(f"{self.endpoint_url}/models", headers=headers)
                if res.status_code == 200:
                    models_data = res.json().get("data", [])
                    model_count = len(models_data)
                    return HealthStatusOutput(
                        status=HealthStatus.HEALTHY if model_count > 0 else HealthStatus.DEGRADED,
                        latency_ms=res.elapsed.total_seconds() * 1000,
                        details=f"OpenRouter API reachable, {model_count} models available",
                    )
                else:
                    return HealthStatusOutput(
                        status=HealthStatus.UNHEALTHY,
                        latency_ms=0,
                        details=f"OpenRouter API returned {res.status_code}",
                    )
        except Exception as e:
            logger.warning(f"OpenRouter health check failed: {e}")
            return HealthStatusOutput(
                status=HealthStatus.OFFLINE,
                latency_ms=0,
                details=f"Health check error: {e}",
            )

    def supports_capability(self, capability: CapabilityType) -> bool:
        """Check if OpenRouter supports the given capability.

        OpenRouter supports most capabilities through its aggregated models.
        """
        # OpenRouter aggregates many models, most support text capabilities
        supported = {
            "text.generate": True,
            "text.reason": True,
            "text.structured": True,
            "text.translate": True,
            "text.summarize": True,
            # Vision support depends on the specific model selected
            "vision.understand": True,  # Many OpenRouter models support vision
            "vision.ocr_assist": True,
            "vision.panel_analysis": True,
            "vision.continuity_check": True,
            # Audio not typically supported by OpenRouter models
            "audio.transcribe": False,
            "audio.synthesize": False,
            "audio.analyze": False,
            "music.generate": False,
            "image.generate": False,
            "image.edit": False,
            "video.generate": False,
            "embeddings.generate": True,
        }
        return supported.get(capability, False)

    def get_capabilities(self) -> ModelInfo:
        """Return model metadata and capability flags."""
        # OpenRouter aggregates many models - default to comprehensive capabilities
        return ModelInfo(
            model_id=self.model_name or "auto",
            provider_id=self.provider_id,
            upstream_model_id=self.model_name or "auto",
            display_name=self.display_name,
            capabilities=[
                "text.generate",
                "text.reason",
                "text.structured",
                "text.translate",
                "text.summarize",
                "vision.understand",
                "vision.ocr_assist",
                "vision.panel_analysis",
                "vision.continuity_check",
                "embeddings.generate",
            ],
            modalities_in=["text", "image"],
            modalities_out=["text"],
            context_window=128_000,  # Many OpenRouter models support long context
            output_limit=4096,
            supports_streaming=True,
            supports_structured=True,
            supports_tools=False,
            pricing_input_per_million=Decimal("2.0"),  # Approximate average
            pricing_output_per_million=Decimal("2.0"),
            free_tier=False,
            commercial_use=True,  # Varies by model - check individual model terms
            privacy_retention="openrouter_policy",
            health_status=HealthStatus.HEALTHY,
        )

    # --- Request execution ---

    async def execute(self, request: NormalizedRequest) -> NormalizedResponse:
        """Execute a normalized request against OpenRouter API."""
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
            elif capability in {
                "vision.understand",
                "vision.ocr_assist",
                "vision.panel_analysis",
                "vision.continuity_check",
            }:
                result = await self._execute_vision_task(request, attempt_history)
            elif capability == "embeddings.generate":
                result = await self._execute_embeddings(request, attempt_history)
            else:
                raise UnsupportedCapabilityError(
                    f"Capability '{capability}' not supported by OpenRouter adapter"
                )

            normalized = self._build_response(
                result=result,
                provider_id=self.provider_id,
                model_id=request.model_overrides.get("model", self.model_name or "auto"),
                attempt_history=attempt_history,
                latency_ms=self._get_latency(),
            )

            return normalized

        except Exception as e:
            logger.error(f"OpenRouter execution failed: {e}", exc_info=True)
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                raise RateLimitError(f"OpenRouter rate limited: {e}")
            elif "authentication" in error_str or "invalid" in error_str or "401" in error_str:
                raise AuthenticationError(f"OpenRouter auth failed: {e}")
            elif "timeout" in error_str:
                raise TransientError(f"OpenRouter timeout: {e}")
            else:
                raise TransientError(f"OpenRouter generation failed: {e}")

    async def _execute_text_generation(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute text generation via OpenRouter API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Build the request
            payload: Dict[str, Any] = {
                "model": request.model_overrides.get("model", self.model_name or "auto"),
                "messages": [
                    {"role": "user", "content": request.prompt}
                ],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": False,
            }

            # Add structured output if requested
            if request.output_schema:
                payload["response_format"] = {"type": "json_object"}

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # OpenRouter-specific headers
                "HTTP-Referer": "https://panelflow.studio",
                "X-Title": "PanelFlow Studio",
            }

            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            if res.status_code != 200:
                error_detail = res.text
                if "429" in str(res.status_code) or "rate" in error_detail.lower():
                    raise RateLimitError(f"OpenRouter rate limited: {error_detail}")
                raise TransientError(f"OpenRouter generation failed: HTTP {res.status_code}: {error_detail}")

            data = res.json()
            return data["choices"][0]["message"]["content"].strip()

    async def _execute_structured_output(self, request: NormalizedRequest, attempt_history: list) -> dict:
        """Execute structured output via OpenRouter."""
        schema = request.output_schema or {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload: Dict[str, Any] = {
                "model": request.model_overrides.get("model", self.model_name or "auto"),
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
                "HTTP-Referer": "https://panelflow.studio",
                "X-Title": "PanelFlow Studio",
            }

            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            if res.status_code != 200:
                raise TransientError(f"OpenRouter structured failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            raw_json = data["choices"][0]["message"]["content"].strip()
            return json.loads(raw_json)

    async def _execute_vision_task(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute vision task via OpenRouter."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload: Dict[str, Any] = {
                "model": request.model_overrides.get("model", self.model_name or "auto"),
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": request.prompt},
                        ],
                    }
                ],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": False,
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://panelflow.studio",
                "X-Title": "PanelFlow Studio",
            }

            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            if res.status_code != 200:
                raise TransientError(f"OpenRouter vision failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            if data.get("choices") and data["choices"][0].get("message"):
                text_parts = data["choices"][0]["message"].get("content", "")
                if isinstance(text_parts, str):
                    return text_parts.strip()
            raise TransientError(f"OpenRouter vision no response: {data}")

    async def _execute_embeddings(self, request: NormalizedRequest, attempt_history: list) -> list:
        """Execute embeddings via OpenRouter."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload: Dict[str, Any] = {
                "input": request.prompt,
                "model": request.model_overrides.get("model", self.model_name or "auto"),
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            res = await client.post(
                f"{self.endpoint_url}/embeddings",
                headers=headers,
                json=payload,
            )

            if res.status_code != 200:
                raise TransientError(f"OpenRouter embeddings failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            if data.get("data") and len(data["data"]) > 0:
                return data["data"][0].get("embedding", [])
            raise TransientError(f"OpenRouter embeddings no data: {data}")

    # --- Response building ---

    def _build_response(
        self,
        result: Any,
        provider_id: str,
        model_id: str,
        attempt_history: list,
        latency_ms: int,
    ) -> NormalizedResponse:
        """Build a NormalizedResponse from raw OpenRouter result."""
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

        # Cost calculation (approximate OpenRouter pricing)
        if input_tokens and output_tokens:
            cost_actual = Decimal(
                str(round((input_tokens / 1_000_000) * 2.0 + (output_tokens / 1_000_000) * 2.0, 6))
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

    def _get_latency(self) -> int:
        return 0

    def normalize_request(self, request: NormalizedRequest) -> Dict[str, Any]:
        """Convert normalized request to OpenRouter-specific payload."""
        payload: Dict[str, Any] = {
            "model": request.model_overrides.get("model", self.model_name or "auto"),
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

        # Add OpenRouter-specific headers will be added in execute()
        return payload

    def normalize_response(self, raw_response: Dict[str, Any], request: NormalizedRequest) -> NormalizedResponse:
        """Convert OpenRouter's raw API response to NormalizedResponse."""
        from engine.ai_gateway.contracts import FinishStatus, AttemptResult

        # Check for errors
        if raw_response.get("error"):
            error_msg = raw_response["error"].get("message", "Unknown OpenRouter error")
            if "429" in str(raw_response["error"].get("status", "")) or "rate" in error_msg.lower():
                raise RateLimitError(f"OpenRouter rate limited: {error_msg}")
            raise AuthenticationError(f"OpenRouter auth failed: {error_msg}")

        # Success case
        response_text = raw_response["choices"][0]["message"]["content"].strip()
        usage = raw_response.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        # Estimate latency
        latency_ms = 0

        # Calculate cost
        cost_estimate = Decimal("0.0")
        cost_actual = self._calculate_cost(input_tokens, output_tokens, self.model_name or "auto")

        attempt_history = [AttemptResult(
            attempt_number=1,
            provider_id=self.provider_id,
            model_id=request.model_overrides.get("model", self.model_name or "auto"),
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
            model_used=request.model_overrides.get("model", self.model_name or "auto"),
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
        """Estimate cost for OpenRouter model usage."""
        # Approximate OpenRouter pricing - varies by model
        return Decimal("0.0")  # OpenRouter often has discounted rates


# Global instance for gateway integration
openrouter_adapter = OpenRouterAdapter()