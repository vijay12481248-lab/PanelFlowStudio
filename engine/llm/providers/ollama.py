import base64
import json
import logging
from pathlib import Path
from typing import TypeVar, Type, Any
import httpx
from pydantic import BaseModel, ValidationError

from engine.llm.providers.base import LLMProvider, ModelMetadata

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger("panelflow.llm.ollama")

class OllamaProvider(LLMProvider):
    """
    Adapter for local Ollama instance (http://127.0.0.1:11434).
    Supports local text models (e.g. qwen3.5, llama3, mistral)
    and vision models (e.g. qwen3.5:9b, gemma4, llava).
    """

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:11434",
        text_model: str = "qwen3.5:9b",
        vision_model: str = "qwen3.5:9b",
        timeout: float = 120.0,
        num_ctx: int = 4096,
    ):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.text_model = text_model
        self.vision_model = vision_model
        self.timeout = timeout
        self.num_ctx = num_ctx

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return f"Ollama Local ({self.text_model})"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.endpoint_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def list_available_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.endpoint_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            pass
        return []

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs
    ) -> str:
        payload = {
            "model": self.text_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.endpoint_url}/api/generate", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama text generation failed: HTTP {res.status_code}: {res.text}")
            return res.json().get("response", "").strip()

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_repair_retries: int = 2,
        **kwargs
    ) -> T:
        schema_dict = response_model.model_json_schema()
        schema_json = json.dumps(schema_dict, indent=2)
        system_instruction = (
            (system_prompt or "You are a precise narrative structure analysis engine.") +
            f"\n\nYou MUST respond ONLY with valid JSON conforming to this JSON schema:\n{schema_json}\n"
            "Do NOT include markdown fences, comments, or preamble. Return raw JSON only."
        )

        current_prompt = prompt
        last_error = ""

        for attempt in range(max_repair_retries + 1):
            payload = {
                "model": self.text_model,
                "prompt": current_prompt,
                "system": system_instruction,
                "format": schema_dict,
                "think": False,
                "thinking": False,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_ctx": self.num_ctx,
                    "think": False,
                    "thinking": False,
                    "num_predict": kwargs.get("max_tokens", 1536),
                },
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.endpoint_url}/api/generate", json=payload)
                if res.status_code != 200 and isinstance(payload.get("format"), dict):
                    payload["format"] = "json"
                    res = await client.post(f"{self.endpoint_url}/api/generate", json=payload)

                if res.status_code != 200:
                    raise RuntimeError(f"Ollama structured generation failed: HTTP {res.status_code}: {res.text}")

                raw_json = res.json().get("response", "").strip()

            try:
                # Parse JSON
                parsed = json.loads(raw_json)
                # Validate Pydantic schema
                return response_model.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = str(e)
                logger.warning(f"Ollama JSON validation failed on attempt {attempt + 1}: {e}")
                if attempt < max_repair_retries:
                    # Construct repair prompt
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

        payload = {
            "model": self.vision_model,
            "prompt": prompt,
            "images": [b64_img],
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.endpoint_url}/api/generate", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama vision analysis failed: HTTP {res.status_code}: {res.text}")
            return res.json().get("response", "").strip()

    def context_window(self) -> int:
        return 32768

    def model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_id=self.provider_id,
            model_name=self.text_model,
            supports_vision=True,
            supports_structured=True,
            context_window=self.context_window(),
            endpoint=self.endpoint_url,
            extra={"vision_model": self.vision_model},
        )
