import json
import logging
from pathlib import Path
from typing import TypeVar, Type, Any
from pydantic import BaseModel

from engine.llm.providers.base import LLMProvider, ModelMetadata

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger("panelflow.llm.mock")

class MockLLMProvider(LLMProvider):
    """
    Deterministic Mock LLM Provider for offline testing, CI gates, and unit benchmarks.
    Never calls external network endpoints.
    """

    def __init__(self, model_name: str = "mock-story-v1", simulate_failure: bool = False):
        self.model_name = model_name
        self.simulate_failure = simulate_failure
        self.call_history: list[dict[str, Any]] = []

    @property
    def provider_id(self) -> str:
        return "mock_llm"

    @property
    def display_name(self) -> str:
        return f"Mock Deterministic LLM ({self.model_name})"

    async def health_check(self) -> bool:
        return not self.simulate_failure

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs
    ) -> str:
        self.call_history.append({"type": "text", "prompt": prompt})
        if self.simulate_failure:
            raise RuntimeError("Simulated Mock LLM failure")
        return "The crystal conduit pulsed with ancient resonance as the traveler stepped into the chamber."

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_repair_retries: int = 2,
        **kwargs
    ) -> T:
        self.call_history.append({"type": "structured", "prompt": prompt, "model": response_model.__name__})
        if self.simulate_failure:
            raise RuntimeError("Simulated Mock LLM failure in structured generation")

        # Create a deterministic instance based on model fields
        fields_data = {}
        for field_name, field_info in response_model.model_fields.items():
            annotation = field_info.annotation
            origin = getattr(annotation, "__origin__", None)

            if origin is list:
                fields_data[field_name] = []
            elif origin is dict:
                fields_data[field_name] = {}
            elif annotation is str:
                fields_data[field_name] = f"mock_{field_name}"
            elif annotation is int:
                fields_data[field_name] = 1
            elif annotation is float:
                fields_data[field_name] = 0.95
            elif annotation is bool:
                fields_data[field_name] = True
            elif hasattr(annotation, "__members__"):
                # Enum
                fields_data[field_name] = list(annotation.__members__.values())[0].value
            else:
                fields_data[field_name] = None

        try:
            return response_model.model_validate(fields_data)
        except Exception:
            # Fallback to empty construct if partial
            return response_model.model_construct(**fields_data)

    async def analyze_vision(
        self,
        image: Path | bytes,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ) -> str:
        self.call_history.append({"type": "vision", "prompt": prompt})
        if self.simulate_failure:
            raise RuntimeError("Simulated Mock LLM vision failure")
        return "A solitary figure in an ivory coat observing a glowing crystal prism inside a cavernous stone structure."

    def context_window(self) -> int:
        return 32768

    def model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_id=self.provider_id,
            model_name=self.model_name,
            supports_vision=True,
            supports_structured=True,
            context_window=32768,
            endpoint="local://mock",
        )
