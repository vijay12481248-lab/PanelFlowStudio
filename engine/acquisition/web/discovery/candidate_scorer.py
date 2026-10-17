"""
Candidate scoring engine with explainable positive and negative signals.
"""
import re
from typing import List, Optional
from engine.acquisition.web.models.image_candidate import ImageCandidate, CandidateCluster

NEGATIVE_NAME_REGEX = re.compile(
    r"(logo|icon|avatar|banner|ad_|ads|sponsor|thumb|preview|cover|btn|button|social|share|nav|arrow|close|header|footer|badge|rating)",
    re.IGNORECASE,
)
POSITIVE_NAME_REGEX = re.compile(
    r"(page|chapter|comic|manga|read|strip|\d{2,4})",
    re.IGNORECASE,
)


class CandidateScorer:
    """
    Computes explainable content score (0.0 - 1.0) for individual image candidates.
    """

    def score_candidate(
        self,
        candidate: ImageCandidate,
        dominant_cluster: Optional[CandidateCluster] = None,
        in_reader_container: bool = False,
    ) -> float:
        score = 0.5
        reasons = []
        from urllib.parse import urlparse
        from pathlib import Path

        parsed_url = urlparse(candidate.resolved_url)
        path_lower = parsed_url.path.lower()
        filename_lower = Path(path_lower).name

        # 1. Negative Signals
        is_negative_name = bool(NEGATIVE_NAME_REGEX.search(filename_lower))
        if is_negative_name:
            score -= 0.40
            reasons.append("url-matches-negative-icon-or-ad")

        w = candidate.natural_width or candidate.rendered_width
        h = candidate.natural_height or candidate.rendered_height
        is_thumb_dim = False

        if w and h:
            if w <= 32 or h <= 32:
                score -= 0.45
                reasons.append(f"tiny-icon-dimensions ({w}x{h})")
                is_thumb_dim = True
            elif w <= 150 and h <= 150:
                score -= 0.35
                reasons.append(f"thumbnail-dimensions ({w}x{h})")
                is_thumb_dim = True
            elif w >= 600 or h >= 800:
                score += 0.25
                reasons.append(f"large-content-dimensions ({w}x{h})")

            # Aspect ratio check
            if w > 0 and h > 0:
                ratio = float(h) / float(w)
                if 1.1 <= ratio <= 1.8:
                    score += 0.10
                    reasons.append("standard-comic-portrait-aspect-ratio")
                elif ratio >= 2.0:
                    score += 0.15
                    reasons.append("long-strip-webtoon-aspect-ratio")

        # 2. Positive Signals
        if POSITIVE_NAME_REGEX.search(filename_lower):
            score += 0.15
            reasons.append("filename-contains-page-or-chapter-keywords")

        if in_reader_container:
            score += 0.20
            reasons.append("inside-dominant-reader-container")

        if dominant_cluster and candidate.cluster_id == dominant_cluster.cluster_id:
            score += 0.20
            reasons.append("member-of-dominant-image-cluster")

        if len(candidate.source_strategies) > 1:
            score += 0.15
            reasons.append(f"confirmed-by-multiple-strategies ({len(candidate.source_strategies)})")

        # Guard: If item is a thumbnail or preview icon, cap maximum score
        if is_negative_name and is_thumb_dim:
            score = min(score, 0.20)

        final_score = max(0.0, min(1.0, round(score, 2)))
        candidate.content_score = final_score
        candidate.score_reasons = reasons
        return final_score

    def score_all(
        self,
        candidates: List[ImageCandidate],
        dominant_cluster: Optional[CandidateCluster] = None,
        in_reader_container: bool = False,
    ) -> List[ImageCandidate]:
        for c in candidates:
            self.score_candidate(c, dominant_cluster, in_reader_container)
        return candidates
