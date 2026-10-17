"""
SiteFingerprint model for capturing domain/reader architectural characteristics.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class SiteFingerprint(BaseModel):
    domain: str
    path_pattern: Optional[str] = None
    framework_hints: List[str] = Field(default_factory=list)
    reader_container_signature: Optional[str] = None
    known_cdn_hosts: List[str] = Field(default_factory=list)
    lazy_loading_style: Optional[str] = None
    hydration_format: Optional[str] = None
    content_architecture: str = "GENERIC_DOM"
    estimated_page_count: Optional[int] = None
