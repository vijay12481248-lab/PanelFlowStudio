"""
Recipe builder for learning reusable reader recipes from successful extractions or teach-mode selections.
"""
from urllib.parse import urlparse
from pathlib import Path
from engine.acquisition.web.recipes.recipe import ReaderRecipe
from engine.acquisition.web.models.chapter_manifest import ChapterManifest
from engine.acquisition.web.models.image_candidate import CandidateCluster


class RecipeBuilder:
    """
    Constructs a ReaderRecipe from extraction evidence.
    """

    def build_from_manifest(
        self,
        manifest: ChapterManifest,
        dominant_cluster: CandidateCluster,
    ) -> ReaderRecipe:
        parsed = urlparse(manifest.source_url)
        domain = parsed.netloc.lower()

        # Build path pattern by replacing numeric segments with wildcards
        path = parsed.path
        parts = path.strip("/").split("/")
        pattern_parts = []
        for p in parts:
            if p.isdigit() or any(char.isdigit() for char in p):
                pattern_parts.append("*")
            else:
                pattern_parts.append(p)
        pattern = "/" + "/".join(pattern_parts) if pattern_parts else "/*"

        # Image attributes from dominant cluster
        detected_attrs = set()
        for c in dominant_cluster.candidates:
            detected_attrs.update(c.attributes.keys())

        image_attrs = [a for a in ["data-src", "data-original", "data-url", "srcset", "src"] if a in detected_attrs]
        if not image_attrs:
            image_attrs = ["src", "data-src"]

        # Container signature
        signatures = []
        if manifest.reader_container_signature:
            signatures.append(manifest.reader_container_signature)
        if dominant_cluster.dominant_parent:
            signatures.append(dominant_cluster.dominant_parent)

        # Common CDN pattern
        cdn_patterns = []
        if dominant_cluster.common_host:
            cdn_patterns.append(dominant_cluster.common_host)

        return ReaderRecipe(
            domain=domain,
            chapter_path_pattern=pattern,
            preferred_strategy=manifest.extraction_strategy,
            container_signatures=signatures,
            image_attributes=image_attrs,
            ordering="DOM_ORDER",
            expected_cluster_minimum=max(2, len(manifest.pages) // 2),
            known_cdn_patterns=cdn_patterns,
        )
