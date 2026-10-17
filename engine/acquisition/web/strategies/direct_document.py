"""
Direct resource detection strategy (Stage 1).
Handles direct single-image links, archives, and documents without spinning up browser infrastructure.
"""
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from pathlib import Path
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.discovery.page_classifier import IMAGE_EXTENSIONS, ARCHIVE_EXTENSIONS


class DirectDocumentStrategy(BaseExtractionStrategy):
    @property
    def strategy_id(self) -> str:
        return "DIRECT_DOCUMENT"

    async def extract(
        self,
        url: str,
        html_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        start_t = time.perf_counter()
        parsed = urlparse(url)
        path_lower = parsed.path.lower()

        # Check if direct image extension
        for ext in IMAGE_EXTENSIONS:
            if path_lower.endswith(ext):
                elapsed = (time.perf_counter() - start_t) * 1000
                stem = Path(parsed.path).stem or "direct_page"
                candidate = ImageCandidate(
                    url=url,
                    resolved_url=url,
                    dom_order=1,
                    title=stem,
                    content_score=1.0,
                    score_reasons=["direct-image-resource-url"],
                    source_strategies={self.strategy_id},
                )
                return StrategyResult(
                    strategy_id=self.strategy_id,
                    status="SUCCESS",
                    candidates=[candidate],
                    metadata={"resource_type": "DIRECT_IMAGE", "filename": f"{stem}{ext}"},
                    confidence=1.0,
                    elapsed_ms=round(elapsed, 2),
                )

        # Check if archive
        for ext in ARCHIVE_EXTENSIONS:
            if path_lower.endswith(ext):
                elapsed = (time.perf_counter() - start_t) * 1000
                return StrategyResult(
                    strategy_id=self.strategy_id,
                    status="NOT_APPLICABLE",
                    candidates=[],
                    metadata={"resource_type": "ARCHIVE", "format": ext},
                    confidence=1.0,
                    elapsed_ms=round(elapsed, 2),
                    failure_reason="URL is a downloadable archive; hand off to archive pipeline",
                )

        elapsed = (time.perf_counter() - start_t) * 1000
        return StrategyResult(
            strategy_id=self.strategy_id,
            status="NOT_APPLICABLE",
            candidates=[],
            confidence=0.0,
            elapsed_ms=round(elapsed, 2),
            failure_reason="URL is not a direct image or document resource",
        )
