"""
Panel Classification and Non-Story Content Filtering Service.
Classifies comic/manga regions into:
  - STORY_PANEL: Core narrative panels containing scenes, characters, or story actions.
  - NON_STORY_CONTENT: Advertisements, donation links, scanlation credits, logos, covers.
  - UNCERTAIN: Borderline regions requiring secondary inspection or human review.

Combines deterministic geometric analysis, OCR keyword matching, and vision model verification.
Ensures full provenance tracking and prevents silent panel dropping.
"""
import re
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field


class PanelClassificationKind(str, Enum):
    STORY_PANEL = "STORY_PANEL"
    NON_STORY_CONTENT = "NON_STORY_CONTENT"
    UNCERTAIN = "UNCERTAIN"


class NonStorySubtype(str, Enum):
    ADVERTISEMENT_BANNER = "ADVERTISEMENT_BANNER"
    PROMOTIONAL_ICON = "PROMOTIONAL_ICON"
    COVER_CREDITS = "COVER_CREDITS"
    OUTRO_CREDITS = "OUTRO_CREDITS"
    WEBSITE_WATERMARK = "WEBSITE_WATERMARK"
    UNKNOWN_NON_STORY = "UNKNOWN_NON_STORY"
    NONE = "NONE"


class PanelCoverageItem(BaseModel):
    panel_id: str
    reading_order: int
    source_image: str
    bbox: List[int] = Field(description="[x, y, width, height]")
    width: int
    height: int
    aspect_ratio: float
    classification: PanelClassificationKind
    subtype: NonStorySubtype = NonStorySubtype.NONE
    confidence: float = 1.0
    exclusion_reason: Optional[str] = None
    ocr_snippets: List[str] = Field(default_factory=list)
    vision_description: Optional[str] = None


class PanelCoverageReport(BaseModel):
    project_id: str
    total_discovered_panels: int
    total_story_panels: int
    total_non_story_panels: int
    total_uncertain_panels: int
    coverage_percentage: float
    items: List[PanelCoverageItem] = Field(default_factory=list)


# Promotional and non-story OCR text patterns
PROMO_PATTERNS = [
    re.compile(r"\b(?:visit|read|support|join|follow)\s+(?:us\s+(?:at|on)\s+|our\s+(?:web)?site\b)", re.IGNORECASE),
    re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE),
    re.compile(r"\b[\w-]+\.(?:com|net|org|io|gg)\b", re.IGNORECASE),
    re.compile(r"manhuaplus", re.IGNORECASE),
    re.compile(r"read\s*on\s*manhua", re.IGNORECASE),
    re.compile(r"faster\s*release", re.IGNORECASE),
    re.compile(r"enjoyed\s*this\s*series", re.IGNORECASE),
    re.compile(r"support\s*us", re.IGNORECASE),
    re.compile(r"patreon\.com", re.IGNORECASE),
    re.compile(r"paypal", re.IGNORECASE),
    re.compile(r"discord\.gg", re.IGNORECASE),
    re.compile(r"donate", re.IGNORECASE),
    re.compile(r"scanlation", re.IGNORECASE),
    re.compile(r"translated\s*by", re.IGNORECASE),
    re.compile(r"proofread\s*by", re.IGNORECASE),
    re.compile(r"cleaned\s*by", re.IGNORECASE),
    re.compile(r"typeset\s*by", re.IGNORECASE),
    re.compile(r"uploaded\s*to", re.IGNORECASE),
    re.compile(r"chapter\s*end", re.IGNORECASE),
]


class PanelClassifier:
    """
    Deterministic and multi-modal classifier for panel filtering.
    Guarantees that advertisements, sponsor banners, and translator credits
    do not contaminate story reasoning or video timelines.
    """

    @classmethod
    def classify_panel(
        cls,
        panel_id: str,
        reading_order: int,
        source_image: str,
        bbox: List[int],
        page_width: int = 1200,
        page_height: int = 12000,
        ocr_text: str = "",
        vision_summary: Optional[str] = None,
        is_first_on_first_page: bool = False,
        is_last_on_last_page: bool = False,
    ) -> PanelCoverageItem:
        x, y, w, h = bbox
        aspect = round(float(w) / max(1.0, float(h)), 2)

        # 1. Deterministic Geometry Checks for Ribbons & Banners
        # Webtoon/manhua banner ribbons are typically wide and very thin (aspect > 4.0, h <= 250)
        if aspect >= 4.0 and h <= 250 and w >= 700 and not ocr_text.strip() and not vision_summary:
            return PanelCoverageItem(
                panel_id=panel_id,
                reading_order=reading_order,
                source_image=source_image,
                bbox=bbox,
                width=w,
                height=h,
                aspect_ratio=aspect,
                classification=PanelClassificationKind.UNCERTAIN,
                subtype=NonStorySubtype.ADVERTISEMENT_BANNER,
                confidence=0.55,
                exclusion_reason=f"Geometric horizontal banner ribbon: aspect {aspect:.2f} (w={w}, h={h} <= 250)",
                ocr_snippets=[ocr_text] if ocr_text else [],
                vision_description=vision_summary,
            )

        # Small watermark / promo icons
        if w <= 400 and h <= 120 and not ocr_text.strip() and not vision_summary:
            return PanelCoverageItem(
                panel_id=panel_id,
                reading_order=reading_order,
                source_image=source_image,
                bbox=bbox,
                width=w,
                height=h,
                aspect_ratio=aspect,
                classification=PanelClassificationKind.UNCERTAIN,
                subtype=NonStorySubtype.PROMOTIONAL_ICON,
                confidence=0.5,
                exclusion_reason=f"Small logo/icon geometry: w={w} <= 400, h={h} <= 120",
                ocr_snippets=[ocr_text] if ocr_text else [],
                vision_description=vision_summary,
            )

        # 2. Text / OCR Pattern Checks
        combined_text = f"{ocr_text} {vision_summary or ''}".lower()
        for pattern in PROMO_PATTERNS:
            if pattern.search(combined_text):
                subtype = (
                    NonStorySubtype.COVER_CREDITS
                    if ("translated" in combined_text or "scanlation" in combined_text or "credits" in combined_text)
                    else NonStorySubtype.ADVERTISEMENT_BANNER
                )
                return PanelCoverageItem(
                    panel_id=panel_id,
                    reading_order=reading_order,
                    source_image=source_image,
                    bbox=bbox,
                    width=w,
                    height=h,
                    aspect_ratio=aspect,
                    classification=PanelClassificationKind.NON_STORY_CONTENT,
                    subtype=subtype,
                    confidence=0.99,
                    exclusion_reason=f"Matched promotional pattern '{pattern.pattern}' in text/vision",
                    ocr_snippets=[ocr_text] if ocr_text else [],
                    vision_description=vision_summary,
                )

        # 3. Vision Observation Check (e.g. LLM explicitly flagged promotional banner)
        if vision_summary:
            v_low = vision_summary.lower()
            if "promotional banner" in v_low or "advertisement" in v_low or "translator credit" in v_low:
                return PanelCoverageItem(
                    panel_id=panel_id,
                    reading_order=reading_order,
                    source_image=source_image,
                    bbox=bbox,
                    width=w,
                    height=h,
                    aspect_ratio=aspect,
                    classification=PanelClassificationKind.NON_STORY_CONTENT,
                    subtype=NonStorySubtype.ADVERTISEMENT_BANNER,
                    confidence=0.95,
                    exclusion_reason=f"Vision model classified content as promotional: {vision_summary[:80]}",
                    ocr_snippets=[ocr_text] if ocr_text else [],
                    vision_description=vision_summary,
                )

        # 4. First / Last Page Splash Envelope Checks
        if is_first_on_first_page and h > 1400:
            # Check if it has title / credit splash
            if any(term in combined_text for term in ["chapter", "magic emperor", "manhuaplus", "presents", "team"]):
                return PanelCoverageItem(
                    panel_id=panel_id,
                    reading_order=reading_order,
                    source_image=source_image,
                    bbox=bbox,
                    width=w,
                    height=h,
                    aspect_ratio=aspect,
                    classification=PanelClassificationKind.NON_STORY_CONTENT,
                    subtype=NonStorySubtype.COVER_CREDITS,
                    confidence=0.95,
                    exclusion_reason="First page scanlation intro/title splash card",
                    ocr_snippets=[ocr_text] if ocr_text else [],
                    vision_description=vision_summary,
                )

        if is_last_on_last_page and h > 1800:
            if any(term in combined_text for term in ["to be continued", "end", "next chapter", "discord", "credits", "manhuaplus"]):
                return PanelCoverageItem(
                    panel_id=panel_id,
                    reading_order=reading_order,
                    source_image=source_image,
                    bbox=bbox,
                    width=w,
                    height=h,
                    aspect_ratio=aspect,
                    classification=PanelClassificationKind.NON_STORY_CONTENT,
                    subtype=NonStorySubtype.OUTRO_CREDITS,
                    confidence=0.95,
                    exclusion_reason="Last page scanlation outro/credits card",
                    ocr_snippets=[ocr_text] if ocr_text else [],
                    vision_description=vision_summary,
                )

        # Default: Confirmed Story Panel
        return PanelCoverageItem(
            panel_id=panel_id,
            reading_order=reading_order,
            source_image=source_image,
            bbox=bbox,
            width=w,
            height=h,
            aspect_ratio=aspect,
            classification=PanelClassificationKind.STORY_PANEL,
            subtype=NonStorySubtype.NONE,
            confidence=0.95,
            exclusion_reason=None,
            ocr_snippets=[ocr_text] if ocr_text else [],
            vision_description=vision_summary,
        )

    @classmethod
    def generate_coverage_report(
        cls,
        project_id: str,
        items: List[PanelCoverageItem],
    ) -> PanelCoverageReport:
        story_cnt = sum(1 for it in items if it.classification == PanelClassificationKind.STORY_PANEL)
        non_story_cnt = sum(1 for it in items if it.classification == PanelClassificationKind.NON_STORY_CONTENT)
        uncertain_cnt = sum(1 for it in items if it.classification == PanelClassificationKind.UNCERTAIN)
        total = len(items)

        cov_pct = round((story_cnt / total * 100.0) if total > 0 else 0.0, 1)

        return PanelCoverageReport(
            project_id=project_id,
            total_discovered_panels=total,
            total_story_panels=story_cnt,
            total_non_story_panels=non_story_cnt,
            total_uncertain_panels=uncertain_cnt,
            coverage_percentage=cov_pct,
            items=items,
        )
