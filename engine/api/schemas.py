from pydantic import BaseModel, Field
from engine.acquisition.models import SourceType, PipelineStage
from engine.acquisition.rights.models import RightsStatus

class ProjectCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    source_type: SourceType
    source_url: str | None = None
    rights_status: RightsStatus
    license_info: str = ""
    source_metadata: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    id: str
    title: str
    source_type: str
    source_url: str | None
    source_metadata: dict
    rights_status: str
    license_info: str
    workspace_path: str
    current_stage: str
    settings: dict
    created_at: str
    updated_at: str
    total_pages: int = 0
    ready_pages: int = 0
    failed_pages: int = 0
    stale_stages: list[str] = Field(default_factory=list)


class PageResponse(BaseModel):
    id: str
    project_id: str
    sequence: int
    filename: str
    source_url: str | None
    content_type: str
    width: int
    height: int
    byte_size: int
    sha256: str
    status: str
    error_message: str | None
    downloaded_at: str
    image_url: str


class PageReorderRequest(BaseModel):
    page_ids: list[str]


class PageRotateRequest(BaseModel):
    degrees: int = Field(default=90, description="Degrees to rotate clockwise (90, 180, 270)")


class SourceInspectRequest(BaseModel):
    source: str = Field(..., description="Local path, archive path, or URL")


class SourceInspectResponse(BaseModel):
    adapter_id: str
    is_valid: bool
    source_type: str
    title_suggestion: str | None
    total_pages_detected: int
    chapters: list[dict] = Field(default_factory=list)
    error: str | None = None


class JobResponse(BaseModel):
    job_id: str
    project_id: str
    job_type: str
    status: str
    progress: float
    message: str
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    error: str | None = None
    priority: int = 10
    depends_on_job_id: str | None = None
    requires_gpu: bool = False
    gpu_vram_mb: int = 0
    cpu_units: int = 1
    worker_lease_id: str | None = None
    lease_expires_at: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None



class NormalizeProjectRequest(BaseModel):
    target_width: int = Field(default=1920, ge=640, le=7680)


class DetectPanelsRequest(BaseModel):
    reading_direction: str = Field(default="ltr", pattern="^(ltr|rtl|vertical|auto|custom)$")
    min_area_ratio: float = Field(default=0.02, ge=0.005, le=0.5)
    profile: str = "AUTO"


class PanelCreateRequest(BaseModel):
    page_id: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    panel_type: str = "STANDARD"


class PanelUpdateRequest(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    status: str | None = None
    panel_type: str | None = None


class PanelSplitRequest(BaseModel):
    split_type: str = Field(default="horizontal", pattern="^(horizontal|vertical)$")
    ratio: float = Field(default=0.5, gt=0.05, lt=0.95)


class PanelMergeRequest(BaseModel):
    panel_ids: list[str]


class PanelReorderRequest(BaseModel):
    panel_ids: list[str]


class PanelResponse(BaseModel):
    id: str
    project_id: str
    page_id: str
    sequence: int
    page_sequence: int
    x: int
    y: int
    width: int
    height: int
    normalized_x: float = 0.0
    normalized_y: float = 0.0
    normalized_width: float = 0.0
    normalized_height: float = 0.0
    crop_filename: str
    reading_direction: str
    detection_method: str = "AUTO"
    confidence: float = 1.0
    panel_type: str = "STANDARD"
    status: str = "DETECTED"
    manually_modified: bool = False
    created_at: str
    image_url: str


class OCREngineInfo(BaseModel):
    engine_id: str
    display_name: str
    description: str
    registered: bool = True
    installed: bool = False
    configured: bool = False
    is_available: bool = False
    is_verified: bool = False
    status_label: str = "Configuration required"
    diagnostic_message: str = ""


class OCRExtractRequest(BaseModel):
    engine_id: str = "mock_ocr"
    language: str = "en"


class AdaptedBlockUpdateRequest(BaseModel):
    speaker: str | None = None
    text: str
    classification: str = "dialogue"
    notes: str = ""


class OCRResponse(BaseModel):
    id: str
    project_id: str
    panel_id: str
    engine_name: str
    engine_version: str
    raw_blocks: list[dict]
    adapted_blocks: list[dict]
    full_text: str
    confidence_avg: float
    status: str


class TextRegionCreateRequest(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    region_type: str = "SPEECH"


class TextRegionUpdateRequest(BaseModel):
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    region_type: str | None = None
    status: str | None = None
    # Layer 2 human correction
    corrected_text: str | None = None
    corrected_by: str | None = None
    correction_status: str | None = None
    # Layer 3 speaker preparation
    speaker_character_id: str | None = None
    speaker_confidence: float | None = None
    speaker_assignment_method: str | None = None


class TextRegionResponse(BaseModel):
    id: str
    project_id: str
    page_id: str
    panel_id: str
    sequence_in_panel: int
    sequence_global: int
    x: int
    y: int
    width: int
    height: int
    normalized_x: float = 0.0
    normalized_y: float = 0.0
    normalized_width: float = 0.0
    normalized_height: float = 0.0
    page_x: int = 0
    page_y: int = 0
    page_width: int = 0
    page_height: int = 0
    region_type: str
    confidence: float
    status: str
    detection_method: str
    crop_filename: str = ""
    crop_sha256: str = ""
    # Layer 1: Machine OCR (Immutable)
    raw_text: str = ""
    raw_confidence: float = 0.0
    raw_polygon: list = Field(default_factory=list)
    ocr_engine: str = ""
    ocr_engine_version: str = ""
    # Layer 2: Corrected Text (Human Revision)
    corrected_text: str = ""
    corrected_by: str = ""
    correction_status: str = "UNEDITED"
    # Layer 3: Speaker Attribution (Milestone 4 ready)
    speaker_character_id: str | None = None
    speaker_confidence: float | None = None
    speaker_assignment_method: str | None = None
    image_url: str = ""


class BlurRegionRequest(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    blur_radius: int = 24
    feather: int = 4


class BlurTextRequest(BaseModel):
    region_ids: list[str] | None = None
    blur_radius: int = 24
    feather: int = 4


class BlurPanelRequest(BaseModel):
    blur_radius: int = 32


class BlurStatusResponse(BaseModel):
    is_blurred: bool
    has_backup: bool
    blurred_regions_count: int


class BatchBlurRequest(BaseModel):
    preset: str = "TOP_WATERMARK"
    height_px: int = 80
    blur_radius: int = 24
    feather: int = 6
    panel_ids: list[str] | None = None


class BatchResetRequest(BaseModel):
    panel_ids: list[str] | None = None


