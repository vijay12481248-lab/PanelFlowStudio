"""
Base strategy interface and StrategyResult model for adaptive chapter extraction.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from engine.acquisition.web.models.image_candidate import ImageCandidate


class StrategyResult(BaseModel):
    strategy_id: str
    status: str  # SUCCESS, LOW_CONFIDENCE, FAILED, ACCESS_RESTRICTED, SKIPPED, NOT_APPLICABLE
    candidates: List[ImageCandidate] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: float = 0.0
    failure_reason: Optional[str] = None


class BaseExtractionStrategy(ABC):
    """
    Abstract base class for all extraction strategies.
    Strategies never throw unhandled exceptions to abort the orchestrator;
    they return a structured StrategyResult.
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        pass

    @abstractmethod
    async def extract(
        self,
        url: str,
        html_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        pass
