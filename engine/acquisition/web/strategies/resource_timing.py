"""
Resource Timing API strategy (Stage 12).
Queries performance.getEntriesByType("resource") to collect loaded image and fetch resources.
"""
import time
from typing import Optional, Dict, Any, List
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.discovery.candidate_collector import normalize_image_url
from engine.acquisition.web.discovery.page_classifier import IMAGE_EXTENSIONS


class ResourceTimingStrategy(BaseExtractionStrategy):
    @property
    def strategy_id(self) -> str:
        return "RESOURCE_TIMING"

    async def extract(
        self,
        url: str,
        html_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        start_t = time.perf_counter()
        context = context or {}

        mock_resources = context.get("mock_resource_timings")
        if mock_resources is not None:
            return self._process_resources(url, mock_resources, start_t)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="FAILED",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason="Playwright package not installed",
            )

        try:
            from engine.acquisition.web.strategies.browser_utils import launch_chromium_browser
            async with async_playwright() as p:
                browser = await launch_chromium_browser(p, headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=10000)

                # Query performance entries
                entries = await page.evaluate(
                    """() => window.performance.getEntriesByType('resource').map(e => ({
                        name: e.name,
                        initiatorType: e.initiatorType,
                        duration: e.duration
                    }))"""
                )
                await browser.close()
                return self._process_resources(url, entries, start_t)

        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="FAILED",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason=f"Resource timing evaluation failed: {e}",
            )

    def _process_resources(self, base_url: str, entries: List[Dict[str, Any]], start_t: float) -> StrategyResult:
        candidates: List[ImageCandidate] = []
        for idx, entry in enumerate(entries, start=1):
            name = entry.get("name", "")
            initiator = entry.get("initiatorType", "").lower()
            lower_name = name.lower().split("?")[0]

            is_image = initiator == "img" or any(lower_name.endswith(ext) for ext in IMAGE_EXTENSIONS)
            if not is_image:
                continue

            resolved = normalize_image_url(name, base_url)
            cand = ImageCandidate(
                url=name,
                resolved_url=resolved,
                dom_order=idx,
                content_score=0.75,
                score_reasons=[f"performance-resource-timing-entry ({initiator})"],
                source_strategies={self.strategy_id},
            )
            candidates.append(cand)

        elapsed = (time.perf_counter() - start_t) * 1000
        count = len(candidates)
        return StrategyResult(
            strategy_id=self.strategy_id,
            status="SUCCESS" if count >= 2 else "LOW_CONFIDENCE",
            candidates=candidates,
            metadata={"performance_resources_found": count},
            confidence=0.85 if count >= 4 else 0.50,
            elapsed_ms=round(elapsed, 2),
        )
