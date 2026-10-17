"""
Completeness validator for assessing whether an extracted sequence represents a complete chapter.
"""
from typing import List, Optional, Tuple, Dict, Any
from engine.acquisition.web.models.chapter_manifest import ChapterPage


class CompletenessValidator:
    """
    Evaluates extracted pages against contiguity, manifest count, and navigation markers.
    """

    def evaluate(
        self,
        pages: List[ChapterPage],
        declared_page_count: Optional[int] = None,
        has_start_marker: bool = False,
        has_end_marker: bool = False,
        has_next_chapter_nav: bool = False,
    ) -> Tuple[float, List[str]]:
        """
        Calculates completeness_score (0.0 - 1.0) and returns a list of diagnostic observations.
        """
        if not pages:
            return 0.0, ["Zero pages discovered in chapter sequence"]

        issues: List[str] = []
        score = 1.0
        n_pages = len(pages)

        # 1. Contiguity check on page sequence
        sequences = [p.sequence for p in pages]
        expected_seqs = list(range(1, n_pages + 1))
        if sequences != expected_seqs:
            missing = set(range(1, max(sequences) + 1)) - set(sequences)
            if missing:
                score -= 0.25
                issues.append(f"Non-contiguous sequence detected. Missing page numbers: {sorted(list(missing))[:5]}")
            else:
                score -= 0.10
                issues.append("Page sequence order does not start at 1 or contains irregular increments.")

        # 2. Declared count comparison
        if declared_page_count is not None and declared_page_count > 0:
            if n_pages == declared_page_count:
                # Perfect match
                pass
            elif n_pages < declared_page_count:
                ratio = n_pages / declared_page_count
                score *= ratio
                issues.append(f"Discovered {n_pages} pages out of {declared_page_count} declared in manifest.")
            else:
                score -= 0.05
                issues.append(f"Discovered {n_pages} pages, exceeding declared manifest count of {declared_page_count}.")

        # 3. Very small count check (comic chapters rarely have < 3 pages unless a teaser or strip)
        if n_pages < 2:
            score -= 0.20
            issues.append(f"Unusually low page count ({n_pages}) for a full chapter.")

        # 4. Reader boundaries & navigation bonus
        if has_next_chapter_nav or has_end_marker:
            score = min(1.0, score + 0.05)
        elif not has_end_marker and n_pages < 5:
            score -= 0.10
            issues.append("Neither end-of-chapter marker nor next-chapter navigation detected.")

        final_score = max(0.0, min(1.0, round(score, 2)))
        return final_score, issues
