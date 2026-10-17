from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeVar, Type, Any
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)

class ModelMetadata(BaseModel):
    provider_id: str
    model_name: str
    supports_vision: bool = False
    supports_structured: bool = True
    context_window: int = 8192
    endpoint: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

class LLMProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier (e.g. 'ollama', 'lmstudio', 'openai_compatible', 'mock_llm')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifies endpoint connectivity and model availability."""
        pass

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs
    ) -> str:
        """Generates raw text response."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_repair_retries: int = 2,
        **kwargs
    ) -> T:
        """Generates validated structured response adhering to Pydantic schema with repair retry loop."""
        pass

    @abstractmethod
    async def analyze_vision(
        self,
        image: Path | bytes,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ) -> str:
        """Analyzes image with multimodal prompt."""
        pass

    @abstractmethod
    def context_window(self) -> int:
        """Returns max input context window in tokens."""
        pass

    @abstractmethod
    def model_metadata(self) -> ModelMetadata:
        """Returns active model metadata and capability flags."""
        pass
