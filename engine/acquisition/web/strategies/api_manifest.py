"""
Accessible API manifest discovery strategy (Stage 8).
Discovers public or documented reader manifest endpoints referenced in page metadata or configuration.
"""
import json
import re
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.discovery.candidate_collector import normalize_image_url
from engine.acquisition.web.strategies.embedded_json import find_image_arrays_recursive
from engine.acquisition.web.validation.ssrf_guard import is_safe_url

API_ENDPOINT_REGEX = re.compile(
    r"""['"]((?:https?://[^'"]+)?/(?:api|v\d+|manifest|chapters?)/[^'"]*manifest[^'"]*)['"]""",
    re.IGNORECASE,
)


class ApiManifestStrategy(BaseExtractionStrategy):
    @property
    def strategy_id(self) -> str:
        return "API_MANIFEST"

    async def extract(
        self,
        url: str,
        html_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        start_t = time.perf_counter()

        if not html_text:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="FAILED",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason="No HTML document provided to search for API endpoints",
            )

        allow_loopback = context.get("allow_loopback_for_testing", False) if context else False

        # Look for referenced API manifest URLs in document
        soup = BeautifulSoup(html_text, "html.parser")
        potential_api_urls = []

        # Check <link rel="alternate" type="application/json" href="...">
        for link in soup.find_all("link", attrs={"type": "application/json"}):
            href = link.get("href")
            if href:
                potential_api_urls.append(urljoin(url, href))

        # Check script references
        for script in soup.find_all("script"):
            text = script.string or ""
            matches = API_ENDPOINT_REGEX.findall(text)
            for m in matches:
                potential_api_urls.append(urljoin(url, m))

        if not potential_api_urls:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="LOW_CONFIDENCE",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason="No referenced API manifest endpoints found in page",
            )

        # Query first valid safe endpoint
        candidates: List[ImageCandidate] = []
        target_api = potential_api_urls[0]

        safe, reason = is_safe_url(target_api, allow_loopback_for_testing=allow_loopback)
        if not safe:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="FAILED",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason=f"Discovered API manifest URL unsafe: {reason}",
            )

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(target_api)
                if resp.status_code == 200:
                    data = resp.json()
                    found_url_lists: List[List[str]] = []
                    find_image_arrays_recursive(data, found_url_lists)
                    if found_url_lists:
                        found_url_lists.sort(key=len, reverse=True)
                        for idx, u in enumerate(found_url_lists[0], start=1):
                            res = normalize_image_url(u, target_api)
                            candidates.append(
                                ImageCandidate(
                                    url=u,
                                    resolved_url=res,
                                    dom_order=idx,
                                    content_score=0.98,
                                    score_reasons=["public-api-manifest-item"],
                                    source_strategies={self.strategy_id},
                                )
                            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="LOW_CONFIDENCE",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason=f"Failed to query discovered API endpoint: {e}",
            )

        count = len(candidates)
        if count >= 2:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="SUCCESS",
                candidates=candidates,
                metadata={"api_endpoint": target_api, "page_count": count},
                confidence=0.98,
                elapsed_ms=round(elapsed, 2),
            )

        elapsed = (time.perf_counter() - start_t) * 1000
        return StrategyResult(
            strategy_id=self.strategy_id,
            status="LOW_CONFIDENCE",
            candidates=[],
            confidence=0.0,
            elapsed_ms=round(elapsed, 2),
            failure_reason="API endpoint did not yield chapter page array",
        )
