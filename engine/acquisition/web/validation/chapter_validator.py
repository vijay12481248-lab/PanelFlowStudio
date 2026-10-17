"""
Comprehensive chapter validation pipeline combining duplicate removal, placeholder filtering,
SSRF checks, sequence normalization, and completeness scoring.
"""
from typing import List, Tuple, Optional
from engine.acquisition.web.models.chapter_manifest import ChapterPage, ChapterManifest
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.validation.placeholder_detector import is_placeholder_candidate
from engine.acquisition.web.validation.duplicate_detector import DuplicateDetector
from engine.acquisition.web.validation.completeness_validator import CompletenessValidator
from engine.acquisition.web.validation.ssrf_guard import is_safe_url


class ChapterValidator:
    def __init__(self):
        self.duplicate_detector = DuplicateDetector()
        self.completeness_validator = CompletenessValidator()

    def sanitize_candidates(
        self,
        candidates: List[ImageCandidate],
        allow_loopback_for_testing: bool = False,
    ) -> Tuple[List[ImageCandidate], List[str]]:
        """
        Filters out unsafe SSRF URLs, placeholders, and duplicates from candidate list.
        """
        filtered: List[ImageCandidate] = []
        issues: List[str] = []

        # 1. Deduplicate by resolved URL
        unique_cands, dup_count = self.duplicate_detector.filter_candidates(candidates)
        if dup_count > 0:
            issues.append(f"Filtered out {dup_count} duplicate image candidate URLs.")

        for c in unique_cands:
            # 2. SSRF check
            safe, reason = is_safe_url(c.resolved_url, allow_loopback_for_testing=allow_loopback_for_testing)
            if not safe:
                issues.append(f"Rejected unsafe URL {c.resolved_url}: {reason}")
                continue

            # 3. Placeholder check
            is_placeholder, p_reason = is_placeholder_candidate(
                c.resolved_url,
                width=c.natural_width or c.rendered_width,
                height=c.natural_height or c.rendered_height,
                attributes=c.attributes,
            )
            if is_placeholder:
                c.is_placeholder = True
                issues.append(f"Excluded placeholder: {c.resolved_url} ({p_reason})")
                continue

            filtered.append(c)

        return filtered, issues

    def validate_manifest(
        self,
        manifest: ChapterManifest,
        declared_count: Optional[int] = None,
        has_next_chapter: bool = False,
    ) -> ChapterManifest:
        """
        Performs post-extraction integrity checks on a ChapterManifest and computes completeness.
        """
        score, issues = self.completeness_validator.evaluate(
            manifest.pages,
            declared_page_count=declared_count,
            has_next_chapter_nav=has_next_chapter,
        )
        manifest.completeness_score = score
        if issues:
            manifest.diagnostics.setdefault("completeness_issues", []).extend(issues)

        return manifest
