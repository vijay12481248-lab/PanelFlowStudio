"""
Rendered DOM extraction strategy using headless browser (Stages 9 & 10).
Progressively scrolls the document to trigger lazy-load handlers and extracts
rendered DOM elements (currentSrc, naturalWidth, naturalHeight).
"""
import time
from typing import Optional, Dict, Any, List
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.discovery.candidate_collector import normalize_image_url
from engine.acquisition.web.discovery.candidate_clusterer import CandidateClusterer
from engine.acquisition.web.discovery.candidate_scorer import CandidateScorer

# Script to evaluate rendered DOM state in browser page
BROWSER_DOM_EVAL_SCRIPT = """
() => {
    const images = Array.from(document.querySelectorAll('img, picture > source'));
    return images.map((el, idx) => {
        const isImg = el.tagName.toLowerCase() === 'img';
        const src = isImg ? (el.currentSrc || el.src) : el.srcset;
        const rect = el.getBoundingClientRect();
        return {
            dom_order: idx + 1,
            url: src,
            natural_width: isImg ? el.naturalWidth : null,
            natural_height: isImg ? el.naturalHeight : null,
            rendered_width: Math.round(rect.width),
            rendered_height: Math.round(rect.height),
            top: Math.round(rect.top + window.scrollY),
            alt: el.alt || null,
            parent_tag: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
            parent_classes: el.parentElement ? Array.from(el.parentElement.classList) : []
        };
    }).filter(item => item.url && !item.url.startsWith('javascript:'));
}
"""


class RenderedDomStrategy(BaseExtractionStrategy):
    def __init__(self):
        self.clusterer = CandidateClusterer()
        self.scorer = CandidateScorer()

    @property
    def strategy_id(self) -> str:
        return "RENDERED_DOM"

    async def extract(
        self,
        url: str,
        html_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        start_t = time.perf_counter()
        context = context or {}

        # 1. Check for simulated / mock browser driver in context (useful for tests)
        mock_rendered_items = context.get("mock_rendered_items")
        if mock_rendered_items is not None:
            return self._process_items(url, mock_rendered_items, start_t)

        # 2. Real Playwright execution
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
                failure_reason="Playwright package is not installed or available",
            )

        try:
            from engine.acquisition.web.strategies.browser_utils import launch_chromium_browser
            async with async_playwright() as p:
                browser = await launch_chromium_browser(p, headless=True)
                page = await browser.new_page()

                # Set standard desktop viewport
                await page.set_viewport_size({"width": 1280, "height": 1024})

                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1000)

                # Controlled progressive scrolling in viewport increments
                max_scroll_steps = 15
                last_height = 0
                for _ in range(max_scroll_steps):
                    curr_height = await page.evaluate("() => document.body.scrollHeight")
                    await page.evaluate("() => window.scrollBy(0, 800)")
                    await page.wait_for_timeout(250)
                    if curr_height == last_height and _ > 3:
                        break
                    last_height = curr_height

                # Evaluate rendered DOM
                raw_items = await page.evaluate(BROWSER_DOM_EVAL_SCRIPT)
                await browser.close()

                return self._process_items(url, raw_items, start_t)

        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="FAILED",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason=f"Playwright rendered DOM execution failed: {e}",
            )

    def _process_items(self, base_url: str, items: List[Dict[str, Any]], start_t: float) -> StrategyResult:
        candidates: List[ImageCandidate] = []
        for item in items:
            raw_url = item.get("url", "")
            if not raw_url:
                continue
            resolved = normalize_image_url(raw_url, base_url)
            cand = ImageCandidate(
                url=raw_url,
                resolved_url=resolved,
                dom_order=item.get("dom_order", 0),
                natural_width=item.get("natural_width"),
                natural_height=item.get("natural_height"),
                rendered_width=item.get("rendered_width"),
                rendered_height=item.get("rendered_height"),
                parent_tag=item.get("parent_tag"),
                parent_classes=item.get("parent_classes", []),
                alt_text=item.get("alt"),
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
                failure_reason="Rendered browser session produced zero image candidates",
            )

        clusters = self.clusterer.cluster_candidates(candidates)
        dominant = clusters[0] if clusters else None
        scored = self.scorer.score_all(candidates, dominant_cluster=dominant)

        accepted = [c for c in scored if c.content_score >= 0.40]
        count = len(accepted)
        conf = 0.96 if count >= 5 else 0.80

        elapsed = (time.perf_counter() - start_t) * 1000
        return StrategyResult(
            strategy_id=self.strategy_id,
            status="SUCCESS" if count >= 2 else "LOW_CONFIDENCE",
            candidates=accepted,
            metadata={"rendered_images_count": count},
            confidence=conf,
            elapsed_ms=round(elapsed, 2),
        )
