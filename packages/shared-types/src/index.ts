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
  polygon_json?: string | null;
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
  priority?: number;
  depends_on_job_id?: string | null;
  requires_gpu?: boolean;
  gpu_vram_mb?: number;
  cpu_units?: number;
  worker_lease_id?: string | null;
  lease_expires_at?: string | null;
  retry_count?: number;
  max_retries?: number;
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

export type CharacterChangeStatus = "NONE" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";

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
  role: CharacterRole;
  first_panel_id?: string | null;
  reference_panel_ids: string[];
  status: CharacterStatus;
  manual_override: boolean;
  reference_asset_id?: string | null;
  generation_params?: Record<string, unknown>;
  proposed_changes?: Record<string, unknown>;
  change_status?: CharacterChangeStatus;
  created_at?: string;
  updated_at?: string;
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
    status?: string;
    reasons?: string[];
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

export interface CloudLLMConfig {
  provider_type: "openrouter" | "groq" | "custom_openai" | string;
  endpoint_url: string;
  has_api_key?: boolean;
  masked_api_key?: string;
  api_key?: string;
  model_name: string;
  custom_models?: string[];
  is_active?: boolean;
}

export interface CloudLLMTestRequest {
  endpoint_url: string;
  api_key?: string;
  model_name?: string;
}

export interface CloudLLMTestResponse {
  status: "HEALTHY" | "DEGRADED" | "ERROR";
  connected: boolean;
  latency_ms: number;
  models_count: number;
  models: string[];
  error?: string | null;
}

export interface AvailableLLMProviderItem {
  id: string;
  name: string;
  type: "local" | "cloud";
  endpoint: string;
  models: string[];
  active_model: string;
  is_healthy?: boolean;
  is_configured?: boolean;
  is_active?: boolean;
}

export interface AvailableLLMProvidersResponse {
  providers: AvailableLLMProviderItem[];
}

export interface FlowOverrideConfig {
  provider_id: string;
  model_name?: string;
}

export interface ProviderCatalogItem {
  id: string;
  name: string;
  type: "local" | "gateway" | "cloud" | "custom" | string;
  is_configured: boolean;
  is_healthy: boolean;
  endpoint?: string;
  models: string[];
  default_model?: string;
}

export interface GlobalLLMSettings {
  global_default_provider: string;
  global_default_model: string;
  flow_overrides: Record<string, FlowOverrideConfig>;
  providers?: ProviderCatalogItem[];
}

export interface SaveGlobalLLMSettingsRequest {
  global_default_provider: string;
  global_default_model: string;
  flow_overrides?: Record<string, FlowOverrideConfig>;
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
  warnings?: string[];
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

export interface YouTubeThumbnailResearch {
  aspect_ratio: "16:9" | "9:16" | "1:1";
  recommended_width: number;
  recommended_height: number;
  prompt: string;
  negative_prompt: string;
  workflow_id: string;
  seed: number;
  text_hooks: string[];
  composition_guidance: string;
}

export interface YouTubeChapter {
  timestamp: string;
  seconds: number;
  title: string;
}

export interface YouTubePackagingData {
  project_id: string;
  titles: string[];
  selected_title?: string;
  description: string;
  tags: string[];
  tags_string: string;
  hashtags: string[];
  hashtags_string: string;
  chapters: YouTubeChapter[];
  thumbnail: YouTubeThumbnailResearch;
  generated_at?: string;
  source_profile?: string;
}

export interface YouTubePackagingGenerateRequest {
  profile_name?: string;
  focus_character?: string;
  style_tone?: "dramatic" | "action" | "mysterious" | "hype" | "emotional";
  custom_hook?: string;
}

export interface AutoPilotStageItem {
  id: string;
  name: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "SKIPPED" | "FAILED";
  progress: number;
  message: string;
  duration_sec: number;
}

export interface AutoPilotStatusResponse {
  project_id: string;
  status: "IDLE" | "RUNNING" | "COMPLETED" | "CANCELLED" | "FAILED";
  current_stage_id?: string | null;
  overall_progress: number;
  stages: AutoPilotStageItem[];
  logs: string[];
  result: Record<string, any>;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface AutoPilotStartRequest {
  target_profile?: string;
  skip_existing_stages?: boolean;
  voice_preset?: string;
  enable_thumbnails?: boolean;
}

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

export interface OllamaConfig {
  endpoint_url: string;
  is_remote: boolean;
  has_auth_token: boolean;
  vision_model: string;
  reasoning_model: string;
  narration_model: string;
  num_ctx: number;
  concurrency_mode: "AUTO" | "MANUAL";
  max_gpu_concurrency: number;
}

export interface OllamaModelCapability {
  name: string;
  supports_vision: boolean;
  supports_tools: boolean;
  supports_thinking: boolean;
  family: string;
  parameter_size: string;
  quantization_level: string;
  format: string;
  capabilities: string[];
}

export interface OllamaModelsResponse {
  models: OllamaModelCapability[];
  recommendations: {
    vision_model: string;
    reasoning_model: string;
    narration_model: string;
  };
  endpoint_url: string;
  is_remote: boolean;
  healthy: boolean;
}

export interface SystemResourcesResponse {
  ram: {
    total_gb: number;
    available_gb: number;
    used_percent: number;
    sufficient_for_inference: boolean;
  };
  gpu: {
    available: boolean;
    device_name: string;
    total_mb: number;
    free_mb: number;
    used_mb: number;
    used_percent: number;
    headroom_mb: number;
  };
  ollama: {
    online: boolean;
    loaded_models_count: number;
    total_ollama_vram_mb: number;
    models: Array<{
      name: string;
      model: string;
      size_mb: number;
      vram_mb: number;
      context_length: number;
      runner: string;
    }>;
  };
  scheduler: {
    concurrency_mode: "AUTO" | "MANUAL";
    configured_limit: number;
    effective_limit: number;
    active_gpu_jobs: string[];
    active_count: number;
    available_slots: number;
  };
}

export interface CameraMotionConfig {
  type: "SLOW_PUSH" | "CHARACTER_FOCUS" | "REACTION_CLOSEUP" | "IMPACT" | "PAN" | "STATIC" | string;
  start_zoom: number;
  end_zoom: number;
  easing: "EASE_IN_OUT" | "LINEAR" | "EASE_OUT" | string;
}

export interface StoryboardPanelRef {
  panel_id: string;
  reading_order: number;
  role: "ESTABLISHING" | "REACTION_CLOSEUP" | "ACTION" | "NARRATION_FOCUS" | "TRANSITION" | string;
  crop_bounds: { x: number; y: number; width: number; height: number };
  sub_duration_sec: number;
  camera_motion: CameraMotionConfig;
  crop_filename: string;
  image_url?: string;
}

export interface StoryboardSegment {
  segment_id: string;
  scene_id: string;
  sequence: number;
  text: string;
  emotion: string;
  intensity: number;
  audio_clip_path?: string | null;
  measured_duration_sec: number;
  supporting_panels: StoryboardPanelRef[];
  music_cue: { intent: string; ducking_gain_db: number };
  sfx_cue: { type: string; offset_sec: number };
  manual_override: boolean;
}

export interface StoryboardDocument {
  project_id: string;
  script_id: string;
  version: string;
  total_duration_sec: number;
  segments: StoryboardSegment[];
  created_at: string;
  updated_at: string;
}

export interface StoryboardSegmentUpdate {
  text?: string;
  emotion?: string;
  intensity?: number;
  measured_duration_sec?: number;
  supporting_panels?: StoryboardPanelRef[];
  music_cue?: { intent: string; ducking_gain_db: number };
  sfx_cue?: { type: string; offset_sec: number };
}

// ==========================================
// Video-First Story Editor Domain Models
// ==========================================

export type SceneCameraPreset =
  | "static"
  | "slow_zoom_in"
  | "slow_zoom_out"
  | "pan_left"
  | "pan_right"
  | "pan_up"
  | "pan_down"
  | "diagonal_pan"
  | "custom";

export type AnimationEasing =
  | "linear"
  | "ease_in"
  | "ease_out"
  | "ease_in_out"
  | "cubic_bezier";

export interface SceneCameraConfig {
  id?: string;
  preset: SceneCameraPreset;
  zoom_start: number; // 1.0 to 2.0
  zoom_end: number;   // 1.0 to 2.0
  pan_x_start: number; // -30% to +30%
  pan_x_end: number;
  pan_y_start: number;
  pan_y_end: number;
  start_offset_sec?: number;
  duration_sec?: number;
  easing?: AnimationEasing;
}

export type MotionPresetType =
  | "none"
  | "slow_zoom_in"
  | "slow_zoom_out"
  | "pan_left"
  | "pan_right"
  | "pan_up"
  | "pan_down"
  | "diagonal_pan"
  | "slide_in_left"
  | "slide_in_right"
  | "slide_in_top"
  | "slide_in_bottom"
  | "slide_out_left"
  | "slide_out_right"
  | "slide_out"
  | "move_left"
  | "move_right"
  | "move_up"
  | "move_down"
  | "move"
  | "rise"
  | "fall"
  | "scale_up"
  | "scale_down"
  | "rotate_cw"
  | "rotate_ccw"
  | "rotate"
  | "fade_in"
  | "fade_out"
  | "fade_in_out"
  | "cross_dissolve"
  | "wipe"
  | "blur"
  | "flash"
  | "shake_impact"
  | "opacity_reveal"
  | "custom";

export type AnimatableProperty =
  | "x"
  | "y"
  | "scale"
  | "rotation"
  | "opacity"
  | "blur";

export interface PropertyKeyframe {
  id: string;
  time_offset_sec: number; // Layer-relative time offset in seconds (0.0 to layer.duration_sec)
  value: number;           // Target property value (e.g. x: -20, opacity: 1.0, scale: 1.15)
  easing?: AnimationEasing;
  control_points?: [number, number, number, number]; // [x1, y1, x2, y2] for cubic_bezier
}

export interface PropertyTrack {
  property: AnimatableProperty;
  keyframes: PropertyKeyframe[];
  enabled?: boolean;
}

export interface LayerAnimationConfig {
  id: string;
  enabled: boolean;
  preset?: MotionPresetType;
  direction?: "left" | "right" | "up" | "down";
  duration_sec?: number;
  easing: AnimationEasing;
  speed?: number; // 0.5 to 2.0
  intensity?: number; // 0.1 to 2.0
  target_layer_id?: string;
  tracks?: Record<string, PropertyTrack>;
  start_pos?: { x: number; y: number; scale: number; rotation: number; opacity: number };
  end_pos?: { x: number; y: number; scale: number; rotation: number; opacity: number };
}

export interface VisualLayerCrop {
  x: number;
  y: number;
  width: number;
  height: number;
  crop_type?: "rect" | "polygon" | "pen";
  polygon_points?: Array<{ x: number; y: number }>;
  clip_path?: string;
}

export interface VisualLayerTransform {
  x: number; // percentage offset relative to 16:9 canvas center (-50 to +50)
  y: number; // percentage offset relative to 16:9 canvas center (-50 to +50)
  scale: number; // 1.0 = native fit, > 1.0 = zoom
  rotation: number; // in degrees
  opacity: number; // 0.0 to 1.0
  z_index: number; // stacking order
}

export interface VisualLayer {
  id: string;
  source_page_id: string;
  source_panel_id?: string;
  image_url: string;
  page_sequence: number;
  crop: VisualLayerCrop;
  transform: VisualLayerTransform;
  motion_preset?: MotionPresetType;
  motion_direction?: "left" | "right" | "up" | "down";
  motion_duration_sec?: number;
  motion_intensity?: number;
  motion_easing?: AnimationEasing;
  animation?: LayerAnimationConfig;
  animation_config?: LayerAnimationConfig;
  name?: string;
  locked?: boolean;
  visible?: boolean;
  crop_type?: "rect" | "polygon" | "pen";
  clip_path?: string;
  polygon_points?: Array<{ x: number; y: number }>;
  crop_filename?: string;
  // Chapter 3: Independent layer timing within scene
  start_offset_sec?: number; // Relative start offset in scene (default 0)
  duration_sec?: number;     // Active visible duration (default scene.duration_sec)
}

export type SceneTransitionType =
  | "none"
  | "cut"
  | "fade"
  | "fade_to_black"
  | "fade_from_black"
  | "cross_dissolve"
  | "wipe_left"
  | "wipe_right"
  | "impact_flash"
  | "dissolve";

export type SmartBackgroundPreset = "none" | "solid" | "duplicate_blur" | "gradient" | "mirror" | "edge_stretch" | "custom_image";

/** Versioned, non-destructive settings shared by preview and render compilation. */
export interface SmartBackgroundSettings {
  version: 1;
  enabled: boolean;
  preset: SmartBackgroundPreset;
  source_mode: "follow_active_visual" | "pinned_layer" | "custom_image";
  source_layer_id?: string;
  custom_image_url?: string;
  color: string;
  color_secondary: string;
  blur_sigma: number;
  zoom: number;
  focal_x: number;
  focal_y: number;
  brightness: number;
  saturation: number;
  tint: string;
  tint_opacity: number;
  opacity: number;
  vignette: number;
  edge_shadow: number;
  glow: number;
  motion: "none" | "slow_zoom" | "pan_left" | "pan_right";
  motion_amount: number;
  foreground_fit: "contain" | "cover";
  foreground_x: number;
  foreground_y: number;
  auto_only_when_needed: boolean;
}

export interface VideoScene {
  id: string;
  sequence: number;
  title: string;
  duration_sec: number;
  start_time_sec: number;
  layers: VisualLayer[];
  narration_id?: string;
  transition_in?: SceneTransitionType;
  transition_duration_sec?: number;
  camera?: SceneCameraConfig;
  camera_motion?: SceneCameraConfig;
  /** Missing means inherit the project's default; enabled:false explicitly turns it off. */
  background?: SmartBackgroundSettings;
}

export type NarrationEmotion =
  | "Neutral"
  | "Happy"
  | "Sad"
  | "Angry"
  | "Fearful"
  | "Suspenseful"
  | "Excited"
  | "Whispering"
  | "Serious"
  | "Mysterious"
  | "Determined";

export interface NarrationClip {
  id: string;
  scene_id?: string;
  panel_id?: string;
  speaker: string;
  text: string;
  emotion: NarrationEmotion | string;
  speed: number;
  status: "UNQUEUED" | "QUEUED" | "PROCESSING" | "READY" | "NEEDS_REVIEW" | "FAILED" | "OUTDATED";
  start_time_sec: number;
  duration_sec: number;
  audio_url?: string;
  linked_to_scene?: boolean; // Chapter 3 & 5: linked narration shifts when scene is moved/trimmed
  // Chapter 5B Narration Studio Integration fields:
  narration_segment_id?: string;
  speaker_id?: string;
  voice_profile_id?: string;
  speaker_type?: "NARRATOR" | "CHARACTER";
  text_revision?: number;
  content_hash?: string;
  delivery_intensity?: number;
  scene_offset_sec?: number; // relative offset within scene when linked
  review_status?: "DRAFT" | "NEEDS_REVIEW" | "APPROVED";
  previous_audio_asset_uri?: string | null;
  generated_audio_revision?: number | null;
  source_panel_ids?: string[];
  performance_intent?: string;
  pause_preset?: string;
}

export interface BgmTrack {
  id: string;
  title: string;
  name?: string;
  volume: number;
  start_time_sec: number;
  duration_sec: number;
  loop: boolean;
  asset_id?: string;
  file_url?: string | null;
  fade_in_sec?: number;
  fade_out_sec?: number;
  category?: string;
  bpm?: number;
  key?: string;
  ducking_enabled?: boolean;
  ducking_amount_db?: number;
  measured_peaks?: number[];
  availability?: string;
}

export interface SfxCue {
  id: string;
  name: string;
  category: "ambience" | "movement" | "magic" | "impact" | "transition" | string;
  start_time_sec: number;
  duration_sec: number;
  volume: number;
  asset_id?: string;
  file_url?: string | null;
  fade_in_sec?: number;
  fade_out_sec?: number;
  loop?: boolean;
  measured_peaks?: number[];
  availability?: string;
}

export type EditorSelectedObject =
  | { type: "scene"; id: string }
  | { type: "layer"; id: string; sceneId: string }
  | { type: "narration"; id: string }
  | { type: "bgm"; id: string }
  | { type: "sfx"; id: string }
  | { type: "page"; id: string }
  | { type: "panel"; id: string; pageId: string }
  | null;

export interface StoryEditorState {
  schema_version?: number; // Chapter 3 schema version (v2)
  project_id: string;
  aspect_ratio: "16:9" | "9:16" | "1:1" | "4:5" | "custom";
  canvas_width?: number;
  canvas_height?: number;
  background_default?: SmartBackgroundSettings;
  /** Preview comparison only; the export compiler deliberately ignores this flag. */
  background_preview_disabled?: boolean;
  mode: "simple" | "advanced";
  scenes: VideoScene[];
  narration_clips: NarrationClip[];
  narration_chapter?: any; // Chapter 5B: Full NarrationChapter domain model persisted with project
  bgm_tracks: BgmTrack[];
  sfx_cues?: SfxCue[];
  track_states?: Record<string, { visible: boolean; locked: boolean; collapsed?: boolean }>;
  selected_object: EditorSelectedObject;
  playhead_sec: number;
  is_playing: boolean;
  zoom_level: number;
  snapping?: boolean;
  ripple_edit?: boolean; // Chapter 3 explicit ripple toggle
  show_motion_paths?: boolean; // Chapter 4 canvas motion path toggle
  clipboard_animation?: LayerAnimationConfig; // Chapter 4 copy/paste animation
}

/** Server-authoritative project history, using the portable library's state vocabulary. */
export interface ProjectHistoryState {
  scope: string; revision: number; undoCount: number; redoCount: number;
  undoLabel: string | null; redoLabel: string | null; canUndo: boolean; canRedo: boolean;
  busy: boolean; recoveryRequired: boolean; conflicted: boolean; fingerprint: string;
  error: { code: string; message: string } | null;
}
export interface ProjectHistoryReply {
  state: StoryEditorState | null; history: ProjectHistoryState;
  replayed?: boolean; operation_revision?: number;
}

// ---------------------------------------------------------------------------
// Chapter 9: Story-Aware AI Music & Sound Design Domain Types
// ---------------------------------------------------------------------------

export interface MusicTakeRecord {
  take_id: string;
  cue_id: string;
  project_id: string;
  take_index: number;
  audio_file_path: string;
  audio_file_uri: string;
  duration_sec: number;
  sample_rate: number;
  channels: number;
  format: string;
  file_size_bytes: number;
  checksum_sha256: string;
  prompt: string;
  seed: number;
  bpm: number;
  key_scale: string;
  time_signature: string;
  model_id: string;
  inference_steps: number;
  guidance_scale: number;
  measured_peak_dbfs: number;
  measured_rms_dbfs: number;
  waveform_peaks: number[];
  approval_status: "DRAFT" | "APPROVED" | "REJECTED";
  created_at: number;
  generation_time_sec: number;
}

export interface MusicCuePlan {
  cue_id: string;
  title: string;
  scene_ids: string[];
  start_time_sec: number;
  end_time_sec: number;
  duration_sec: number;
  narrative_function:
    | "opening_mystery"
    | "character_discovery"
    | "rising_threat"
    | "confrontation"
    | "emotional_resolution"
    | "ambient_underscore"
    | "transitional_stinger";
  emotional_direction: string;
  intensity: number;
  genre_style: string;
  instrumentation: string[];
  tempo_bpm: number;
  tonal_center: string;
  time_signature: string;
  instrumental: boolean;
  musical_continuity: string;
  editable_prompt: string;
  selected_take_id?: string | null;
  takes: MusicTakeRecord[];
}

export interface MusicDirectionPlan {
  plan_id: string;
  project_id: string;
  storyboard_id?: string | null;
  overall_musical_theme: string;
  harmonic_key: string;
  recommended_headroom_notes: string;
  cues: MusicCuePlan[];
  total_score_duration_sec: number;
  created_at: number;
  updated_at: number;
}

export interface MusicGenerationRequest {
  cue_id?: string;
  prompt: string;
  audio_duration?: number;
  bpm?: number;
  key_scale?: string;
  time_signature?: string;
  seed?: number;
  use_random_seed?: boolean;
  inference_steps?: number;
  guidance_scale?: number;
  model?: string;
  thinking?: boolean;
}

export interface SFXCapabilityReport {
  local_ai_sfx_model_available: boolean;
  detected_models: string[];
  curated_sfx_library_available: boolean;
  available_categories: string[];
  notes: string;
}





