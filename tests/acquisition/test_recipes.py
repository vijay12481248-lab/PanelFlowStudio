"""
Tests for recipe storage, matching, validation, and self-healing.
"""
from pathlib import Path
from engine.acquisition.web.recipes.recipe import ReaderRecipe
from engine.acquisition.web.recipes.recipe_store import RecipeStore
from engine.acquisition.web.recipes.recipe_validator import RecipeValidator
from engine.acquisition.web.models.image_candidate import ImageCandidate


def test_recipe_store_matching(tmp_path: Path):
    store = RecipeStore(storage_dir=tmp_path)

    recipe = ReaderRecipe(
        domain="manga-site.org",
        chapter_path_pattern="/series/*/chapter-*",
        preferred_strategy="STATIC_DOM",
        container_signatures=["div.reader-content"],
        known_cdn_patterns=["cdn.manga-site.org"],
    )
    store.save_recipe(recipe, persist=True)

    # Matching URL
    matched = store.find_recipe("https://manga-site.org/series/solo-hero/chapter-42")
    assert matched is not None
    assert matched.domain == "manga-site.org"
    assert matched.preferred_strategy == "STATIC_DOM"

    # Non-matching URL
    non_matched = store.find_recipe("https://other-site.com/chapter-1")
    assert non_matched is None


def test_recipe_validator():
    validator = RecipeValidator()

    recipe = ReaderRecipe(
        domain="example.com",
        expected_cluster_minimum=3,
        known_cdn_patterns=["cdn.example.com"],
    )

    # Valid candidates
    valid_cands = [
        ImageCandidate(url=f"https://cdn.example.com/p{i}.jpg", resolved_url=f"https://cdn.example.com/p{i}.jpg")
        for i in range(1, 6)
    ]
    is_valid, conf, issues = validator.validate_candidates(recipe, valid_cands)
    assert is_valid is True
    assert conf >= 0.80

    # Stale candidates: too few images
    stale_few = [
        ImageCandidate(url="https://cdn.example.com/p1.jpg", resolved_url="https://cdn.example.com/p1.jpg")
    ]
    is_valid_few, _, _ = validator.validate_candidates(recipe, stale_few)
    assert is_valid_few is False

    # Stale candidates: CDN mismatch (site structure changed)
    stale_cdn = [
        ImageCandidate(url=f"https://unknown-host.com/p{i}.jpg", resolved_url=f"https://unknown-host.com/p{i}.jpg")
        for i in range(1, 6)
    ]
    is_valid_cdn, _, _ = validator.validate_candidates(recipe, stale_cdn)
    assert is_valid_cdn is False
