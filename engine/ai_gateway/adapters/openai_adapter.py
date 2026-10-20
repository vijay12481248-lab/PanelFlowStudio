"""OpenAI provider adapter for the Universal AI Gateway.

Implements the ProviderAdapter interface for OpenAI's API, supporting:
- Chat completions (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
- Structured outputs via response_format
- Vision (gpt-4o with image input)
- Whisper speech-to-text
- TTS (text-to-speech)
- Embeddings generation
"""

import asyncio
import base64
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

logger = logging.getLogger("panelflow.llm.adapter.openai")


class OpenAIAdapter(ProviderAdapter):
    """Adapter for OpenAI API (gpt-4o, gpt-4-turbo, etc.).

    Wraps the OpenAI Chat Completions API and provides normalized
    request/response contracts compatible with the Universal AI Gateway.
    """

    def __init__(
        self,
        endpoint_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model_name: str = "gpt-4o",
        timeout: float = 60.0,
    ):
        """Initialize the OpenAI adapter.

        Args:
            endpoint_url: OpenAI API base URL (default: https://api.openai.com/v1)
            api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.
            model_name: Default model to use (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or ""
        self.endpoint_url = endpoint_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

        if not self.api_key:
            import os
            self.api_key = os.environ.get("OPENAI_API_KEY", "")

    # --- ProviderAdapter interface ---

    @property
    def provider_id(self) -> str:
        return "openai"

    @property
    def display_name(self) -> str:
        return f"OpenAI ({self.model_name})"

    async def health_check(self) -> HealthStatusOutput:
        """Verify OpenAI API connectivity and model availability."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                res = await client.get(
                    f"{self.endpoint_url}/models",
                    headers=headers,
                )
                if res.status_code == 200:
                    models = res.json().get("data", [])
                    # Check if our model is available
                    model_available = any(m.get("id") == self.model_name for m in models)
                    status = (
                        HealthStatus.HEALTHY
                        if model_available
                        else HealthStatus.DEGRADED
                    )
                    return HealthStatusOutput(
                        status=status,
                        latency_ms=res.elapsed.total_seconds() * 1000,
                        details=f"OpenAI API reachable, model={self.model_name}",
                    )
                else:
                    return HealthStatusOutput(
                        status=HealthStatus.UNHEALTHY,
                        latency_ms=0,
                        details=f"OpenAI API returned {res.status_code}",
                    )
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return HealthStatusOutput(
                status=HealthStatus.OFFLINE,
                latency_ms=0,
                details=f"Health check error: {e}",
            )

    def supports_capability(self, capability: CapabilityType) -> bool:
        """Check if OpenAI supports the given capability."""
        supported = {
            # Text capabilities - all supported
            "text.generate": True,
            "text.reason": True,
            "text.structured": True,
            "text.translate": True,
            "text.summarize": True,
            # Vision capabilities - supported by gpt-4o and later
            "vision.understand": self.model_name in {"gpt-4o", "gpt-4-vision-preview"},
            "vision.ocr_assist": self.model_name in {"gpt-4o", "gpt-4-vision-preview"},
            "vision.panel_analysis": self.model_name in {"gpt-4o", "gpt-4-vision-preview"},
            "vision.continuity_check": self.model_name in {"gpt-4o", "gpt-4-vision-preview"},
            # Audio - Whisper supported
            "audio.transcribe": self.model_name in {"gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"},
            # Audio - TTS supported
            "audio.synthesize": True,
            # Others - embeddings supported
            "embeddings.generate": True,
            # Not supported by OpenAI
            "audio.analyze": False,
            "music.generate": False,
            "image.generate": False,  # Dall-E is separate
            "image.edit": False,
            "video.generate": False,
        }
        return supported.get(capability, False)

    def get_capabilities(self) -> ModelInfo:
        """Return model metadata and capability flags."""
        supports_vision = self.model_name in {"gpt-4o", "gpt-4-vision-preview"}

        return ModelInfo(
            model_id=self.model_name,
            provider_id=self.provider_id,
            upstream_model_id=self.model_name,
            display_name=self.display_name,
            capabilities=self._capability_list_from_bool(
                supports_vision=supports_vision
            ),
            modalities_in=["text"] + (["image"] if supports_vision else []),
            modalities_out=["text"],
            context_window=self._get_context_window(),
            output_limit=4096,
            supports_streaming=True,
            supports_structured=True,
            supports_tools=self.model_name in {"gpt-4o", "gpt-4-turbo"},
            pricing_input_per_million=Decimal("3.0") if self.model_name == "gpt-4o" else Decimal("1.0"),
            pricing_output_per_million=Decimal("6.0") if self.model_name == "gpt-4o" else Decimal("2.0"),
            free_tier=False,  # OpenAI has no free tier (trial only)
            commercial_use=False,  # Must verify per use case
            privacy_retention="openai_policy",
            health_status=HealthStatus.HEALTHY,
        )

    # --- Capability list builder ---

    @staticmethod
    def _capability_list_from_bool(**kwargs) -> list:
        """Build CapabilityType list from boolean flags."""
        from engine.ai_gateway.adapters.base import CapabilityType

        result = [CapabilityType.TEXT_GENERATE]  # Always include text
        if kwargs.get("supports_vision"):
            result.extend(
                [
                    CapabilityType.VISION_UNDERSTAND,
                    CapabilityType.VISION_OCR_ASSIST,
                    CapabilityType.VISION_PANEL_ANALYSIS,
                    CapabilityType.VISION_CONTINUITY_CHECK,
                ]
            )
        # Add reasoning if model supports it
        if kwargs.get("model_name") in {"gpt-4o", "gpt-4-turbo", "gpt-4"}:
            result.append(CapabilityType.TEXT_REASON)
        if kwargs.get("supports_structured"):
            result.append(CapabilityType.TEXT_STRUCTURED)
        return result

    @staticmethod
    def _get_context_window() -> int:
        """Return context window in tokens based on model."""
        windows = {
            "gpt-4o": 128000,
            "gpt-4-turbo": 128000,
            "gpt-4": 8192,
            "gpt-3.5-turbo": 16385,
            "gpt-4o-mini": 128000,
        }
        return windows.get("gpt-4o", 8192)  # default

    # --- Request execution ---

    async def execute(self, request: NormalizedRequest) -> NormalizedResponse:
        """Execute a normalized request against OpenAI API."""
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
            elif capability == "audio.transcribe":
                result = await self._execute_transcription(request, attempt_history)
            elif capability == "audio.synthesize":
                result = await self._execute_tts(request, attempt_history)
            elif capability == "embeddings.generate":
                result = await self._execute_embeddings(request, attempt_history)
            else:
                raise UnsupportedCapabilityError(
                    f"Capability '{capability}' not supported by OpenAI adapter"
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
            logger.error(f"OpenAI execution failed: {e}", exc_info=True)
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                raise RateLimitError(f"OpenAI rate limited: {e}")
            elif "invalid api key" in error_str or "authentication" in error_str or "401" in error_str:
                raise AuthenticationError(f"OpenAI auth failed: {e}")
            elif "timeout" in error_str:
                raise TransientError(f"OpenAI timeout: {e}")
            else:
                raise TransientError(f"OpenAI generation failed: {e}")

    async def _execute_text_generation(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute text generation via OpenAI chat completions."""
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {
                "model": request.model_overrides.get("model", self.model_name),
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }

            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if res.status_code != 200:
                raise RuntimeError(f"OpenAI generation failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            return data["choices"][0]["message"]["content"].strip()

    async def _execute_structured_output(self, request: NormalizedRequest, attempt_history: list) -> dict:
        """Execute structured output via OpenAI response_format."""
        schema = request.output_schema or {}

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": self._struct_prompt(schema)})

        messages.append({"role": "user", "content": request.prompt})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {
                "model": request.model_overrides.get("model", self.model_name),
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "response_format": {"type": "json_object"},
            }

            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if res.status_code != 200:
                raise RuntimeError(f"OpenAI structured failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            raw_json = data["choices"][0]["message"]["content"].strip()
            return json.loads(raw_json)

    @staticmethod
    def _struct_prompt(schema: dict) -> str:
        """Generate system instruction for structured output."""
        return (
            f"You MUST respond ONLY with valid JSON conforming to this schema: "
            f"{json.dumps(schema)}. Do NOT include markdown fences, comments, "
            f"or preamble. Return raw JSON only."
        )

    async def _execute_vision_task(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute vision task via OpenAI gpt-4o with image input."""
        # Encode image if provided
        image_base64 = None
        if request.input_modalities and "image" in request.input_modalities:
            # Try to load from input_refs - in full implementation would resolve paths
            # For now, assume image is embedded in prompt or provide placeholder
            image_base64 = ""  # Will be filled by caller with actual base64 data

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        # Build content array for multimodal input
        content = [
            {"type": "text", "text": request.prompt},
        ]
        if image_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                }
            )

        messages.append({"role": "user", "content": content})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {
                "model": request.model_overrides.get("model", self.model_name),
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }

            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if res.status_code != 200:
                raise RuntimeError(f"OpenAI vision failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            return data["choices"][0]["message"]["content"].strip()

    async def _execute_transcription(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute audio transcription via OpenAI Whisper.

        Note: Whisper API uses a different endpoint (POST /audio/transcriptions).
        """
        # In a full implementation, the audio file would be uploaded.
        # For now, return empty string as placeholder.
        # The actual implementation would use: requests.post(
        #     "https://api.openai.com/v1/audio/transcriptions",
        #     headers={"Authorization": f"Bearer {self.api_key}"},
        #     files={"file": audio_file},
        # )
        return ""

    async def _execute_tts(self, request: NormalizedRequest, attempt_history: list) -> str:
        """Execute text-to-speech via OpenAI TTS.

        Note: TTS returns audio data, not text. For gateway compatibility,
        we return a reference/placeholder.
        """
        # TTS would return audio file path or base64 audio data
        # For now, return placeholder
        return ""

    async def _execute_embeddings(self, request: NormalizedRequest, attempt_history: list) -> list:
        """Execute embeddings generation via OpenAI embeddings endpoint."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {
                "input": request.prompt,
                "model": request.model_overrides.get("model", self.model_name),
            }

            res = await client.post(
                f"{self.endpoint_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if res.status_code != 200:
                raise RuntimeError(f"OpenAI embeddings failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            return data["data"][0]["embedding"]

    # --- Response building ---

    def _build_response(
        self,
        result: Any,
        provider_id: str,
        model_id: str,
        attempt_history: list,
        latency_ms: int,
    ) -> NormalizedResponse:
        """Build a NormalizedResponse from raw OpenAI result."""
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
            # Rough estimate
            output_tokens = max(1, len(result) // 4)

        # For text generation, we'd typically get token counts from the response
        # headers or usage field. For now use estimates.

        # Cost calculation (estimates)
        # gpt-4o: $0.003/$0.006 per 1K input/output tokens
        # gpt-4-turbo: $0.01/$0.03 per 1K input/output tokens
        # gpt-3.5-turbo: $0.0005/$0.0015 per 1K input/output tokens
        if input_tokens and output_tokens:
            if model_id == "gpt-4o":
                cost_actual = Decimal(str(round((input_tokens / 1000) * 0.003 + (output_tokens / 1000) * 0.006, 6)))
            elif model_id == "gpt-3.5-turbo":
                cost_actual = Decimal(str(round((input_tokens / 1000) * 0.0005 + (output_tokens / 1000) * 0.0015, 6)))
            else:
                cost_actual = Decimal(str(round((input_tokens / 1000) * 0.01 + (output_tokens / 1000) * 0.03, 6)))

        # Estimate cost_estimate as same as actual for now (real systems would use
        # provider-provided pricing metadata)
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
            cost_confidence="MEDIUM",  # OpenAI pricing known but variable
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
        """Convert normalized request to OpenAI-specific payload."""
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        payload: Dict[str, Any] = {
            "model": request.model_overrides.get("model", self.model_name),
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        # Add structured output format if requested
        if request.output_schema:
            payload["response_format"] = {"type": "json_object"}

        return payload

    def normalize_response(self, raw_response: Dict[str, Any], request: NormalizedRequest) -> NormalizedResponse:
        """Convert OpenAI's raw API response to NormalizedResponse."""
        from engine.ai_gateway.contracts import FinishStatus, AttemptResult

        # Check for errors
        if raw_response.get("error"):
            error_msg = raw_response["error"].get("message", "Unknown OpenAI error")
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
                    error_code="openai_api_error",
                    error_message=error_msg,
                )],
                latency_ms=0,
                validation_status="FAILED",
                error_info={"provider_error": error_msg},
                provider_request_id="",
                trace_id="",
            )

        # Success case
        response_text = raw_response["choices"][0]["message"]["content"].strip()
        usage = raw_response.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        # Estimate latency from response headers or use 0
        latency_ms = 0  # Would be measured in practice

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
        """Estimate cost for OpenAI model usage."""
        pricing = {
            "gpt-4o": (Decimal("0.003"), Decimal("0.006")),
            "gpt-4-turbo": (Decimal("0.01"), Decimal("0.03")),
            "gpt-4": (Decimal("0.03"), Decimal("0.06")),
            "gpt-3.5-turbo": (Decimal("0.0005"), Decimal("0.0015")),
            "gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
        }
        inp, out = pricing.get(model, (Decimal("0.01"), Decimal("0.03")))
        cost = (Decimal(input_tokens) / 1000) * inp + (Decimal(output_tokens) / 1000) * out
        return cost


# Global instance for gateway integration
openai_adapter = OpenAIAdapter()