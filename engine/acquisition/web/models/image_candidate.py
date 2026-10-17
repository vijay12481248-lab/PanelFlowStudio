"""
ImageCandidate, CandidateCluster, and GlobalCandidatePool models.
"""
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field


class ImageCandidate(BaseModel):
    url: str
    resolved_url: str
    dom_order: int = 0
    dom_path: Optional[str] = None
    parent_tag: Optional[str] = None
    parent_classes: List[str] = Field(default_factory=list)
    attributes: Dict[str, str] = Field(default_factory=dict)

    natural_width: Optional[int] = None
    natural_height: Optional[int] = None
    rendered_width: Optional[int] = None
    rendered_height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    mime_type: Optional[str] = None
    byte_size: Optional[int] = None
    sha256: Optional[str] = None

    alt_text: Optional[str] = None
    title: Optional[str] = None
    nearby_text: Optional[str] = None

    is_placeholder: bool = False
    placeholder_url: Optional[str] = None

    content_score: float = Field(default=0.5, ge=0.0, le=1.0)
    score_reasons: List[str] = Field(default_factory=list)

    cluster_id: Optional[str] = None
    source_strategies: Set[str] = Field(default_factory=set)

    def merge_with(self, other: "ImageCandidate"):
        """Merge evidence from another observation of the same canonical URL."""
        self.source_strategies.update(other.source_strategies)
        if other.natural_width and not self.natural_width:
            self.natural_width = other.natural_width
        if other.natural_height and not self.natural_height:
            self.natural_height = other.natural_height
        if other.rendered_width and not self.rendered_width:
            self.rendered_width = other.rendered_width
        if other.rendered_height and not self.rendered_height:
            self.rendered_height = other.rendered_height
        if other.aspect_ratio and not self.aspect_ratio:
            self.aspect_ratio = other.aspect_ratio
        if other.mime_type and not self.mime_type:
            self.mime_type = other.mime_type
        if other.byte_size and not self.byte_size:
            self.byte_size = other.byte_size
        if other.sha256 and not self.sha256:
            self.sha256 = other.sha256
        if other.dom_path and not self.dom_path:
            self.dom_path = other.dom_path
        if other.alt_text and not self.alt_text:
            self.alt_text = other.alt_text
        if other.title and not self.title:
            self.title = other.title
        if other.is_placeholder and not self.is_placeholder:
            self.is_placeholder = True
            self.placeholder_url = other.placeholder_url
        for r in other.score_reasons:
            if r not in self.score_reasons:
                self.score_reasons.append(r)


class CandidateCluster(BaseModel):
    cluster_id: str
    candidates: List[ImageCandidate] = Field(default_factory=list)
    dominant_parent: Optional[str] = None
    common_host: Optional[str] = None
    common_path_prefix: Optional[str] = None
    avg_width: Optional[float] = None
    avg_height: Optional[float] = None
    avg_aspect_ratio: Optional[float] = None
    cluster_score: float = Field(default=0.5, ge=0.0, le=1.0)
    cluster_reasons: List[str] = Field(default_factory=list)


class GlobalCandidatePool:
    """
    Central repository merging candidate images across multiple strategies by canonical URL,
    maintaining combined multi-source evidence and scores.
    """
    def __init__(self):
        self._pool: Dict[str, ImageCandidate] = {}

    def add_candidate(self, candidate: ImageCandidate) -> ImageCandidate:
        key = candidate.resolved_url
        if key in self._pool:
            self._pool[key].merge_with(candidate)
        else:
            self._pool[key] = candidate
        return self._pool[key]

    def add_candidates(self, candidates: List[ImageCandidate]) -> List[ImageCandidate]:
        return [self.add_candidate(c) for c in candidates]

    def get_candidate(self, resolved_url: str) -> Optional[ImageCandidate]:
        return self._pool.get(resolved_url)

    def all_candidates(self) -> List[ImageCandidate]:
        return list(self._pool.values())

    def get_candidates(self) -> List[ImageCandidate]:
        return list(self._pool.values())

    def clear(self):
        self._pool.clear()

    def count(self) -> int:
        return len(self._pool)
