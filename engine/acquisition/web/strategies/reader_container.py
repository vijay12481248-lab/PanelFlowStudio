"""
Reader container extraction strategy (Stage 3).
Discovers the dominant reader container and isolates candidate extraction strictly within its subtree.
"""
import time
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.discovery.container_detector import ContainerDetector
from engine.acquisition.web.discovery.candidate_collector import CandidateCollector
from engine.acquisition.web.discovery.candidate_clusterer import CandidateClusterer
from engine.acquisition.web.discovery.candidate_scorer import CandidateScorer


class ReaderContainerStrategy(BaseExtractionStrategy):
    def __init__(self):
        self.detector = ContainerDetector()
        self.collector = CandidateCollector()
        self.clusterer = CandidateClusterer()
        self.scorer = CandidateScorer()

    @property
    def strategy_id(self) -> str:
        return "READER_CONTAINER"

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
                failure_reason="No HTML provided for reader container analysis",
            )

        soup = BeautifulSoup(html_text, "html.parser")
        container_tag, container_conf, signature = self.detector.detect_reader_container(soup)

        if not container_tag or container_conf < 0.30:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="LOW_CONFIDENCE",
                candidates=[],
                confidence=container_conf,
                elapsed_ms=round(elapsed, 2),
                failure_reason="No clear reader container structure discovered",
            )

        # Collect images strictly inside the container
        container_candidates = self.collector.collect(soup, base_url=url, container_tag=container_tag)
        for c in container_candidates:
            c.source_strategies.add(self.strategy_id)

        clusters = self.clusterer.cluster_candidates(container_candidates)
        dominant = clusters[0] if clusters else None
        scored = self.scorer.score_all(container_candidates, dominant_cluster=dominant, in_reader_container=True)

        accepted = [c for c in scored if c.content_score >= 0.50]
        count = len(accepted)

        final_conf = min(0.98, container_conf + (0.10 if count >= 5 else 0.0))
        status = "SUCCESS" if count >= 3 and final_conf >= 0.70 else "LOW_CONFIDENCE"

        elapsed = (time.perf_counter() - start_t) * 1000
        return StrategyResult(
            strategy_id=self.strategy_id,
            status=status,
            candidates=accepted,
            metadata={
                "container_signature": signature,
                "container_confidence": container_conf,
                "candidates_in_container": count,
            },
            confidence=final_conf,
            elapsed_ms=round(elapsed, 2),
        )
