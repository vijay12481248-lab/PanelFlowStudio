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
    # Call to action & social / site invitations
    re.compile(r"\b(?:visit|support|join|follow|subscribe|donate)\s+(?:us\s+(?:at|on)\s+|our\s+(?:web)?site\b)", re.IGNORECASE),
    re.compile(r"\b(?:read\s+first\s+(?:at|on)|faster\s*release|higher\s*quality|support\s*us|donate\s*(?:via|now)?|uploaded\s*to)\b", re.IGNORECASE),
    re.compile(r"\b(?:if\s*you\s*enjoyed\s*this|thank\s*you\s*for\s*reading|leave\s*a\s*comment)\b", re.IGNORECASE),
    re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE),
    # Domains (any .com, .net, .org, .gg, .me, etc.)
    re.compile(r"\b[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.(?:com|net|org|io|gg|me|to|xyz|site|tv|cc|co|club|online|app|moe|fun|live|link)\b", re.IGNORECASE),
    # Common scanlator social handles & donation platforms
    re.compile(r"\b(?:discord\.(?:gg|com/invite)|patreon\.com|paypal(?:\.me)?|ko-fi\.com|t\.me|twitter\.com|x\.com)\b", re.IGNORECASE),
    # Scanlation & credit role markers
    re.compile(r"\b(?:translated\s*(?:by)?|translation|tl|proofread\s*(?:by)?|proofreader|pr|typeset\s*(?:by)?|typesetter|ts|cleaned\s*(?:by)?|cleaner|cl|redraw\s*(?:by)?|redrawer|rd|raw\s*provider|raws|qc|quality\s*check)\s*[:：\-\–]", re.IGNORECASE),
    re.compile(r"\b(?:scanlation|scans\s+team|scanlations)\b", re.IGNORECASE),
    re.compile(r"\bchapter\s*(?:end|\d+\s*end|finished)\b", re.IGNORECASE),
]

CREDIT_ROLE_TOKENS = {
    "cl", "ts", "pr", "tl", "rd", "rwe", "qc", "raws", "raw", "c/rd", "scans", "scan"
}

GENERIC_CREDIT_TERMS = [
    "translated", "proofread", "cleaned", "typeset", "redraw", "raws", "scanlation",
    "credits", "presents", "team", "discord", "patreon", "paypal", "author", "artist"
]

GENERIC_OUTRO_PATTERNS = [
    re.compile(r"\b(?:to\s*be\s*continued|end\s*of\s*(?:the\s*)?chapter|chapter\s*\d+\s*end|the\s*end|see\s*you\s*(?:in\s*the\s*)?next\s*chapter|thank(?:s|\s*you)\s*for\s*reading)\b", re.IGNORECASE),
    re.compile(r"\b(?:next\s*chapter\s*(?:is|will\s*be)?\s*(?:available|coming|soon)?)\b", re.IGNORECASE),
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
        story_content_present: bool = False,
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
        if story_content_present and h > 300 and aspect < 3:
            # A watermark inside a story image is not evidence that the whole
            # panel is an advertisement. Region cleanup handles the overlay.
            return PanelCoverageItem(
                panel_id=panel_id, reading_order=reading_order, source_image=source_image,
                bbox=bbox, width=w, height=h, aspect_ratio=aspect,
                classification=PanelClassificationKind.STORY_PANEL,
                subtype=NonStorySubtype.NONE, confidence=0.8,
                exclusion_reason=None, ocr_snippets=[ocr_text] if ocr_text else [],
                vision_description=vision_summary,
            )
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
        if is_first_on_first_page:
            words = set(re.findall(r"\b[a-z/]+\b", combined_text))
            found_roles = words & CREDIT_ROLE_TOKENS
            has_credit = bool(found_roles) or any(term in combined_text for term in GENERIC_CREDIT_TERMS)
            has_promo = any(pattern.search(combined_text) for pattern in PROMO_PATTERNS)
            if has_credit or has_promo:
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
                    confidence=0.98,
                    exclusion_reason="First page scanlation intro/cover credits splash card",
                    ocr_snippets=[ocr_text] if ocr_text else [],
                    vision_description=vision_summary,
                )

        if is_last_on_last_page:
            has_outro = any(p.search(combined_text) for p in GENERIC_OUTRO_PATTERNS)
            has_promo = any(p.search(combined_text) for p in PROMO_PATTERNS)
            has_credit = any(term in combined_text for term in ("discord", "credits", "patreon", "paypal", "support us", "donation", "scanlation"))
            has_redacted = "[blurred" in combined_text or "[redacted" in combined_text
            if (has_outro or has_promo or has_credit or has_redacted) and not story_content_present:
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
                    confidence=0.98,
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
