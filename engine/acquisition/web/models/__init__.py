"""
Web acquisition models package.
"""
from engine.acquisition.web.models.chapter_manifest import (
    PageType,
    ContentLayout,
    ExtractionStrategyId,
    SourceQuality,
    PageEvidence,
    ChapterPage,
    ChapterManifest,
)
from engine.acquisition.web.models.image_candidate import (
    ImageCandidate,
    CandidateCluster,
    GlobalCandidatePool,
)
from engine.acquisition.web.models.site_fingerprint import SiteFingerprint
from engine.acquisition.web.models.extraction_result import (
    ExtractionState,
    ExtractionAttempt,
    ChapterExtractionResult,
)

__all__ = [
    "PageType",
    "ContentLayout",
    "ExtractionStrategyId",
    "SourceQuality",
    "PageEvidence",
    "ChapterPage",
    "ChapterManifest",
    "ImageCandidate",
    "CandidateCluster",
    "GlobalCandidatePool",
    "SiteFingerprint",
    "ExtractionState",
    "ExtractionAttempt",
    "ChapterExtractionResult",
]
