from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Float,
    DateTime,
    Text,
    JSON,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, relationship
from engine.acquisition.models.models import PipelineStage, JobStatus
from engine.acquisition.rights.models import RightsStatus

Base = declarative_base()

def utc_now():
    return datetime.now(timezone.utc)

class ProjectRecord(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    source_type = Column(String(64), nullable=False)
    source_url = Column(String(1024), nullable=True)
    source_metadata = Column(JSON, default=dict, nullable=False)
    rights_status = Column(String(64), default=RightsStatus.UNKNOWN.value, nullable=False)
    license_info = Column(Text, default="", nullable=False)
    workspace_path = Column(String(1024), nullable=False)
    current_stage = Column(String(64), default=PipelineStage.NEW.value, nullable=False)
    settings = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    pages = relationship("PageRecord", back_populates="project", cascade="all, delete-orphan", order_by="PageRecord.sequence")
    jobs = relationship("JobRecord", back_populates="project", cascade="all, delete-orphan", order_by="desc(JobRecord.created_at)")
    panels = relationship("PanelRecord", back_populates="project", cascade="all, delete-orphan", order_by="PanelRecord.sequence")
    normalizations = relationship("NormalizationRecord", back_populates="project", cascade="all, delete-orphan")
    ocr_results = relationship("OCRRecord", back_populates="project", cascade="all, delete-orphan")
    text_regions = relationship("TextRegionRecord", back_populates="project", cascade="all, delete-orphan", order_by="TextRegionRecord.sequence_global")
    narratives = relationship("NarrativeRecord", back_populates="project", cascade="all, delete-orphan")
    characters = relationship("CharacterRecord", back_populates="project", cascade="all, delete-orphan")
    scenes = relationship("SceneRecord", back_populates="project", cascade="all, delete-orphan", order_by="SceneRecord.sequence")
    scripts = relationship("VideoScriptRecord", back_populates="project", cascade="all, delete-orphan", order_by="VideoScriptRecord.created_at.desc()")
    audio_timelines = relationship("AudioTimelineRecord", back_populates="project", cascade="all, delete-orphan", order_by="desc(AudioTimelineRecord.created_at)")
    motion_timelines = relationship("VisualTimelineRecord", back_populates="project", cascade="all, delete-orphan", order_by="desc(VisualTimelineRecord.created_at)")
    renders = relationship("RenderJobRecord", back_populates="project", cascade="all, delete-orphan", order_by="desc(RenderJobRecord.created_at)")


class PageRecord(Base):
    __tablename__ = "pages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    source_url = Column(String(1024), nullable=True)
    content_type = Column(String(64), default="image/jpeg", nullable=False)
    width = Column(Integer, default=0, nullable=False)
    height = Column(Integer, default=0, nullable=False)
    byte_size = Column(BigInteger, default=0, nullable=False)
    sha256 = Column(String(64), default="", nullable=False, index=True)
    downloaded_at = Column(DateTime, default=utc_now, nullable=False)
    status = Column(String(32), default="READY", nullable=False)  # READY, FAILED, PENDING
    error_message = Column(Text, nullable=True)

    project = relationship("ProjectRecord", back_populates="pages")
    panels = relationship("PanelRecord", back_populates="page", cascade="all, delete-orphan", order_by="PanelRecord.page_sequence")
    normalizations = relationship("NormalizationRecord", back_populates="page", cascade="all, delete-orphan", order_by="NormalizationRecord.created_at.desc()")
    text_regions = relationship("TextRegionRecord", back_populates="page", cascade="all, delete-orphan", order_by="TextRegionRecord.sequence_global")


class NormalizationRecord(Base):
    __tablename__ = "page_normalizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    page_id = Column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_sha256 = Column(String(64), nullable=False)
    normalized_sha256 = Column(String(64), nullable=False)
    source_width = Column(Integer, nullable=False)
    source_height = Column(Integer, nullable=False)
    normalized_width = Column(Integer, nullable=False)
    normalized_height = Column(Integer, nullable=False)
    color_space = Column(String(32), default="sRGB", nullable=False)
    orientation = Column(Integer, default=1, nullable=False)
    operations = Column(JSON, default=dict, nullable=False)
    status = Column(String(32), default="SUCCESS", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    page = relationship("PageRecord", back_populates="normalizations")
    project = relationship("ProjectRecord", back_populates="normalizations")


class PanelRecord(Base):
    __tablename__ = "panels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, index=True)
    page_sequence = Column(Integer, nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    normalized_x = Column(Float, default=0.0, nullable=False)
    normalized_y = Column(Float, default=0.0, nullable=False)
    normalized_width = Column(Float, default=0.0, nullable=False)
    normalized_height = Column(Float, default=0.0, nullable=False)
    crop_filename = Column(String(255), nullable=False)
    reading_direction = Column(String(16), default="ltr", nullable=False)
    detection_method = Column(String(32), default="AUTO", nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    panel_type = Column(String(32), default="STANDARD", nullable=False)  # STANDARD, FULL_PAGE, INSET, OVERLAPPING, BORDERLESS, SPLASH, WEBTOON_SEGMENT, UNKNOWN
    status = Column(String(32), default="DETECTED", nullable=False)  # DETECTED, CONFIRMED, NEEDS_REVIEW, IGNORED, MANUAL
    manually_modified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    @property
    def sequence_global(self) -> int:
        return self.sequence

    @sequence_global.setter
    def sequence_global(self, val: int):
        self.sequence = val

    @property
    def sequence_page(self) -> int:
        return self.page_sequence

    @sequence_page.setter
    def sequence_page(self, val: int):
        self.page_sequence = val

    project = relationship("ProjectRecord", back_populates="panels")
    page = relationship("PageRecord", back_populates="panels")
    ocr_result = relationship("OCRRecord", back_populates="panel", uselist=False, cascade="all, delete-orphan")
    text_regions = relationship("TextRegionRecord", back_populates="panel", cascade="all, delete-orphan", order_by="TextRegionRecord.sequence_in_panel")


class OCRRecord(Base):
    __tablename__ = "ocr_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    panel_id = Column(String(36), ForeignKey("panels.id", ondelete="CASCADE"), nullable=False, index=True)
    engine_name = Column(String(64), nullable=False)
    engine_version = Column(String(32), default="1.0", nullable=False)
    raw_blocks = Column(JSON, default=list, nullable=False)  # Immutable raw OCR output
    adapted_blocks = Column(JSON, default=list, nullable=False)  # Dialogue / user edits referencing raw blocks
    full_text = Column(Text, default="", nullable=False)
    confidence_avg = Column(Float, default=1.0, nullable=False)
    status = Column(String(32), default="DETECTED", nullable=False)  # DETECTED, EDITED, APPROVED
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("ProjectRecord", back_populates="ocr_results")
    panel = relationship("PanelRecord", back_populates="ocr_result")


class JobRecord(Base):
    __tablename__ = "jobs"

    job_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(64), nullable=False)
    status = Column(String(32), default=JobStatus.QUEUED.value, nullable=False, index=True)
    progress = Column(Float, default=0.0, nullable=False)
    message = Column(Text, default="", nullable=False)
    input = Column(JSON, default=dict, nullable=False)
    output = Column(JSON, default=dict, nullable=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    project = relationship("ProjectRecord", back_populates="jobs")


class TextRegionRecord(Base):
    __tablename__ = "text_regions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    panel_id = Column(String(36), ForeignKey("panels.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_in_panel = Column(Integer, default=1, nullable=False)
    sequence_global = Column(Integer, default=1, nullable=False, index=True)

    # Geometry relative to panel
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    normalized_x = Column(Float, default=0.0, nullable=False)
    normalized_y = Column(Float, default=0.0, nullable=False)
    normalized_width = Column(Float, default=0.0, nullable=False)
    normalized_height = Column(Float, default=0.0, nullable=False)

    # Geometry relative to page
    page_x = Column(Integer, default=0, nullable=False)
    page_y = Column(Integer, default=0, nullable=False)
    page_width = Column(Integer, default=0, nullable=False)
    page_height = Column(Integer, default=0, nullable=False)

    # Classification & status
    region_type = Column(String(32), default="SPEECH", nullable=False)  # SPEECH, NARRATION, THOUGHT, SFX, CAPTION, UNKNOWN
    confidence = Column(Float, default=1.0, nullable=False)
    status = Column(String(32), default="DETECTED", nullable=False)  # DETECTED, CONFIRMED, MANUAL, NEEDS_REVIEW, IGNORED
    detection_method = Column(String(32), default="AUTO", nullable=False)  # AUTO, MANUAL, FALLBACK_PANEL

    # Crops & Cache
    crop_filename = Column(String(255), default="", nullable=False)
    crop_sha256 = Column(String(64), default="", nullable=False, index=True)

    # Layer 1: Raw Machine OCR (Immutable)
    raw_text = Column(Text, default="", nullable=False)
    raw_confidence = Column(Float, default=0.0, nullable=False)
    raw_polygon = Column(JSON, default=list, nullable=False)
    ocr_engine = Column(String(64), default="", nullable=False)
    ocr_engine_version = Column(String(32), default="", nullable=False)
    ocr_extracted_at = Column(DateTime, nullable=True)

    # Layer 2: Corrected Text (Human Revision)
    corrected_text = Column(Text, default="", nullable=False)
    corrected_by = Column(String(64), default="", nullable=False)
    corrected_at = Column(DateTime, nullable=True)
    correction_status = Column(String(32), default="UNEDITED", nullable=False)  # UNEDITED, EDITED, VERIFIED

    # Layer 3: Speaker Attribution Preparation (Milestone 4 ready)
    speaker_character_id = Column(String(36), nullable=True)
    speaker_confidence = Column(Float, nullable=True)
    speaker_assignment_method = Column(String(32), nullable=True)  # MANUAL, RULE_BASED, LLM_INFERRED

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("ProjectRecord", back_populates="text_regions")
    page = relationship("PageRecord", back_populates="text_regions")
    panel = relationship("PanelRecord", back_populates="text_regions")


class OCRCacheRecord(Base):
    __tablename__ = "ocr_cache"

    cache_key = Column(String(64), primary_key=True)  # SHA256(crop_sha256 + engine_id + engine_version + language + settings_hash)
    crop_sha256 = Column(String(64), nullable=False, index=True)
    engine_id = Column(String(64), nullable=False)
    engine_version = Column(String(32), nullable=False)
    language = Column(String(16), default="en", nullable=False)
    settings_hash = Column(String(64), default="", nullable=False)
    raw_text = Column(Text, default="", nullable=False)
    raw_confidence = Column(Float, default=0.0, nullable=False)
    raw_blocks = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


# ---------------------------------------------------------------------------
# Milestone 4: Narrative Interpretation Models (Layer B)
# ---------------------------------------------------------------------------

class NarrativeRecord(Base):
    __tablename__ = "narratives"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(32), default="1.0", nullable=False)
    language = Column(String(16), default="en", nullable=False)
    status = Column(String(32), default="DRAFT", nullable=False)  # DRAFT, COMPLETE, APPROVED, STALE
    document = Column(JSON, default=dict, nullable=False)  # Full NarrativeDocument schema
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("ProjectRecord", back_populates="narratives")


class CharacterRecord(Base):
    __tablename__ = "characters"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    canonical_name = Column(String(255), nullable=True)
    aliases = Column(JSON, default=list, nullable=False)
    description = Column(Text, default="", nullable=False)
    visual_traits = Column(JSON, default=list, nullable=False)
    role = Column(String(32), default="UNKNOWN", nullable=False)
    first_panel_id = Column(String(36), nullable=True)
    reference_panel_ids = Column(JSON, default=list, nullable=False)
    status = Column(String(32), default="LIKELY", nullable=False)
    manual_override = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("ProjectRecord", back_populates="characters")


class LocationRecord(Base):
    __tablename__ = "locations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    canonical_name = Column(String(255), nullable=True)
    description = Column(Text, default="", nullable=False)
    visual_cues = Column(JSON, default=list, nullable=False)
    panel_ids = Column(JSON, default=list, nullable=False)
    status = Column(String(32), default="LIKELY", nullable=False)
    manual_override = Column(Boolean, default=False, nullable=False)


class SceneRecord(Base):
    __tablename__ = "scenes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, index=True)
    title = Column(String(255), default="", nullable=False)
    panel_start = Column(String(36), nullable=False)
    panel_end = Column(String(36), nullable=False)
    location_id = Column(String(36), nullable=True)
    character_ids = Column(JSON, default=list, nullable=False)
    summary = Column(Text, default="", nullable=False)
    confidence = Column(Float, default=0.85, nullable=False)
    boundary_reason = Column(String(64), default="UNKNOWN", nullable=False)
    manual_override = Column(Boolean, default=False, nullable=False)

    project = relationship("ProjectRecord", back_populates="scenes")


class StoryBeatRecord(Base):
    __tablename__ = "story_beats"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id = Column(String(36), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    panel_ids = Column(JSON, default=list, nullable=False)
    event_ids = Column(JSON, default=list, nullable=False)
    summary = Column(Text, default="", nullable=False)
    dramatic_function = Column(String(64), default="UNKNOWN", nullable=False)
    importance = Column(String(32), default="MEDIUM", nullable=False)
    intensity = Column(Float, default=0.5, nullable=False)
    confidence = Column(Float, default=0.85, nullable=False)
    music_intent = Column(String(64), nullable=True)
    sfx_intent = Column(String(64), nullable=True)


class EventRecord(Base):
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(32), default="OTHER", nullable=False)
    actor_character_id = Column(String(36), nullable=True)
    target_character_id = Column(String(36), nullable=True)
    object_name = Column(String(255), nullable=True)
    location_id = Column(String(36), nullable=True)
    panel_ids = Column(JSON, default=list, nullable=False)
    description = Column(Text, default="", nullable=False)
    confidence = Column(Float, default=0.85, nullable=False)
    evidence = Column(JSON, default=dict, nullable=False)


# ---------------------------------------------------------------------------
# Milestone 4: Video Script Adaptation Models (Layer C)
# ---------------------------------------------------------------------------

class VideoScriptRecord(Base):
    __tablename__ = "video_scripts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(32), default="1.0", nullable=False)
    adaptation_profile = Column(String(64), default="FAITHFUL", nullable=False)
    estimated_duration = Column(Float, default=0.0, nullable=False)
    language = Column(String(16), default="en", nullable=False)
    status = Column(String(32), default="DRAFT", nullable=False)  # DRAFT, VALIDATED, APPROVED
    quality_metrics = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("ProjectRecord", back_populates="scripts")
    segments = relationship("ScriptSegmentRecord", back_populates="script", cascade="all, delete-orphan", order_by="ScriptSegmentRecord.sequence")

    @property
    def is_approved(self) -> bool:
        return self.status == "APPROVED"

    @property
    def script_id(self) -> str:
        return self.id


class ScriptSegmentRecord(Base):
    __tablename__ = "script_segments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    script_id = Column(String(36), ForeignKey("video_scripts.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), nullable=False, index=True)
    scene_id = Column(String(36), nullable=False)
    beat_id = Column(String(36), nullable=True)
    sequence = Column(Integer, nullable=False)
    type = Column(String(32), default="CHARACTER_DIALOGUE", nullable=False)
    speaker_character_id = Column(String(36), nullable=True)
    text = Column(Text, default="", nullable=False)
    emotion = Column(String(32), default="NEUTRAL", nullable=False)
    intensity = Column(Float, default=0.5, nullable=False)
    estimated_duration = Column(Float, default=2.0, nullable=False)
    estimated_start = Column(Float, default=0.0, nullable=False)
    estimated_end = Column(Float, default=2.0, nullable=False)
    source_evidence = Column(JSON, default=dict, nullable=False)
    production_intent = Column(Text, default="", nullable=False)
    music_intent = Column(String(64), nullable=True)
    sfx_intent = Column(String(64), nullable=True)
    motion_intent = Column(String(64), nullable=True)
    faithfulness_status = Column(String(32), default="SUPPORTED", nullable=False)
    manual_override = Column(Boolean, default=False, nullable=False)

    @property
    def is_manual_override(self) -> bool:
        return self.manual_override

    script = relationship("VideoScriptRecord", back_populates="segments")


# ---------------------------------------------------------------------------
# Milestone 8: Audio, Motion, and Render Models (Layer D & Final Video Delivery)
# ---------------------------------------------------------------------------

class AudioTimelineRecord(Base):
    __tablename__ = "audio_timelines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="DRAFT", nullable=False)  # DRAFT, APPROVED
    total_duration = Column(Float, default=0.0, nullable=False)
    timeline_json = Column(JSON, default=dict, nullable=False)
    voice_casting = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("ProjectRecord", back_populates="audio_timelines")


class VisualTimelineRecord(Base):
    __tablename__ = "motion_timelines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="DRAFT", nullable=False)  # DRAFT, APPROVED
    total_duration = Column(Float, default=0.0, nullable=False)
    total_shots = Column(Integer, default=0, nullable=False)
    style_preset = Column(String(64), default="cinematic", nullable=False)
    timeline_json = Column(JSON, default=dict, nullable=False)
    overrides_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("ProjectRecord", back_populates="motion_timelines")


class RenderJobRecord(Base):
    __tablename__ = "render_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="QUEUED", nullable=False)  # QUEUED, PREPARING, COMPOSING, ENCODING, MUXING, VALIDATING, COMPLETE, FAILED, CANCELLED
    current_stage = Column(String(32), default="QUEUED", nullable=False)
    progress = Column(Float, default=0.0, nullable=False)
    frames_done = Column(Integer, default=0, nullable=False)
    frames_total = Column(Integer, default=0, nullable=False)
    output_profile = Column(String(64), default="standard_1080p", nullable=False)
    output_path = Column(String(1024), default="", nullable=False)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    validation_status = Column(String(32), nullable=True)  # VALID, INVALID
    validation_report = Column(JSON, default=dict, nullable=False)
    render_plan_hash = Column(String(64), default="", nullable=False)
    visual_timeline_hash = Column(String(64), default="", nullable=False)
    master_audio_timeline_hash = Column(String(64), default="", nullable=False)
    contact_sheet_path = Column(String(1024), nullable=True)
    metrics = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("ProjectRecord", back_populates="renders")

    @property
    def render_id(self) -> str:
        return self.id


