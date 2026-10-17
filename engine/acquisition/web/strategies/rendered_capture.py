"""
Rendered content capture fallback strategy (Stage 13).
Creates clearly labeled RENDERED_CAPTURE assets when content is presented through <canvas>
or custom client-side renderers without accessible image URLs.
"""
import time
from typing import Optional, Dict, Any, List
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.models.chapter_manifest import SourceQuality


class RenderedCaptureStrategy(BaseExtractionStrategy):
    @property
    def strategy_id(self) -> str:
        return "RENDERED_CAPTURE"

    async def extract(
        self,
        url: str,
        html_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        start_t = time.perf_counter()
        context = context or {}

        # 1. Check for simulated / mock canvas captures in context (for unit tests)
        mock_captures = context.get("mock_canvas_captures")
        if mock_captures is not None:
            return self._process_captures(url, mock_captures, start_t)

        # 2. Real Playwright canvas capture
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

                # Locate canvas elements
                canvases = await page.query_selector_all("canvas")
                captures = []
                for idx, c in enumerate(canvases, start=1):
                    # Extract data URL
                    data_url = await page.evaluate(
                        "(el) => el.toDataURL('image/png')", c
                    )
                    if data_url and len(data_url) > 200:
                        box = await c.bounding_box()
                        w = int(box["width"]) if box else 800
                        h = int(box["height"]) if box else 1200
                        captures.append({
                            "url": data_url,
                            "width": w,
                            "height": h,
                            "sequence": idx,
                        })

                await browser.close()
                return self._process_captures(url, captures, start_t)

        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="FAILED",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason=f"Rendered canvas capture failed: {e}",
            )

    def _process_captures(self, base_url: str, items: List[Dict[str, Any]], start_t: float) -> StrategyResult:
        candidates: List[ImageCandidate] = []
        for idx, item in enumerate(items, start=1):
            cand_url = item.get("url") or f"{base_url}#canvas_{idx}"
            cand = ImageCandidate(
                url=cand_url,
                resolved_url=cand_url,
                dom_order=idx,
                rendered_width=item.get("width", 800),
                rendered_height=item.get("height", 1200),
                mime_type="image/png",
                content_score=0.75,
                score_reasons=["rendered-canvas-capture-fallback"],
                source_strategies={self.strategy_id},
            )
            candidates.append(cand)

        elapsed = (time.perf_counter() - start_t) * 1000
        count = len(candidates)
        return StrategyResult(
            strategy_id=self.strategy_id,
            status="SUCCESS" if count >= 1 else "LOW_CONFIDENCE",
            candidates=candidates,
            metadata={
                "capture_type": "RENDERED_CAPTURE",
                "notice": "Inferior to ORIGINAL_RESOURCE; visibly rendered canvas snapshot",
            },
            confidence=0.70 if count >= 1 else 0.0,
            elapsed_ms=round(elapsed, 2),
        )
