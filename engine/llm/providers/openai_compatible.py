import base64
import json
import logging
from pathlib import Path
from typing import TypeVar, Type, Any
import httpx
from pydantic import BaseModel, ValidationError

from engine.llm.providers.base import LLMProvider, ModelMetadata

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger("panelflow.llm.openai_compatible")

class OpenAICompatibleProvider(LLMProvider):
    """
    Generic adapter for OpenAI-compatible local/remote endpoints (LM Studio, vLLM, LocalAI, llama.cpp).
    Uses /v1/chat/completions.
    """

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:1234/v1",
        model_name: str = "default",
        api_key: str = "local-no-key",
        timeout: float = 60.0,
        provider_id: str = "openai_compatible",
        display_name: str | None = None,
    ):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout
        self._provider_id = provider_id
        self._display_name = display_name or f"OpenAI-Compatible ({self.endpoint_url})"

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def display_name(self) -> str:
        return self._display_name

    async def health_check(self) -> bool:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{self.endpoint_url}/models",
                    headers=headers,
                )
                return res.status_code == 200
        except Exception:
            return False

    async def list_available_models(self) -> list[str]:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(
                    f"{self.endpoint_url}/models",
                    headers=headers,
                )
                if res.status_code == 200:
                    data = res.json()
                    models = []
                    for item in data.get("data", []):
                        m_id = item.get("id")
                        if m_id:
                            models.append(m_id)
                    return models
        except Exception as e:
            logger.warning(f"Failed to list models from {self.endpoint_url}: {e}")
        return []

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        model_to_use = kwargs.get("model") or self.model_name
        payload = {
            "model": model_to_use,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if res.status_code != 200:
                raise RuntimeError(f"OpenAI-compatible generation failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            return data["choices"][0]["message"]["content"].strip()

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_repair_retries: int = 2,
        **kwargs
    ) -> T:
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        system_instruction = (
            (system_prompt or "You are a precise narrative structure analysis engine.") +
            f"\n\nYou MUST respond ONLY with valid JSON conforming to this JSON schema:\n{schema_json}\n"
            "Do NOT include markdown fences, comments, or preamble. Return raw JSON only."
        )

        current_prompt = prompt
        last_error = ""

        for attempt in range(max_repair_retries + 1):
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": current_prompt},
            ]

            model_to_use = kwargs.get("model") or self.model_name
            payload = {
                "model": model_to_use,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(
                    f"{self.endpoint_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if res.status_code != 200:
                    raise RuntimeError(f"Structured generation failed: HTTP {res.status_code}: {res.text}")

                data = res.json()
                raw_json = data["choices"][0]["message"]["content"].strip()

            try:
                parsed = json.loads(raw_json)
                return response_model.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = str(e)
                logger.warning(f"Structured validation failed on attempt {attempt + 1}: {e}")
                if attempt < max_repair_retries:
                    current_prompt = (
                        f"Previous response was invalid:\n{raw_json}\n\n"
                        f"Validation error:\n{last_error}\n\n"
                        f"Please fix the JSON to strictly conform to schema. Original request was:\n{prompt}"
                    )
                else:
                    break

        raise ValueError(
            f"Failed to generate structured data for {response_model.__name__} after "
            f"{max_repair_retries + 1} attempts. Last error: {last_error}"
        )

    async def analyze_vision(
        self,
        image: Path | bytes,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ) -> str:
        if isinstance(image, Path):
            with open(image, "rb") as f:
                img_bytes = f.read()
        else:
            img_bytes = image

        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64_img}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        })

        model_to_use = kwargs.get("model") or self.model_name
        payload = {
            "model": model_to_use,
            "messages": messages,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(
                f"{self.endpoint_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if res.status_code != 200:
                raise RuntimeError(f"Vision analysis failed: HTTP {res.status_code}: {res.text}")

            data = res.json()
            return data["choices"][0]["message"]["content"].strip()

    def context_window(self) -> int:
        return 16384

    def model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_id=self.provider_id,
            model_name=self.model_name,
            supports_vision=True,
            supports_structured=True,
            context_window=self.context_window(),
            endpoint=self.endpoint_url,
        )


class LMStudioProvider(OpenAICompatibleProvider):
    """Convenience adapter specifically configured for LM Studio local server."""

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:1234/v1",
        model_name: str = "default",
        timeout: float = 60.0,
    ):
        super().__init__(endpoint_url=endpoint_url, model_name=model_name, timeout=timeout)

    @property
    def provider_id(self) -> str:
        return "lmstudio"

    @property
    def display_name(self) -> str:
        return f"LM Studio Local ({self.endpoint_url})"
