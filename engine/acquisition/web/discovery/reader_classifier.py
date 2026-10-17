"""
Reader architecture and layout classifier (Paged comic vs Long-strip Webtoon).
"""
from typing import List, Optional
from engine.acquisition.web.models.chapter_manifest import ContentLayout
from engine.acquisition.web.models.image_candidate import ImageCandidate


class ReaderClassifier:
    """
    Infers content layout from candidate dimensions and DOM arrangement.
    """

    def classify_layout(self, candidates: List[ImageCandidate]) -> ContentLayout:
        if not candidates:
            return ContentLayout.UNKNOWN

        aspect_ratios = []
        for c in candidates:
            w = c.natural_width or c.rendered_width
            h = c.natural_height or c.rendered_height
            if w and h and h > 0:
                aspect_ratios.append(float(h) / float(w))  # height / width

        if not aspect_ratios:
            return ContentLayout.PAGED

        # Standard comic pages usually have height/width between 1.2 and 1.6
        # Webtoon / long strips often have individual strips with height/width > 2.0 or 3.0+
        tall_strips = [ar for ar in aspect_ratios if ar >= 2.0]
        tall_ratio = len(tall_strips) / len(aspect_ratios)

        if tall_ratio >= 0.5:
            return ContentLayout.LONG_STRIP
        elif tall_ratio > 0.1:
            return ContentLayout.MIXED
        else:
            return ContentLayout.PAGED
