export type RightsStatus =
  | "UNKNOWN"
  | "PUBLIC_DOMAIN"
  | "CREATIVE_COMMONS"
  | "LICENSED"
  | "USER_OWNED"
  | "EXPLICIT_PERMISSION";

export type SourceType = "LOCAL_FOLDER" | "ZIP_ARCHIVE" | "AUTHORIZED_WEB";

export type PipelineStage =
  | "NEW"
  | "RIGHTS_APPROVED"
  | "ACQUIRED"
  | "NORMALIZED"
  | "PANELS_DETECTED"
  | "OCR_COMPLETE"
  | "OCR_APPROVED"
  | "STORY_ANALYZED"
  | "STORY_APPROVED"
  | "SCRIPT_GENERATED"
  | "SCRIPT_APPROVED"
  | "VOICE_GENERATED"
  | "AUDIO_APPROVED"
  | "SHOT_PLAN_GENERATED"
  | "MOTION_APPROVED"
  | "RENDERED"
  | "QA_APPROVED"
  | "EXPORTED";

export type JobStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";

export type JobType =
  | "ACQUISITION"
  | "RETRY_PAGES"
  | "PAGE_ROTATE"
  | "PROJECT_INIT"
  | "NORMALIZATION"
  | "PANEL_DETECTION"
  | "OCR_EXTRACTION"
  | "STORY_ANALYSIS"
  | "AUDIO_GENERATION"
  | "MOTION_PLANNING"
  | "RENDER";

export interface Project {
  id: string;
  title: string;
  source_type: SourceType;
  source_url: string | null;
  source_metadata: Record<string, any>;
  rights_status: RightsStatus;
  license_info: string;
  workspace_path: string;
  current_stage: PipelineStage;
  settings: Record<string, any>;
  created_at: string;
  updated_at: string;
  total_pages: number;
  ready_pages: number;
  failed_pages: number;
  stale_stages?: string[];
}

export interface Page {
  id: string;
  project_id: string;
  sequence: number;
  filename: string;
  source_url: string | null;
  content_type: string;
  width: number;
  height: number;
  byte_size: number;
  sha256: string;
  status: "READY" | "FAILED" | "PENDING";
  error_message: string | null;
  downloaded_at: string;
  image_url: string;
}

export type ReadingDirection = "ltr" | "rtl" | "vertical" | "auto" | "custom";
export type PanelType =
  | "STANDARD"
  | "FULL_PAGE"
  | "INSET"
  | "OVERLAPPING"
  | "BORDERLESS"
  | "SPLASH"
  | "WEBTOON_SEGMENT"
  | "UNKNOWN";
export type PanelStatus = "DETECTED" | "CONFIRMED" | "NEEDS_REVIEW" | "IGNORED" | "MANUAL" | "APPROVED";

export interface Panel {
  id: string;
  project_id: string;
  page_id: string;
  sequence: number;
  page_sequence: number;
  x: number;
  y: number;
  width: number;
  height: number;
  normalized_x?: number;
  normalized_y?: number;
  normalized_width?: number;
  normalized_height?: number;
  crop_filename: string;
  reading_direction: ReadingDirection | string;
  detection_method?: "AUTO" | "MANUAL" | "FALLBACK" | string;
  confidence: number;
  panel_type?: PanelType | string;
  status: PanelStatus | string;
  manually_modified?: boolean;
  created_at: string;
  image_url: string;
}

export interface Job {
  job_id: string;
  project_id: string;
  job_type: JobType | string;
  status: JobStatus;
  progress: number;
  message: string;
  input: Record<string, any>;
  output: Record<string, any>;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface SourceInspection {
  adapter_id: string;
  is_valid: boolean;
  source_type: SourceType;
  title_suggestion: string | null;
  total_pages_detected: number;
  chapters: Array<{
    id: string;
    title: string;
    sequence: number;
    source_uri: string;
    page_count: number | null;
  }>;
  error: string | null;
}

export interface ManifestPage {
  id: string;
  sequence: number;
  filename: string;
  source_url: string | null;
  sha256: string;
  width: number;
  height: number;
  bytes: number;
  content_type: string;
  status: string;
  error_message: string | null;
}

export interface AcquisitionManifest {
  project_id: string;
  version: string;
  created_at: string;
  updated_at: string;
  source: Record<string, any>;
  rights: Record<string, any>;
  chapter: Record<string, any>;
  pages: ManifestPage[];
}

export interface OCRRegion {
  id: string;
  panel_id?: string;
  reading_order: number;
  detected_text: string;
  confidence: number;
  bbox: [number, number, number, number];
  polygon?: [number, number][];
  language: string;
}

export interface AdaptedTextBlock {
  id: string;
  raw_region_id: string;
  speaker?: string | null;
  text: string;
  classification: "dialogue" | "narration" | "thought" | "sfx" | "caption";
  notes?: string;
}

export interface OCRRecord {
  id: string;
  project_id: string;
  panel_id: string;
  engine_name: string;
  engine_version: string;
  raw_blocks: OCRRegion[];
  adapted_blocks: AdaptedTextBlock[];
  full_text: string;
  confidence_avg: number;
  status: "DETECTED" | "EDITED" | "APPROVED";
}

export interface OCREngineInfo {
  engine_id: string;
  display_name: string;
  description: string;
  registered?: boolean;
  installed?: boolean;
  configured?: boolean;
  is_available: boolean;
  is_verified?: boolean;
  status_label?: string;
  diagnostic_message?: string;
}

export type TextRegionType =
  | "SPEECH"
  | "NARRATION"
  | "THOUGHT"
  | "SFX"
  | "CAPTION"
  | "UNKNOWN";

export type TextRegionStatus = "DETECTED" | "CONFIRMED" | "NEEDS_REVIEW" | "REJECTED";
export type TextCorrectionStatus = "UNEDITED" | "EDITED" | "VERIFIED";
export type SpeakerAssignmentMethod = "MANUAL" | "RULE_TAIL" | "PROXIMITY" | "LLM_INFERRED";

export interface TextRegion {
  id: string;
  project_id: string;
  page_id: string;
  panel_id: string;
  sequence_in_panel: number;
  sequence_global: number;
  x: number;
  y: number;
  width: number;
  height: number;
  normalized_x: number;
  normalized_y: number;
  normalized_width: number;
  normalized_height: number;
  page_x: number;
  page_y: number;
  page_width: number;
  page_height: number;
  region_type: TextRegionType | string;
  confidence: number;
  status: TextRegionStatus | string;
  detection_method: "AUTO" | "MANUAL" | "FALLBACK" | string;
  crop_filename: string;
  crop_sha256?: string;
  raw_text?: string | null;
  raw_confidence?: number | null;
  raw_polygon?: [number, number][];
  ocr_engine?: string | null;
  ocr_engine_version?: string | null;
  corrected_text?: string | null;
  corrected_by?: string | null;
  correction_status?: TextCorrectionStatus | string;
  speaker_character_id?: string | null;
  speaker_confidence?: number | null;
  speaker_assignment_method?: SpeakerAssignmentMethod | string | null;
  image_url: string;
}

export interface CanonicalExportContract {
  project_id: string;
  title: string;
  current_stage: PipelineStage | string;
  rights: {
    status: RightsStatus | string;
    license_info: string;
  };
  exported_at: string;
  pages: Array<{
    id: string;
    sequence: number;
    filename: string;
    width: number;
    height: number;
    sha256: string;
  }>;
  panels: Array<{
    id: string;
    page_id: string;
    sequence_global: number;
    sequence_page: number;
    bbox: [number, number, number, number];
    normalized_bbox: [number, number, number, number];
    reading_direction: string;
    panel_type: string;
    status: string;
  }>;
  text_regions: Array<{
    id: string;
    page_id: string;
    panel_id: string;
    sequence_in_panel: number;
    sequence_global: number;
    bbox: [number, number, number, number];
    normalized_bbox: [number, number, number, number];
    page_bbox: [number, number, number, number];
    region_type: string;
    status: string;
    detection_method: string;
    raw_ocr: {
      text: string | null;
      confidence: number | null;
      polygon?: [number, number][];
      engine: string | null;
      engine_version: string | null;
      extracted_at: string | null;
    };
    corrected_text: {
      text: string | null;
      corrected_by: string | null;
      status: string;
      corrected_at: string | null;
    };
    speaker: {
      character_id: string | null;
      confidence: number | null;
      assignment_method: string | null;
    };
  }>;
}

// ---------------------------------------------------------------------------
// Milestone 4: Story Understanding & Narrative IR (Layer B)
// ---------------------------------------------------------------------------

export type CharacterRole =
  | "UNKNOWN"
  | "PROTAGONIST"
  | "ANTAGONIST"
  | "SUPPORTING"
  | "MINOR";

export type CharacterStatus = "CONFIRMED" | "LIKELY" | "UNCERTAIN" | "MANUAL";

export interface ProvenanceReference {
  panel_ids: string[];
  text_region_ids: string[];
  confidence: number;
}

export interface CharacterEntity {
  character_id: string;
  project_id: string;
  display_name: string;
  canonical_name: string;
  aliases: string[];
  description: string;
  visual_traits: string[];
  role: CharacterRole | string;
  first_panel_id?: string | null;
  reference_panel_ids: string[];
  status: CharacterStatus | string;
  manual_override: boolean;
}

export interface LocationEntity {
  location_id: string;
  name: string;
  canonical_name?: string | null;
  description: string;
  visual_cues: string[];
  panel_ids: string[];
  status: CharacterStatus | string;
  manual_override: boolean;
}

export interface SpeakerAttributionEntity {
  text_region_id: string;
  speaker_character_id: string;
  confidence: number;
  method: string;
  evidence_panel_ids: string[];
  reason_code: string;
}

export interface UtteranceEntity {
  utterance_id: string;
  text_region_id: string;
  panel_id: string;
  speaker_character_id?: string | null;
  source_text: string;
  corrected_text: string;
  utterance_type: "DIALOGUE" | "NARRATION" | "THOUGHT" | "WHISPER" | "SHOUT" | "SFX" | "OTHER";
  emotion: string;
  emotion_confidence: number;
  intensity: number;
  valence: number;
  arousal: number;
  sequence: number;
  provenance: ProvenanceReference;
}

export interface EventEntity {
  event_id: string;
  event_type: string;
  actor_character_id?: string | null;
  target_character_id?: string | null;
  object_name?: string | null;
  location_id?: string | null;
  panel_ids: string[];
  description: string;
  confidence: number;
  evidence: ProvenanceReference;
}

export interface SceneEntity {
  scene_id: string;
  sequence: number;
  title: string;
  panel_start: string;
  panel_end: string;
  location_id?: string | null;
  character_ids: string[];
  summary: string;
  confidence: number;
  boundary_reason: string;
  manual_override: boolean;
}

export interface StoryBeatEntity {
  beat_id: string;
  scene_id: string;
  sequence: number;
  panel_ids: string[];
  event_ids: string[];
  summary: string;
  dramatic_function: string;
  importance: "HIGH" | "MEDIUM" | "LOW";
  intensity: number;
  confidence: number;
  music_intent?: string | null;
  sfx_intent?: string | null;
}

export interface ContinuityWarningEntity {
  warning_id: string;
  warning_type: string;
  severity: "INFO" | "WARNING" | "ERROR";
  message: string;
  entity_type: string;
  entity_id: string;
  panel_ids: string[];
  resolved: boolean;
}

export interface NarrativeDocument {
  project_id: string;
  characters: CharacterEntity[];
  locations: LocationEntity[];
  scenes: SceneEntity[];
  beats: StoryBeatEntity[];
  events: EventEntity[];
  utterances: UtteranceEntity[];
  speaker_attributions: SpeakerAttributionEntity[];
  continuity_warnings: ContinuityWarningEntity[];
  analysis_metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Milestone 4: Video Script Adaptation (Layer C)
// ---------------------------------------------------------------------------

export type AdaptationProfile =
  | "FAITHFUL"
  | "CONDENSED"
  | "DRAMATIC_NARRATION"
  | "ACCESSIBLE_RECAP";

export type SegmentType = "NARRATOR" | "CHARACTER_DIALOGUE";

export interface ScriptSegment {
  segment_id: string;
  scene_id: string;
  beat_id?: string | null;
  sequence: number;
  type: SegmentType;
  speaker_character_id?: string | null;
  text: string;
  emotion: string;
  intensity: number;
  estimated_duration: number;
  estimated_start: number;
  estimated_end: number;
  source_evidence: ProvenanceReference;
  production_intent: string;
  music_intent?: string | null;
  sfx_intent?: string | null;
  motion_intent?: string | null;
  faithfulness_status: "SUPPORTED" | "WEAKLY_SUPPORTED" | "UNSUPPORTED";
  manual_override: boolean;
}

export interface VideoScript {
  script_id: string;
  project_id: string;
  version: string;
  adaptation_profile: AdaptationProfile;
  segments: ScriptSegment[];
  estimated_duration: number;
  language: string;
  status: "DRAFT" | "VALIDATED" | "APPROVED";
  quality_metrics: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ScriptValidationReport {
  script_id: string;
  total_segments: number;
  supported_segments: number;
  weakly_supported_segments: number;
  unsupported_segments: number;
  coverage_score: number;
  issues: Array<{
    segment_id?: string;
    sequence?: number;
    text?: string;
    issues?: string[];
    grounding_score?: number;
  }>;
  passed: boolean;
}

export interface LLMProviderInfo {
  provider_id: string;
  provider_name: string;
  is_local: boolean;
  is_multimodal: boolean;
  is_healthy: boolean;
  context_window?: number;
}

// ---------------------------------------------------------------------------
// Milestone 6 & 8: Audio Director Interfaces
// ---------------------------------------------------------------------------

export interface AudioInterval {
  interval_id: string;
  timeline_source_type: "SPEECH" | "BGM" | "SFX" | "AMBIENCE";
  audio_file_uri: string;
  start_time: number;
  end_time: number;
  duration: number;
  gain_db: number;
  script_segment_id?: string;
  panel_id?: string;
  scene_id?: string;
  character_id?: string;
  cue_text?: string;
  is_voice: boolean;
}

export interface MasterAudioTimeline {
  timeline_id: string;
  project_id: string;
  total_duration_sec: number;
  sample_rate_hz: number;
  channels: number;
  speech_intervals_count: number;
  bgm_tracks_count: number;
  intervals: AudioInterval[];
  bgm_file_path?: string;
}

export interface AudioTimelineResponse {
  id: string;
  project_id: string;
  status: "DRAFT" | "APPROVED";
  total_duration: number;
  voice_casting: Record<string, string>;
  timeline: MasterAudioTimeline;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Milestone 6 & 8: Motion Director Interfaces
// ---------------------------------------------------------------------------

export type MotionStylePreset =
  | "cinematic"
  | "action_dynamic"
  | "slow_burn"
  | "minimal"
  | "webtoon_scroll";

export interface CameraFraming {
  center_x: number;
  center_y: number;
  width: number;
  height: number;
}

export interface Shot {
  shot_id: string;
  source_asset_id: string;
  panel_id?: string;
  scene_id?: string;
  script_segment_id?: string;
  start_time_sec: number;
  end_time_sec: number;
  duration_sec: number;
  motion_type: string;
  camera_start: CameraFraming;
  camera_end: CameraFraming;
  easing: string;
  transition_in?: string;
  transition_duration_sec?: number;
  hold_duration_sec?: number;
}

export interface VisualTimeline {
  timeline_id: string;
  project_id: string;
  total_duration_sec: number;
  total_shots: number;
  style_preset: string;
  shots: Shot[];
  warnings?: string[];
  hash?: string;
}

export interface MotionTimelineResponse {
  id: string;
  project_id: string;
  status: "DRAFT" | "APPROVED";
  total_duration: number;
  total_shots: number;
  style_preset: string;
  warnings_count?: number;
  timeline: VisualTimeline;
  overrides?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Milestone 7 & 8: Production Renderer Interfaces
// ---------------------------------------------------------------------------

export type RenderStatus =
  | "QUEUED"
  | "PREPARING"
  | "COMPOSING"
  | "ENCODING"
  | "MUXING"
  | "VALIDATING"
  | "COMPLETE"
  | "FAILED"
  | "CANCELLED";

export interface RenderProfileConfig {
  name: string;
  width: number;
  height: number;
  fps: number;
  video_bitrate_kbps: number;
  audio_bitrate_kbps: number;
  codec: string;
  audio_codec: string;
  pixel_format: string;
}

export interface RenderValidationReport {
  is_valid: boolean;
  video_valid: boolean;
  audio_valid: boolean;
  sync_valid: boolean;
  black_frames_count: number;
  timeline_gaps_count: number;
  clipping_samples_count: number;
  duration_sec: number;
  warnings: string[];
  ffprobe_meta?: Record<string, any>;
}

export interface RenderJob {
  render_id: string;
  project_id: string;
  status: RenderStatus;
  current_stage: string;
  progress: number;
  frames_done: number;
  frames_total: number;
  elapsed_sec?: number;
  output_profile: string;
  output_path: string;
  error_code?: string | null;
  error_message?: string | null;
  validation_status?: string | null;
  validation_report?: RenderValidationReport | null;
  render_plan_hash?: string;
  visual_timeline_hash?: string;
  master_audio_timeline_hash?: string;
  contact_sheet_path?: string | null;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ProviderHealth {
  id: string;
  name: string;
  category: "video_engine" | "audio_engine" | "story_intelligence" | "acquisition_engine";
  status:
    | "HEALTHY"
    | "READY"
    | "DEGRADED"
    | "OFFLINE"
    | "STOPPED"
    | "NOT_RUNNING"
    | "MISSING"
    | "UNSUPPORTED"
    | "ERROR"
    | "BROWSER_RUNTIME_MISSING"
    | string;
  version: string;
  path: string;
  required: boolean;
  details: string;
}

export interface SystemProvidersResponse {
  providers: ProviderHealth[];
  system_ready: boolean;
}

export interface HardwareDiagnostics {
  os_name: string;
  os_release: string;
  architecture: string;
  cpu_count: number;
  total_ram_gb: number;
  available_ram_gb: number;
  total_disk_gb: number;
  free_disk_gb: number;
  gpu_name: string;
  vram_mb: number;
  cuda_available: boolean;
  ffmpeg_available: boolean;
  ffmpeg_hwaccels: string[];
  neural_performance_tier: "GOOD" | "SUPPORTED" | "LIMITED" | "UNSUPPORTED";
  recommendations: string;
}

export interface SanitizedDiagnostics {
  panelflow_version: string;
  diagnostic_schema: string;
  generated_at: string;
  hardware: {
    os: string;
    cpu_cores: number;
    total_ram_gb: number;
    free_disk_gb: number;
    gpu: string;
    vram_mb: number;
    tier: string;
  };
  providers: Array<{
    id: string;
    name: string;
    status: string;
    version: string;
    required: boolean;
  }>;
  system_metrics: {
    total_projects: number;
    total_renders: number;
    failed_renders: number;
  };
  recent_job_failures: Array<{
    job_id: string;
    error_code?: string;
    error_message?: string;
    stage?: string;
    created_at?: string;
  }>;
  privacy_notice: string;
}



