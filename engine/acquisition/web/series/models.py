"""
Data models for Smart Manga Series Scraping, Chapter Discovery, and Batch Compilation.
"""
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field


class CompilationMode(str, Enum):
    INDIVIDUAL = "individual"
    COMPILED = "compiled"


class SeriesChapter(BaseModel):
    sequence: float = Field(..., description="Numeric chapter/episode number, e.g. 1.0, 921.0, 921.5")
    title: str = Field(..., description="Display title of the chapter, e.g. 'Chapter 927 - Twisted Reality'")
    url: str = Field(..., description="Full canonical URL of the chapter reader page")
    date_released: Optional[str] = None
    page_count_estimate: Optional[int] = None
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class SeriesMetadata(BaseModel):
    title: str = Field(..., description="Series / Manga canonical title")
    series_url: str = Field(..., description="Base series index URL")
    source_domain: str = Field(..., description="Domain of the manga source, e.g. manhuaplus.com")
    cover_image_url: Optional[str] = None
    description: Optional[str] = None
    total_chapters_detected: int = 0
    chapters: List[SeriesChapter] = Field(default_factory=list)
    url_pattern: Optional[str] = Field(
        None, description="Inferred URL pattern template, e.g. https://domain.com/manga/title/chapter-{chapter_number}/"
    )
    detected_range: Tuple[float, float] = (0.0, 0.0)
    discovery_strategy: str = "UNKNOWN"
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class CompilationBundle(BaseModel):
    bundle_id: str
    title: str
    chapters: List[SeriesChapter]
    target_duration_minutes: float
    estimated_duration_sec: float
    output_filename: str
    chapter_markers: List[Dict[str, Any]] = Field(default_factory=list)


class BatchVideoConfig(BaseModel):
    source_url: str
    compilation_mode: CompilationMode = CompilationMode.INDIVIDUAL
    target_duration_minutes: Optional[float] = 25.0
    chapter_start: Optional[float] = None
    chapter_end: Optional[float] = None
    chapter_urls: Optional[List[str]] = None
    max_chapters: Optional[int] = None
    video_profile: str = "standard_1080p"
    tts_voice: str = "marcus_male"
    tts_provider: str = "qwen3_tts"
    output_dir: Optional[str] = None
    subtitles: bool = True
    speed_factor: float = 1.0


class BatchJobStatus(BaseModel):
    job_id: str
    series_title: str
    status: str = "QUEUED"  # QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED
    progress: float = 0.0
    total_chapters: int = 0
    completed_chapters: int = 0
    current_chapter: Optional[str] = None
    current_step: Optional[str] = None
    generated_videos: List[str] = Field(default_factory=list)
    compilation_videos: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
