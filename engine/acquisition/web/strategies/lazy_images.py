"""
Lazy-loaded image resolution strategy (Stage 4).
Specializes in resolving data-src, data-original, data-url, and replacing placeholders with high-res URLs.
"""
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.discovery.candidate_collector import normalize_image_url, LAZY_ATTR_CANDIDATES
from engine.acquisition.web.discovery.candidate_clusterer import CandidateClusterer
from engine.acquisition.web.discovery.candidate_scorer import CandidateScorer
from engine.acquisition.web.validation.placeholder_detector import is_placeholder_candidate


class LazyImagesStrategy(BaseExtractionStrategy):
    def __init__(self):
        self.clusterer = CandidateClusterer()
        self.scorer = CandidateScorer()

    @property
    def strategy_id(self) -> str:
        return "LAZY_IMAGES"

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
                failure_reason="No HTML provided for lazy image extraction",
            )

        soup = BeautifulSoup(html_text, "html.parser")
        lazy_candidates: List[ImageCandidate] = []

        # Find images that possess explicit data-* lazy attributes
        for idx, img in enumerate(soup.find_all("img"), start=1):
            target_url = None
            placeholder_url = img.get("src")
            attrs = {}

            # Prioritize lazy-loading attributes over static src
            for attr in ["data-src", "data-lazy-src", "data-original", "data-url", "data-image", "data-file"]:
                val = img.get(attr)
                if val and isinstance(val, str) and val.strip():
                    attrs[attr] = val.strip()
                    if not target_url and not val.strip().startswith("data:image"):
                        target_url = val.strip()

            if not target_url:
                continue

            resolved_target = normalize_image_url(target_url, url)

            # Check if src is a placeholder
            is_p = False
            p_url_res = None
            if placeholder_url:
                p_url_res = normalize_image_url(placeholder_url, url)
                is_p, _ = is_placeholder_candidate(p_url_res, attributes=img.attrs)

            cand = ImageCandidate(
                url=target_url,
                resolved_url=resolved_target,
                dom_order=idx,
                attributes=attrs,
                is_placeholder=False,  # The resolved target is legitimate content
                placeholder_url=p_url_res if is_p else None,
                source_strategies={self.strategy_id},
            )
            lazy_candidates.append(cand)

        if not lazy_candidates:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="LOW_CONFIDENCE",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason="No lazy data-src attributes discovered on images",
            )

        clusters = self.clusterer.cluster_candidates(lazy_candidates)
        dominant = clusters[0] if clusters else None
        scored = self.scorer.score_all(lazy_candidates, dominant_cluster=dominant)

        accepted = [c for c in scored if c.content_score >= 0.40]
        count = len(accepted)
        conf = 0.95 if count >= 5 else 0.75
        status = "SUCCESS" if count >= 2 else "LOW_CONFIDENCE"

        elapsed = (time.perf_counter() - start_t) * 1000
        return StrategyResult(
            strategy_id=self.strategy_id,
            status=status,
            candidates=accepted,
            metadata={"lazy_candidates_resolved": count},
            confidence=conf,
            elapsed_ms=round(elapsed, 2),
        )
