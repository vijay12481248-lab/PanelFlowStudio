"""
Browser network observation strategy (Stage 11).
Monitors HTTP requests and responses naturally triggered by the browser during page loading and scrolling.
"""
import time
from typing import Optional, Dict, Any, List
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.discovery.candidate_collector import normalize_image_url
from engine.acquisition.web.discovery.candidate_clusterer import CandidateClusterer
from engine.acquisition.web.discovery.candidate_scorer import CandidateScorer


class BrowserNetworkStrategy(BaseExtractionStrategy):
    def __init__(self):
        self.clusterer = CandidateClusterer()
        self.scorer = CandidateScorer()

    @property
    def strategy_id(self) -> str:
        return "BROWSER_NETWORK"

    async def extract(
        self,
        url: str,
        html_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        start_t = time.perf_counter()
        context = context or {}

        # 1. Check for simulated / mock network responses in context (for unit/integration tests)
        mock_network_events = context.get("mock_network_events")
        if mock_network_events is not None:
            return self._process_network_events(url, mock_network_events, start_t)

        # 2. Real Playwright network monitoring
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

        captured_events: List[Dict[str, Any]] = []

        try:
            from engine.acquisition.web.strategies.browser_utils import launch_chromium_browser
            async with async_playwright() as p:
                browser = await launch_chromium_browser(p, headless=True)
                page = await browser.new_page()

                def handle_response(response):
                    content_type = response.headers.get("content-type", "").lower()
                    if "image/" in content_type:
                        captured_events.append({
                            "url": response.url,
                            "mime_type": content_type,
                            "status": response.status,
                        })

                page.on("response", handle_response)
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)

                # Scroll progressively
                for _ in range(8):
                    await page.evaluate("() => window.scrollBy(0, 1000)")
                    await page.wait_for_timeout(300)

                await browser.close()
                return self._process_network_events(url, captured_events, start_t)

        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="FAILED",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason=f"Playwright network observation error: {e}",
            )

    def _process_network_events(self, base_url: str, events: List[Dict[str, Any]], start_t: float) -> StrategyResult:
        candidates: List[ImageCandidate] = []
        for idx, ev in enumerate(events, start=1):
            raw_u = ev.get("url", "")
            if not raw_u:
                continue
            resolved = normalize_image_url(raw_u, base_url)
            cand = ImageCandidate(
                url=raw_u,
                resolved_url=resolved,
                dom_order=idx,
                mime_type=ev.get("mime_type"),
                source_strategies={self.strategy_id},
            )
            candidates.append(cand)

        if not candidates:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="LOW_CONFIDENCE",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason="No image network responses captured",
            )

        clusters = self.clusterer.cluster_candidates(candidates)
        dominant = clusters[0] if clusters else None
        scored = self.scorer.score_all(candidates, dominant_cluster=dominant)

        accepted = [c for c in scored if c.content_score >= 0.40]
        count = len(accepted)
        conf = 0.96 if count >= 5 else 0.75

        elapsed = (time.perf_counter() - start_t) * 1000
        return StrategyResult(
            strategy_id=self.strategy_id,
            status="SUCCESS" if count >= 2 else "LOW_CONFIDENCE",
            candidates=accepted,
            metadata={"network_images_captured": count},
            confidence=conf,
            elapsed_ms=round(elapsed, 2),
        )
