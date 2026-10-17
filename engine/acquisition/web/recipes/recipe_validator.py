"""
Recipe validator for testing whether a cached ReaderRecipe is still valid or stale.
"""
from typing import Tuple, List
from engine.acquisition.web.recipes.recipe import ReaderRecipe
from engine.acquisition.web.models.image_candidate import ImageCandidate


class RecipeValidator:
    """
    Validates candidate extraction output against recipe expectations.
    """

    def validate_candidates(
        self,
        recipe: ReaderRecipe,
        candidates: List[ImageCandidate],
    ) -> Tuple[bool, float, List[str]]:
        """
        Returns (is_valid, confidence, issues).
        If invalid, indicates recipe is stale and orchestrator must fall back to generic discovery.
        """
        issues: List[str] = []

        if not candidates:
            return False, 0.0, ["Zero candidates extracted using recipe selectors"]

        count = len(candidates)
        if count < recipe.expected_cluster_minimum:
            issues.append(f"Candidate count ({count}) below recipe expectation ({recipe.expected_cluster_minimum})")
            return False, 0.30, issues

        # Check if expected container signature or CDN pattern matched
        if recipe.known_cdn_patterns:
            matched_cdn = any(
                any(cdn in c.resolved_url for cdn in recipe.known_cdn_patterns)
                for c in candidates
            )
            if not matched_cdn:
                issues.append("Candidates do not match recipe known CDN patterns (site structure may have changed)")
                return False, 0.40, issues

        conf = min(0.98, 0.80 + (0.01 * min(count, 18)))
        return True, conf, []
