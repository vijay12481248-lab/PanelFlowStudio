from enum import Enum
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from engine.acquisition.rights.models import RightsStatus, RightsDeclaration


class PipelineStage(str, Enum):
    NEW = "NEW"
    RIGHTS_APPROVED = "RIGHTS_APPROVED"
    ACQUIRED = "ACQUIRED"
    NORMALIZED = "NORMALIZED"
    PANELS_DETECTED = "PANELS_DETECTED"
    OCR_COMPLETE = "OCR_COMPLETE"
    OCR_APPROVED = "OCR_APPROVED"
    STORY_ANALYZED = "STORY_ANALYZED"
    STORY_APPROVED = "STORY_APPROVED"
    SCRIPT_GENERATED = "SCRIPT_GENERATED"
    SCRIPT_APPROVED = "SCRIPT_APPROVED"
    VOICE_GENERATED = "VOICE_GENERATED"
    AUDIO_APPROVED = "AUDIO_APPROVED"
    SHOT_PLAN_GENERATED = "SHOT_PLAN_GENERATED"
    MOTION_APPROVED = "MOTION_APPROVED"
    RENDERED = "RENDERED"
    QA_APPROVED = "QA_APPROVED"
    EXPORTED = "EXPORTED"


class SourceType(str, Enum):
    LOCAL_FOLDER = "LOCAL_FOLDER"
    ZIP_ARCHIVE = "ZIP_ARCHIVE"
    AUTHORIZED_WEB = "AUTHORIZED_WEB"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(str, Enum):
    ACQUISITION = "ACQUISITION"
    RETRY_PAGES = "RETRY_PAGES"
    PAGE_ROTATE = "PAGE_ROTATE"
    PROJECT_INIT = "PROJECT_INIT"
    NORMALIZATION = "NORMALIZATION"
    PANEL_DETECTION = "PANEL_DETECTION"
    OCR_EXTRACTION = "OCR_EXTRACTION"
    STORY_ANALYSIS = "STORY_ANALYSIS"
    SCRIPT_GENERATION = "SCRIPT_GENERATION"
    AUDIO_GENERATION = "AUDIO_GENERATION"
    MOTION_PLANNING = "MOTION_PLANNING"
    RENDER = "RENDER"


class PageCandidate(BaseModel):
    sequence: int = Field(..., description="1-based candidate sequence order")
    source_uri: str = Field(..., description="Absolute local path or remote URL")
    suggested_filename: str | None = None
    extra_metadata: dict = Field(default_factory=dict)


class ChapterInfo(BaseModel):
    id: str
    title: str
    sequence: int = 1
    source_uri: str
    page_count: int | None = None
    extra_metadata: dict = Field(default_factory=dict)


class SourceMetadata(BaseModel):
    title: str | None = None
    author: str | None = None
    description: str | None = None
    language: str | None = None
    suggested_reading_direction: str = "ltr"  # ltr (comic/webtoon) or rtl (manga)
    license_declared: str | None = None
    source_url: str | None = None
    extra: dict = Field(default_factory=dict)


class SourceInspectionResult(BaseModel):
    adapter_id: str
    is_valid: bool
    source_type: SourceType
    title_suggestion: str | None = None
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)
    chapters: list[ChapterInfo] = Field(default_factory=list)
    total_pages_detected: int = 0
    error: str | None = None


class DownloadedPageResult(BaseModel):
    sequence: int
    source_uri: str
    target_path: Path | None = None
    filename: str = ""
    content_type: str = "image/jpeg"
    width: int = 0
    height: int = 0
    byte_size: int = 0
    sha256: str = ""
    success: bool = True
    error_message: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ManifestPage(BaseModel):
    id: str = Field(..., description="Permanent UUID for this page")
    sequence: int = Field(..., description="1-based page order")
    filename: str = Field(..., description="Local sanitized filename in source/")
    source_url: str | None = None
    sha256: str = Field(..., description="SHA-256 hash of the verified image file")
    width: int
    height: int
    bytes: int = Field(..., description="Byte size of the image file")
    content_type: str = "image/jpeg"
    status: str = "READY"
    error_message: str | None = None


class AcquisitionManifest(BaseModel):
    project_id: str
    version: str = "1.0"
    created_at: str
    updated_at: str
    source: dict = Field(default_factory=dict)
    rights: dict = Field(default_factory=dict)
    chapter: dict = Field(default_factory=dict)
    pages: list[ManifestPage] = Field(default_factory=list)
