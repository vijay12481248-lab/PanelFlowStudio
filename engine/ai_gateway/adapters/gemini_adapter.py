"""Gemini provider adapter for the Universal AI Gateway.

Implements the ProviderAdapter interface for Google Gemini API, supporting:
- Gemini 1.5 Pro and 1.5 Flash models
- Vision (image understanding, OCR, panel analysis)
- Text generation, reasoning, structured output
- Embeddings generation
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
from engine.ai_gateway.registry.model_registry import model_registry

logger = logging.getLogger("panelflow.llm.adapter.gemini")


class GeminiAdapter(ProviderAdapter):
    """Adapter for Google Gemini API (gemini-1.5-pro, gemini-1.5-flash).

    Wraps the Google Gemini Generative AI API and provides normalized
    request/response contracts compatible with the Universal AI Gateway.
    """

    def __init__(
        self,
        endpoint_url: str = "https://generativelanguage.googleapis.com/v1beta",
        api_key: str = "",
        model_name: str = "gemini-1.5-flash",
        timeout: float = 60.0,
    ):
        """Initialize the Gemini adapter.

        Args:
            endpoint_url: Gemini API base URL (default: https://generativelanguage.googleapis.com/v1beta)
            api_key: Gemini API key. If not provided, reads from GEMINI_API_KEY env var.
            model_name: Default model to use (gemini-1.5-pro, gemini-1.5-flash)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or ""
        self.endpoint_url = endpoint_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

        if not self.api_key:
            import os
            self.api_key = os.environ.get("GEMINI_API_KEY", "")

    # --- ProviderAdapter interface ---

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return f"Google Gemini ({self.model_name})"

    async def health_check(self) -> HealthStatusOutput:
        """Verify Gemini API connectivity and model availability."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Gemini health check via models list
                url = f"{self.endpoint_url}/models?key={self.api_key}"
                res = await client.get(url)
                if res.status_code == 200:
                    models_data = res.json().get("models", [])
                    model_ids = [m.get("name", "") for m in models_data]
                    # Check if our model prefix is available
                    model_available = any(
                        m.startswith(self.model_name.replace("-", "")) for m in model_ids
                    )
                    status = (
                        HealthStatus.HEALTHY
                        if model_available
                        else HealthStatus.DEGRADED
                    )
                    return HealthStatusOutput(
                        status=status,
                        latency_ms=res.elapsed.total_seconds() * 1000,
                        details=f"Gemini API reachable, model={self.model_name}, "
                        f"found={model_available}",
                    )
                else:
                    return HealthStatusOutput(
                        status=HealthStatus.UNHEALTHY,
                        latency_ms=0,
                        details=f"Gemini API returned {res.status_code}",
                    )
        except Exception as e:
            logger.warning(f"Gemini health check failed: {e}")
            return HealthStatusOutput(
                status=HealthStatus.OFFLINE,
                latency_ms=0,
                details=f"Health check error: {e}",
            )

    def supports_capability(self, capability: CapabilityType) -> bool:
        """Check if Gemini supports the given capability."""
        # Gemini 1.5 Pro/Flash support most capabilities
        supports_vision = self.model_name in {"gemini-1.5-pro", "gemini-1.5-flash"}

        supported = {
            # Text capabilities - all supported
            "text.generate": True,
            "text.reason": True,
            "text.structured": True,
            "text.translate": True,
            "text.summarize": True,
            # Vision capabilities - supported by 1.5 Pro/Flash
            "vision.understand": supports_vision,
            "vision.ocr_assist": supports_vision,
            "vision.panel_analysis": supports_vision,
            "vision.continuity_check": supports_vision,
            # Audio - Gemini has limited audio support via base models
            "audio.transcribe": self.model_name == "gemini-1.5-pro",
            "audio.synthesize": False,  # Not supported directly
            # Embeddings supported
            "embeddings.generate": True,
            # Not supported by Gemini
            "audio.analyze": False,
            "music.generate": False,
            "image.generate": False,  # Dall-E style not supported
            "image.edit": False,
            "video.generate": False,
        }
        return supported.get(capability, False)

    def get_capabilities(self) -> ModelInfo:
        """Return model metadata and capability flags."""
        supports_vision = self.model_name in {"gemini-1.5-pro", "gemini-1.5-flash"}

        cap_list = [
            "text.generate",
            "text.reason" if self.model_name in {"gemini-1.5-pro"} else None,
            "text.structured",
            "text.translate",
            "text.summarize",
        ]
        # Filter None and add vision if supported
        cap_list = [c for c in cap_list if c is not None]
        if supports_vision:
            cap_list.extend([
                "vision.understand",
                "vision.ocr_assist",
                "vision.panel_analysis",
                "vision.continuity_check",
            ])

        # Add embeddings always
        if "embeddings.generate" not in cap_list:
            cap_list.append("embeddings.generate")

        ctx_map = {
            "gemini-1.5-pro": 1_000_000,  # 1M token context
            "gemini-1.5-flash": 1_000_000,
        }
        context_window = ctx_map.get(self.model_name, 1_000_000)

        return ModelInfo(
            model_id=self.model_name,
            provider_id=self.provider_id,
            upstream_model_id=self.model_name,
            display_name=self.display_name,
            capabilities=cap_list,
            modalities_in=["text"] + (["image"] if supports_vision else []),
            modalities_out=["text"],
            context_window=context_window,
            output_limit=8192,
            supports_streaming=True,
            supports_structured=True,
            supports_tools=False,
            pricing_input_per_million=Decimal("0.35") if self.model_name == "gemini-1.5-flash" else Decimal("7.0"),
            pricing_output_per_million=Decimal("1.05") if self.model_name == "gemini-1.5-flash" else Decimal("21.0"),
            free_tier=False,  # Gemini has limited free tier/credits
            commercial_use=False,  # Must verify per use case / Google AI Studio
            privacy_retention="google_policy",
            health_status=HealthStatus.HEALTHY,
        )

    # --- Request execution ---

    async def execute(self, request: NormalizedRequest) -> NormalizedResponse:
        """Execute a normalized request against Gemini API."""
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
                    f"Capability '{capability}' not supported by Gemini adapter"
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
            logger.error(f"Gemini execution failed: {e}", exc_info=True)
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                raise RateLimitError(f"Gemini rate limited: {e}")
            elif ("authentication" in error_str or "invalid" in error_str or "401" in error_str) and self.api_key:
                raise AuthenticationError(f"Gemini auth failed: {e}")
            elif "timeout" in error_str:
                raise TransientError(f"Gemini timeout: {e}")
            else:
                raise TransientError(f"Gemini generation failed: {e}")

    async def _execute_text_generation(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute text generation via Gemini generative API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Gemini uses: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={apiKey}
            url = f"{self.endpoint_url}/models/{self.model_name}:generateContent?key={self.api_key}"

            contents = []
            if request.system_prompt:
                contents.append({"role": "user", "parts": [{"text": request.system_prompt}]})
            contents.append({"role": "user", "parts": [{"text": request.prompt}]})

            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": request.temperature,
                    "maxOutputTokens": request.max_tokens,
                    "responseMimeType": "text/plain",
                },
            }

            res = await client.post(url, json=payload)

            if res.status_code != 200:
                error_detail = res.text
                if "429" in str(res.status_code) or "rate" in error_detail.lower():
                    raise RateLimitError(f"Gemini rate limited: {error_detail}")
                raise TransientError(f"Gemini generation failed: HTTP {res.status_code}: {error_detail}")

            data = res.json()
            # Extract text from response
            if data.get("candidates") and data["candidates"][0].get("content"):
                parts = data["candidates"][0]["content"].get("parts", [])
                text_parts = [p.get("text", "") for p in parts if p.get("text")]
                return "".join(text_parts).strip()
            else:
                raise TransientError(f"Gemini no response candidates: {data}")

    async def _execute_structured_output(self, request: NormalizedRequest, attempt_history: list) -> dict:
        """Execute structured output via Gemini with response schema."""
        schema = request.output_schema or {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.endpoint_url}/models/{self.model_name}:generateContent?key={self.api_key}"

            # Gemini structured output via response MIME type
            contents = []
            if request.system_prompt:
                contents.append({"role": "user", "parts": [{"text": request.system_prompt}]})
            contents.append({"role": "user", "parts": [{"text": request.prompt}]})

            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": request.temperature,
                    "maxOutputTokens": request.max_tokens,
                    "responseMimeType": "application/json",
                },
            }

            res = await client.post(url, json=payload)

            if res.status_code != 200:
                raise TransientError(f"Gemini structured failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            if data.get("candidates") and data["candidates"][0].get("content"):
                parts = data["candidates"][0]["content"].get("parts", [])
                text_parts = [p.get("text", "") for p in parts if p.get("text")]
                raw_json = "".join(text_parts).strip()
                return json.loads(raw_json)
            else:
                raise TransientError(f"Gemini structured no response: {data}")

    async def _execute_vision_task(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute vision task via Gemini with image input."""
        # Gemini vision: embed image as base64 in the content
        image_base64 = None
        if request.input_modalities and "image" in request.input_modalities:
            # In full implementation, resolve image from input_refs/project storage
            # For now, placeholder - caller should provide base64
            image_base64 = ""

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.endpoint_url}/models/{self.model_name}:generateContent?key={self.api_key}"

            # Build multimodal content
            text_part = request.prompt
            image_part = (
                {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}}
                if image_base64
                else None
            )

            contents = [
                {
                    "role": "user",
                    "parts": [
                        {"text": text_part},
                    ]
                    + ([image_part] if image_part else [])
                }
            ]

            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": request.temperature,
                    "maxOutputTokens": request.max_tokens,
                },
            }

            res = await client.post(url, json=payload)

            if res.status_code != 200:
                raise TransientError(f"Gemini vision failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            if data.get("candidates") and data["candidates"][0].get("content"):
                parts = data["candidates"][0]["content"].get("parts", [])
                text_parts = [p.get("text", "") for p in parts if p.get("text")]
                return "".join(text_parts).strip()
            else:
                raise TransientError(f"Gemini vision no response: {data}")

    async def _execute_embeddings(self, request: NormalizedRequest, attempt_history: list) -> list:
        """Execute embeddings generation via Gemini."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.endpoint_url}/models/{self.model_name}:getEmbedding?key={self.api_key}"

            payload = {"input": request.prompt}

            res = await client.post(url, json=payload)

            if res.status_code != 200:
                raise TransientError(f"Gemini embeddings failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            # Gemini embedding response format
            if data.get("embedding"):
                return data["embedding"]
            elif data.get("values"):
                return data["values"]
            else:
                raise TransientError(f"Gemini embeddings unexpected format: {data}")

    # --- Response building ---

    def _build_response(
        self,
        result: Any,
        provider_id: str,
        model_id: str,
        attempt_history: list,
        latency_ms: int,
    ) -> NormalizedResponse:
        """Build a NormalizedResponse from raw Gemini result."""
        from engine.ai_gateway.contracts import FinishStatus

        # Determine status
        if attempt_history and attempt_history[-1].status == FinishStatus.FAILED:
            status = FinishStatus.FAILED
        else:
            status = FinishStatus.SUCCESS

        # Extract tokens from usage if available
        input_tokens = None
        output_tokens = None
        cost_estimate = Decimal("0.0")
        cost_actual = Decimal("0.0")

        if isinstance(result, str):
            output_tokens = max(1, len(result) // 4)  # rough estimate

        # Cost calculation based on model pricing
        # gemini-1.5-flash: $0.00035/$0.00105 per 1K tokens
        # gemini-1.5-pro: $0.007/$0.021 per 1K tokens
        if input_tokens and output_tokens:
            if model_id == "gemini-1.5-flash":
                cost_actual = Decimal(
                    str(round((input_tokens / 1000) * 0.00035 + (output_tokens / 1000) * 0.00105, 6))
                )
            elif model_id == "gemini-1.5-pro":
                cost_actual = Decimal(
                    str(round((input_tokens / 1000) * 0.007 + (output_tokens / 1000) * 0.021, 6))
                )
            else:
                cost_actual = Decimal("0.0")

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
        """Return latency - in practice measured from request timings."""
        return 0

    def normalize_request(self, request: NormalizedRequest) -> Dict[str, Any]:
        """Convert normalized request to Gemini-specific payload."""
        # Build contents array
        contents = []

        # System prompt if provided
        if request.system_prompt:
            contents.append({"role": "user", "parts": [{"text": request.system_prompt}]})

        # User prompt
        contents.append({"role": "user", "parts": [{"text": request.prompt}]})

        # Add image for vision tasks
        if request.capability.value.startswith("vision.") and request.input_modalities and "image" in request.input_modalities:
            # In full implementation, encode image from input_refs
            # Placeholder - caller provides base64
            contents[-1]["parts"].append(
                {"inline_data": {"mime_type": "image/jpeg", "data": ""}}
            )

        payload: Dict[str, Any] = {
            "model": request.model_overrides.get("model", self.model_name),
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "stream": False,
            },
        }

        # Add structured output config if requested
        if request.output_schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        return payload

    def normalize_response(self, raw_response: Dict[str, Any], request: NormalizedRequest) -> NormalizedResponse:
        """Convert Gemini's raw API response to NormalizedResponse."""
        from engine.ai_gateway.contracts import FinishStatus, AttemptResult

        # Check for errors
        if raw_response.get("error"):
            error_msg = raw_response["error"].get("message", "Unknown Gemini error")
            # Try to extract status code
            status_code = raw_response["error"].get("status", "")
            if "429" in str(status_code) or "rate" in error_msg.lower():
                raise RateLimitError(f"Gemini rate limited: {error_msg}")
            raise AuthenticationError(f"Gemini auth failed: {error_msg}")

        # Success case - extract response text
        candidates = raw_response.get("candidates", [])
        if candidates and candidates[0].get("content"):
            parts = candidates[0]["content"].get("parts", [])
            text_parts = [p.get("text", "") for p in parts if p.get("text")]
            response_text = "".join(text_parts).strip()
        else:
            response_text = raw_response.get("text", "")

        # Extract usage
        usage = raw_response.get("usage", {})
        input_tokens = usage.get("prompt_token_count", 0) or usage.get("input_token_count", 0)
        output_tokens = usage.get("candidates_tool_output_token_count", 0) or usage.get("output_token_count", 0)

        # Estimate latency (would be measured in practice)
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
            provider_request_id=raw_response.get("responseId", ""),
            trace_id=request.trace_id,
        )

    @staticmethod
    def _calculate_cost(input_tokens: int, output_tokens: int, model: str) -> Decimal:
        """Estimate cost for Gemini model usage."""
        pricing = {
            "gemini-1.5-flash": (
                Decimal("0.00035"),
                Decimal("0.00105"),
            ),  # input, output per 1K
            "gemini-1.5-pro": (Decimal("0.007"), Decimal("0.021")),
        }
        inp, out = pricing.get(model, (Decimal("0.007"), Decimal("0.021")))
        cost = (Decimal(input_tokens) / 1000) * inp + (Decimal(output_tokens) / 1000) * out
        return cost


# Global instance for gateway integration
gemini_adapter = GeminiAdapter()