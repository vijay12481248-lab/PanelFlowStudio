"""
Sequence resolver for natural numeric ordering and multi-source sequence arbitration.
Ensures ordering never resolves 1, 10, 11, 2 alphabetically.
"""
import re
from typing import List, Tuple
from urllib.parse import urlparse
from pathlib import Path
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.models.chapter_manifest import ChapterPage, SourceQuality, PageEvidence


def natural_sort_key(s: str) -> List:
    """Split string into alternating chunks of text and integer for natural ordering."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


class SequenceResolver:
    """
    Arbitrates canonical reading order from manifest index, DOM order, filename numbers, or Y-coordinates.
    """

    def resolve_sequence(
        self,
        candidates: List[ImageCandidate],
        preferred_strategy: str = "STATIC_DOM",
        has_explicit_manifest_order: bool = False,
    ) -> List[ChapterPage]:
        if not candidates:
            return []

        # If already explicit manifest order, preserve index order directly
        if has_explicit_manifest_order:
            ordered_candidates = candidates
            method = "EXPLICIT_MANIFEST"
            conf = 1.0
        else:
            # Check if filenames have clean embedded numbers (e.g. page_01.jpg, 002.png, p10.webp)
            has_filename_numbers = True
            for c in candidates:
                stem = Path(urlparse(c.resolved_url).path).stem
                if not re.search(r"\d+", stem):
                    has_filename_numbers = False
                    break

            if has_filename_numbers and len(candidates) >= 2:
                # Sort naturally by filename stem
                ordered_candidates = sorted(
                    candidates,
                    key=lambda c: natural_sort_key(Path(urlparse(c.resolved_url).path).stem),
                )
                method = "NATURAL_FILENAME_SORT"
                conf = 0.95
            else:
                # Fall back to DOM order
                ordered_candidates = sorted(candidates, key=lambda c: c.dom_order)
                method = "DOM_ORDER"
                conf = 0.85

        pages: List[ChapterPage] = []
        for idx, c in enumerate(ordered_candidates, start=1):
            stem = Path(urlparse(c.resolved_url).path).stem or f"page_{idx:04d}"
            ext = Path(urlparse(c.resolved_url).path).suffix or ".jpg"
            filename = f"page_{idx:04d}{ext}"

            page = ChapterPage(
                sequence=idx,
                source_url=c.url,
                resolved_url=c.resolved_url,
                source_strategy=list(c.source_strategies)[0] if c.source_strategies else preferred_strategy,
                source_quality=SourceQuality.ORIGINAL_RESOURCE,
                confidence=c.content_score,
                width=c.natural_width or c.rendered_width,
                height=c.natural_height or c.rendered_height,
                mime_type=c.mime_type,
                byte_size=c.byte_size,
                sha256=c.sha256,
                suggested_filename=filename,
                evidence=[
                    PageEvidence(
                        strategy=preferred_strategy,
                        confidence=c.content_score,
                        selector=c.dom_path,
                        notes=f"Sequence {idx} determined via {method} (conf={conf})",
                    )
                ],
            )
            pages.append(page)

        return pages
