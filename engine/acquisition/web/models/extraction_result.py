"""
ExtractionState, ExtractionAttempt, and ChapterExtractionResult models.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from engine.acquisition.web.models.chapter_manifest import ChapterManifest
from engine.acquisition.web.models.image_candidate import CandidateCluster
from engine.acquisition.web.models.site_fingerprint import SiteFingerprint


class ExtractionState(str, Enum):
    INSPECTING = "INSPECTING"
    CLASSIFYING = "CLASSIFYING"
    DISCOVERING = "DISCOVERING"
    RENDERING = "RENDERING"
    OBSERVING_NETWORK = "OBSERVING_NETWORK"
    COLLECTING_CANDIDATES = "COLLECTING_CANDIDATES"
    SCORING = "SCORING"
    VALIDATING = "VALIDATING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    EXTRACTED = "EXTRACTED"
    NOT_A_CHAPTER = "NOT_A_CHAPTER"
    ACCESS_RESTRICTED = "ACCESS_RESTRICTED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    CHALLENGE_PRESENT = "CHALLENGE_PRESENT"
    RIGHTS_NOT_APPROVED = "RIGHTS_NOT_APPROVED"
    UNSUPPORTED_READER = "UNSUPPORTED_READER"
    FAILED_NETWORK = "FAILED_NETWORK"
    FAILED_SSRF_BLOCKED = "FAILED_SSRF_BLOCKED"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    INVALID_URL = "INVALID_URL"
    NO_CONTENT_IMAGES = "NO_CONTENT_IMAGES"
    UNSUPPORTED_DOCUMENT = "UNSUPPORTED_DOCUMENT"
    JAVASCRIPT_REQUIRED = "JAVASCRIPT_REQUIRED"
    RENDER_FAILED = "RENDER_FAILED"
    CONTENT_INCOMPLETE = "CONTENT_INCOMPLETE"
    SUCCESS = "SUCCESS"
    SUCCESS_NEEDS_REVIEW = "SUCCESS_NEEDS_REVIEW"
    USER_CANCELLED = "USER_CANCELLED"


class ExtractionAttempt(BaseModel):
    strategy_id: str
    status: str  # SUCCESS, LOW_CONFIDENCE, FAILED, SKIPPED, ACCESS_RESTRICTED, etc.
    candidate_count: int = 0
    confidence: float = 0.0
    elapsed_ms: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    failure_reason: Optional[str] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class ChapterExtractionResult(BaseModel):
    state: ExtractionState
    manifest: Optional[ChapterManifest] = None
    site_fingerprint: Optional[SiteFingerprint] = None
    attempts: List[ExtractionAttempt] = Field(default_factory=list)
    final_strategy: Optional[str] = None
    overall_confidence: float = 0.0
    completeness_score: float = 0.0
    candidate_clusters: List[CandidateCluster] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    needs_review_reasons: List[str] = Field(default_factory=list)
    error: Optional[str] = None
