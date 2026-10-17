"""
Static HTML DOM extraction strategy (Stage 2).
Fast discovery from delivered static HTML markup.
"""
import time
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.discovery.candidate_collector import CandidateCollector
from engine.acquisition.web.discovery.candidate_clusterer import CandidateClusterer
from engine.acquisition.web.discovery.candidate_scorer import CandidateScorer


class StaticDomStrategy(BaseExtractionStrategy):
    def __init__(self):
        self.collector = CandidateCollector()
        self.clusterer = CandidateClusterer()
        self.scorer = CandidateScorer()

    @property
    def strategy_id(self) -> str:
        return "STATIC_DOM"

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
                failure_reason="No HTML document content provided to Static DOM strategy",
            )

        soup = BeautifulSoup(html_text, "html.parser")
        raw_candidates = self.collector.collect(soup, base_url=url)

        if not raw_candidates:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="LOW_CONFIDENCE",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason="No image elements discovered in static DOM",
            )

        # Cluster candidates
        clusters = self.clusterer.cluster_candidates(raw_candidates)
        dominant_cluster = clusters[0] if clusters else None

        # Score candidates
        scored_candidates = self.scorer.score_all(raw_candidates, dominant_cluster=dominant_cluster)

        # Filter out obvious non-content
        accepted = [c for c in scored_candidates if c.content_score >= 0.40]

        # Calculate strategy confidence
        cluster_score = dominant_cluster.cluster_score if dominant_cluster else 0.5
        count = len(accepted)
        if count >= 8 and cluster_score >= 0.8:
            conf = 0.95
            status = "SUCCESS"
        elif count >= 3:
            conf = min(0.90, cluster_score)
            status = "SUCCESS" if conf >= 0.70 else "LOW_CONFIDENCE"
        else:
            conf = 0.40
            status = "LOW_CONFIDENCE"

        elapsed = (time.perf_counter() - start_t) * 1000
        return StrategyResult(
            strategy_id=self.strategy_id,
            status=status,
            candidates=accepted,
            metadata={
                "total_dom_images": len(raw_candidates),
                "clusters_found": len(clusters),
                "dominant_cluster_id": dominant_cluster.cluster_id if dominant_cluster else None,
            },
            confidence=conf,
            elapsed_ms=round(elapsed, 2),
        )
