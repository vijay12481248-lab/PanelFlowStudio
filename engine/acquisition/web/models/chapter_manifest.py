"""
Canonical ChapterManifest and ChapterPage models for PanelFlow Studio web acquisition.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class PageType(str, Enum):
    DIRECT_IMAGE = "DIRECT_IMAGE"
    CHAPTER_PAGE = "CHAPTER_PAGE"
    SERIES_PAGE = "SERIES_PAGE"
    ARCHIVE = "ARCHIVE"
    DOCUMENT = "DOCUMENT"
    UNKNOWN_PAGE = "UNKNOWN_PAGE"
    NOT_CONTENT = "NOT_CONTENT"


class ContentLayout(str, Enum):
    PAGED = "PAGED"
    LONG_STRIP = "LONG_STRIP"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class ExtractionStrategyId(str, Enum):
    DIRECT_DOCUMENT = "DIRECT_DOCUMENT"
    STATIC_DOM = "STATIC_DOM"
    READER_CONTAINER = "READER_CONTAINER"
    LAZY_IMAGES = "LAZY_IMAGES"
    EMBEDDED_JSON = "EMBEDDED_JSON"
    API_MANIFEST = "API_MANIFEST"
    RENDERED_DOM = "RENDERED_DOM"
    BROWSER_NETWORK = "BROWSER_NETWORK"
    RESOURCE_TIMING = "RESOURCE_TIMING"
    RENDERED_CAPTURE = "RENDERED_CAPTURE"
    RECIPE_FASTPATH = "RECIPE_FASTPATH"
    HUMAN_TEACH = "HUMAN_TEACH"


class SourceQuality(str, Enum):
    ORIGINAL_RESOURCE = "ORIGINAL_RESOURCE"
    OPTIMIZED_RESOURCE = "OPTIMIZED_RESOURCE"
    RENDERED_CAPTURE = "RENDERED_CAPTURE"


class PageEvidence(BaseModel):
    strategy: str
    confidence: float = 1.0
    selector: Optional[str] = None
    attribute: Optional[str] = None
    observed_dimensions: Optional[Dict[str, int]] = None
    network_initiator: Optional[str] = None
    notes: Optional[str] = None


class ChapterPage(BaseModel):
    sequence: int = Field(..., description="1-based natural reading order")
    source_url: str = Field(..., description="Source URL as discovered on page")
    resolved_url: str = Field(..., description="Canonicalized absolute download URL")
    source_strategy: str = Field(..., description="Strategy that discovered or confirmed this page")
    source_quality: SourceQuality = Field(default=SourceQuality.ORIGINAL_RESOURCE)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: Optional[str] = None
    byte_size: Optional[int] = None
    sha256: Optional[str] = None

    evidence: List[PageEvidence] = Field(default_factory=list)
    suggested_filename: Optional[str] = None


class ChapterManifest(BaseModel):
    source_url: str
    canonical_url: str
    domain: str

    page_type: PageType = PageType.CHAPTER_PAGE

    series_title: Optional[str] = None
    chapter_title: Optional[str] = None
    chapter_number: Optional[str] = None

    extraction_strategy: str
    extraction_confidence: float = Field(..., ge=0.0, le=1.0)
    completeness_score: float = Field(..., ge=0.0, le=1.0)

    content_layout: ContentLayout = ContentLayout.PAGED
    reader_container_signature: Optional[str] = None

    pages: List[ChapterPage] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
