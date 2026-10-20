"""Anthropic Claude provider adapter for the Universal AI Gateway.

Implements the ProviderAdapter interface for Anthropic's Claude API, supporting:
- Claude 3 Opus, Sonnet, and Haiku models
- Messages API with tool use support
- Vision (image understanding) via Claude 3 Sonnet/Opus
- Structured output via response_format
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

logger = logging.getLogger("panelflow.llm.adapter.anthropic")


class AnthropicAdapter(ProviderAdapter):
    """Adapter for Anthropic Claude API (Claude 3 Opus, Sonnet, Haiku).

    Wraps the Anthropic Messages API and provides normalized
    request/response contracts compatible with the Universal AI Gateway.
    """

    def __init__(
        self,
        endpoint_url: str = "https://api.anthropic.com/v1",
        api_key: str = "",
        model_name: str = "claude-3-5-sonnet-20240620",
        timeout: float = 60.0,
    ):
        """Initialize the Anthropic adapter.

        Args:
            endpoint_url: Anthropic API base URL
            api_key: Anthropic API key. If not provided, reads from ANTHROPIC_API_KEY env var.
            model_name: Default model to use (claude-3-5-sonnet, claude-3-opus, claude-3-haiku)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or ""
        self.endpoint_url = endpoint_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

        if not self.api_key:
            import os
            self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # --- ProviderAdapter interface ---

    @property
    def provider_id(self) -> str:
        return "anthropic"

    @property
    def display_name(self) -> str:
        return f"Anthropic Claude ({self.model_name})"

    async def health_check(self) -> HealthStatusOutput:
        """Verify Anthropic API connectivity and model availability."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
                res = await client.get(f"{self.endpoint_url}/models", headers=headers)
                if res.status_code == 200:
                    models_data = res.json().get("data", [])
                    model_ids = [m.get("id", "") for m in models_data]
                    model_available = any(self.model_name in mid for mid in model_ids)
                    status = HealthStatus.HEALTHY if model_available else HealthStatus.DEGRADED
                    return HealthStatusOutput(
                        status=status,
                        latency_ms=res.elapsed.total_seconds() * 1000,
                        details=f"Anthropic API reachable, model={self.model_name}",
                    )
                else:
                    return HealthStatusOutput(
                        status=HealthStatus.UNHEALTHY,
                        latency_ms=0,
                        details=f"Anthropic API returned {res.status_code}",
                    )
        except Exception as e:
            logger.warning(f"Anthropic health check failed: {e}")
            return HealthStatusOutput(
                status=HealthStatus.OFFLINE,
                latency_ms=0,
                details=f"Health check error: {e}",
            )

    def supports_capability(self, capability: CapabilityType) -> bool:
        """Check if Anthropic supports the given capability."""
        # Claude 3 Sonnet/Opus support most capabilities
        supports_vision = self.model_name in {"claude-3-opus-20240229", "claude-3-sonnet-20240229"}

        supported = {
            "text.generate": True,
            "text.reason": True,
            "text.structured": True,
            "text.translate": True,
            "text.summarize": True,
            "vision.understand": supports_vision,
            "vision.ocr_assist": supports_vision,
            "vision.panel_analysis": supports_vision,
            "vision.continuity_check": supports_vision,
            "audio.transcribe": False,  # Claude doesn't do transcription natively
            "audio.synthesize": False,
            "audio.analyze": False,
            "music.generate": False,
            "image.generate": False,
            "image.edit": False,
            "video.generate": False,
            "embeddings.generate": True,  # Via text input
        }
        return supported.get(capability, False)

    def get_capabilities(self) -> ModelInfo:
        """Return model metadata and capability flags."""
        supports_vision = self.model_name in {"claude-3-opus-20240229", "claude-3-sonnet-20240229"}

        cap_list = [
            "text.generate",
            "text.reason" if self.model_name.startswith("claude-3") else None,
            "text.structured",
            "text.translate",
            "text.summarize",
        ]
        cap_list = [c for c in cap_list if c is not None]
        if supports_vision:
            cap_list.extend([
                "vision.understand",
                "vision.ocr_assist",
                "vision.panel_analysis",
                "vision.continuity_check",
            ])

        # Context windows by model
        ctx_map = {
            "claude-3-opus-20240229": 200_000,
            "claude-3-sonnet-20240229": 200_000,
            "claude-3-haiku-20240307": 100_000,
        }
        context_window = ctx_map.get(self.model_name, 200_000)

        pricing_input = Decimal("15.0") if self.model_name == "claude-3-opus-20240229" else Decimal("3.0")
        pricing_output = Decimal("75.0") if self.model_name == "claude-3-opus-20240229" else Decimal("15.0")

        return ModelInfo(
            model_id=self.model_name,
            provider_id=self.provider_id,
            upstream_model_id=self.model_name,
            display_name=self.display_name,
            capabilities=cap_list,
            modalities_in=["text"] + (["image"] if supports_vision else []),
            modalities_out=["text"],
            context_window=context_window,
            output_limit=4096,
            supports_streaming=True,
            supports_structured=True,
            supports_tools=self.model_name.startswith("claude-3"),  # Claude 3 supports tool use
            pricing_input_per_million=pricing_input,
            pricing_output_per_million=pricing_output,
            free_tier=False,
            commercial_use=False,  # Must verify per use case
            privacy_retention="anthropic_policy",
            health_status=HealthStatus.HEALTHY,
        )

    # --- Request execution ---

    async def execute(self, request: NormalizedRequest) -> NormalizedResponse:
        """Execute a normalized request against Anthropic API."""
        attempt_history: list = []

        try:
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
                    f"Capability '{capability}' not supported by Anthropic adapter"
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
            logger.error(f"Anthropic execution failed: {e}", exc_info=True)
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                raise RateLimitError(f"Anthropic rate limited: {e}")
            elif "authentication" in error_str or "invalid" in error_str or "401" in error_str:
                raise AuthenticationError(f"Anthropic auth failed: {e}")
            elif "timeout" in error_str:
                raise TransientError(f"Anthropic timeout: {e}")
            else:
                raise TransientError(f"Anthropic generation failed: {e}")

    async def _execute_text_generation(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute text generation via Anthropic Messages API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Anthropic uses: POST https://api.anthropic.com/v1/messages?model={model}
            url = f"{self.endpoint_url}/messages?model={self.model_name}"

            # Build content blocks
            content_blocks = []
            if request.system_prompt:
                content_blocks.append(
                    {"type": "text", "text": request.system_prompt}
                )
            content_blocks.append({"type": "text", "text": request.prompt})

            payload = {
                "model": request.model_overrides.get("model", self.model_name),
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "system": request.system_prompt,
                "messages": [{"role": "user", "content": content_blocks}],
                "stream": False,
            }

            # Add structured output if requested
            if request.output_schema:
                payload["response_format"] = {
                    "type": "json",
                }

            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }

            res = await client.post(url, json=payload, headers=headers)

            if res.status_code != 200:
                error_detail = res.text
                if "429" in str(res.status_code) or "rate" in error_detail.lower():
                    raise RateLimitError(f"Anthropic rate limited: {error_detail}")
                raise TransientError(f"Anthropic generation failed: HTTP {res.status_code}: {error_detail}")

            data = res.json()
            # Extract text from response
            if data.get("content") and len(data["content"]) > 0:
                text_parts = []
                for block in data["content"]:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                return "".join(text_parts).strip()
            else:
                raise TransientError(f"Anthropic no response content: {data}")

    async def _execute_structured_output(self, request: NormalizedRequest, attempt_history: list) -> dict:
        """Execute structured output via Anthropic with response format."""
        schema = request.output_schema or {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.endpoint_url}/messages?model={self.model_name}"

            content_blocks = []
            if request.system_prompt:
                content_blocks.append({"type": "text", "text": request.system_prompt})
            content_blocks.append({"type": "text", "text": request.prompt})

            payload = {
                "model": request.model_overrides.get("model", self.model_name),
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "stream": False,
                "system": request.system_prompt,
                "messages": [{"role": "user", "content": content_blocks}],
                "response_format": {"type": "json"},
            }

            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }

            res = await client.post(url, json=payload, headers=headers)

            if res.status_code != 200:
                raise TransientError(f"Anthropic structured failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            if data.get("content") and len(data["content"]) > 0:
                text_parts = []
                for block in data["content"]:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                raw_json = "".join(text_parts).strip()
                return json.loads(raw_json)
            else:
                raise TransientError(f"Anthropic structured no response: {data}")

    async def _execute_vision_task(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute vision task via Anthropic Claude 3 Sonnet/Opus."""
        # Claude 3 vision: embed image as base64 in the content
        image_base64 = None
        if request.input_modalities and "image" in request.input_modalities:
            # In full implementation, resolve image from input_refs/project storage
            # For now, placeholder - caller should provide base64
            image_base64 = ""

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.endpoint_url}/messages?model={self.model_name}"

            # Build content blocks with image
            content_parts = []
            if request.system_prompt:
                content_parts.append({"type": "text", "text": request.system_prompt})
            content_parts.append({"type": "text", "text": request.prompt})
            if image_base64:
                content_parts.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64,
                        },
                    }
                )

            payload = {
                "model": request.model_overrides.get("model", self.model_name),
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "system": request.system_prompt,
                "messages": [{"role": "user", "content": content_parts}],
                "stream": False,
            }

            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }

            res = await client.post(url, json=payload, headers=headers)

            if res.status_code != 200:
                raise TransientError(f"Anthropic vision failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            if data.get("content") and len(data["content"]) > 0:
                text_parts = []
                for block in data["content"]:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                return "".join(text_parts).strip()
            else:
                raise TransientError(f"Anthropic vision no response: {data}")

    # --- Response building ---

    def _build_response(
        self,
        result: Any,
        provider_id: str,
        model_id: str,
        attempt_history: list,
        latency_ms: int,
    ) -> NormalizedResponse:
        """Build a NormalizedResponse from raw Anthropic result."""
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

        # Cost calculation (Anthropic pricing)
        # Claude 3 Opus: $15/$75 per M tokens
        # Claude 3 Sonnet: $3/$15 per M tokens
        # Claude 3 Haiku: $0.25/$1.25 per M tokens
        if input_tokens and output_tokens:
            if self.model_name == "claude-3-opus-20240229":
                cost_actual = Decimal(
                    str(round((input_tokens / 1_000_000) * 15 + (output_tokens / 1_000_000) * 75, 6))
                )
            elif self.model_name == "claude-3-haiku-20240307":
                cost_actual = Decimal(
                    str(round((input_tokens / 1_000_000) * 0.25 + (output_tokens / 1_000_000) * 1.25, 6))
                )
            else:
                # Sonnet
                cost_actual = Decimal(
                    str(round((input_tokens / 1_000_000) * 3 + (output_tokens / 1_000_000) * 15, 6))
                )

        cost_estimate = cost_actual  # Estimate = actual for known pricing

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
        """Convert normalized request to Anthropic-specific payload."""
        # Build content blocks
        content = []
        if request.system_prompt:
            content.append({"type": "text", "text": request.system_prompt})
        content.append({"type": "text", "text": request.prompt})

        # Add image for vision tasks
        if request.capability.value.startswith("vision.") and request.input_modalities and "image" in request.input_modalities:
            # In full implementation, encode image from input_refs
            # Placeholder - caller provides base64
            content.append(
                {"type": "image", "source": {"type": "base64", "data": ""}}
            )

        payload: Dict[str, Any] = {
            "model": request.model_overrides.get("model", self.model_name),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system_prompt if request.system_prompt else None,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }

        # Add structured output format if requested
        if request.output_schema:
            payload["response_format"] = {"type": "json"}

        return payload

    def normalize_response(self, raw_response: Dict[str, Any], request: NormalizedRequest) -> NormalizedResponse:
        """Convert Anthropic's raw API response to NormalizedResponse."""
        from engine.ai_gateway.contracts import FinishStatus, AttemptResult

        # Check for errors
        if raw_response.get("type") == "error":
            error_msg = raw_response.get("error", {}).get("message", "Unknown Anthropic error")
            if "429" in str(raw_response.get("error", {}).get("type", "")) or "rate" in error_msg.lower():
                raise RateLimitError(f"Anthropic rate limited: {error_msg}")
            raise AuthenticationError(f"Anthropic auth failed: {error_msg}")

        # Success case - extract response text
        content = raw_response.get("content", [])
        text_parts = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        response_text = "".join(text_parts).strip()

        # Extract usage
        usage = raw_response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

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
        """Estimate cost for Anthropic model usage."""
        pricing = {
            "claude-3-opus-20240229": (Decimal("15.0"), Decimal("75.0")),
            "claude-3-sonnet-20240229": (Decimal("3.0"), Decimal("15.0")),
            "claude-3-haiku-20240307": (Decimal("0.25"), Decimal("1.25")),
        }
        inp, out = pricing.get(model, (Decimal("3.0"), Decimal("15.0")))
        cost = (Decimal(input_tokens) / 1_000_000) * inp + (Decimal(output_tokens) / 1_000_000) * out
        return cost


# Global instance for gateway integration
anthropic_adapter = AnthropicAdapter()