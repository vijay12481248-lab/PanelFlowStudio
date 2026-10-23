/**
 * PanelFlow Studio — Chapter 5A: Narration Studio Domain Types
 *
 * Fully serializable, independent narration domain model.
 * Does not depend on or modify Chapter 3 timeline types.
 */

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
  | "Determined"
  | "Dramatic"
  | "Intense"
  | "Calm"
  | "Emotional";

export type ReviewStatus = "DRAFT" | "NEEDS_REVIEW" | "APPROVED";

export type JobStatus =
  | "UNQUEUED"
  | "QUEUED"
  | "PROCESSING"
  | "READY"
  | "NEEDS_REVIEW"
  | "FAILED"
  | "OUTDATED";

export type SpeakerType = "NARRATOR" | "CHARACTER";

export type PausePreset = "none" | "short" | "medium" | "dramatic" | "custom";

export interface PauseSuggestion {
  preset: PausePreset;
  duration_ms: number;
  placement: "before" | "after_first_sentence" | "after" | "custom";
  instruction?: string;
}

export interface PronunciationItem {
  id: string;
  word: string;
  phonetic: string;
  notes?: string;
}

export interface EmotionalDeliveryConfig {
  emotion: NarrationEmotion;
  intensity: number; // 0.0 to 1.0 (subtle to intense)
  speech_speed: number; // 0.75 to 1.5 (default 1.0)
  pause: PauseSuggestion;
  performance_notes: string;
  pronunciation_guide: PronunciationItem[];
}

export interface PageScriptRecord {
  page_id: string;
  page_sequence: number;
  full_script: string;
  lines: string[];
  tone: string;
  panels_count?: number;
  humor_and_emotional_notes?: string;
}

export interface MangaSourceContext {
  page_id: string;
  page_number: number;
  panel_ids: string[];
  panel_labels?: string[]; // e.g. ["Panel 1", "Panel 2"]
  panel_preview_url?: string;
  image_url?: string;
  svg_thumbnail?: string; // Rich inline SVG demonstration representation
  raw_ocr_dialogue: string;
  visual_description: string;
  story_context: string;
  page_context_summary?: string;
  character_name?: string;
  // 3-Tier Narration Properties
  page_narration_text?: string; // Tier 1: 5-10 line witty human recap script
  panel_narration_text?: string; // Tier 2: Micro panel observation & beat
  synthesis_notes?: string; // Tier 3: Comparison & harmonization explanation
  panel_duration_budget_sec?: number; // Target video display window for this panel
}

/**
 * Fast, deterministic content hash utility for script and delivery state.
 * Prevents stale asynchronous audio results from overwriting newer script edits.
 */
export function computeContentHash(
  text: string,
  emotion: string,
  speed: number,
  pausePreset?: string
): string {
  const raw = `${text.trim()}|${emotion}|${speed.toFixed(2)}|${pausePreset || "none"}`;
  let hash = 0x811c9dc5;
  for (let i = 0; i < raw.length; i++) {
    hash ^= raw.charCodeAt(i);
    hash = (hash * 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

export interface NarrationSegment {
  id: string;
  sequence: number;
  scene_id?: string;
  scene_title?: string;

  // Decision 1: Smart Scene Binding & Timing
  linked_to_scene: boolean; // default true: smart scene alignment in future timeline
  scene_offset_sec: number; // user-editable relative timing offset within scene

  // Speaker and voice casting
  speaker_id: string;
  speaker_name: string;
  speaker_type: SpeakerType;
  voice_profile_id: string;
  has_custom_voice_override?: boolean; // protects against silent propagation overwrite
  has_custom_delivery_override?: boolean;

  // Script text and version tracking
  narration_text: string; // Final harmonized synced script
  page_narration_text?: string; // Tier 1: 5-10 lines witty page recap
  panel_narration_text?: string; // Tier 2: Micro panel beat
  synthesis_notes?: string; // Tier 3: Comparison notes
  text_revision: number; // monotonically increasing integer per text edit
  content_hash: string; // hash of text + emotion + speed

  // Story source and delivery
  source_context: MangaSourceContext;
  delivery: EmotionalDeliveryConfig;
  continuity_notes?: string;

  // Decision 2: Decoupled Approval vs Generation State
  review_status: ReviewStatus;
  generation_status: JobStatus;
  generation_progress?: number; // 0 to 100
  generation_error?: string | null;

  // Audio Take Lifecycle & Outdated Take Preservation
  audio_asset_uri?: string | null; // active audio take
  previous_audio_asset_uri?: string | null; // preserved previous take when text changes
  generated_audio_revision?: number | null; // revision matching audio_asset_uri

  estimated_duration_sec: number;
  measured_duration_sec?: number | null;
  updated_at: string;
}

export interface CharacterProfile {
  id: string;
  name: string;
  role: "PROTAGONIST" | "ANTAGONIST" | "SUPPORTING" | "MINOR" | "NARRATOR";
  color_accent: string;
  avatar_initials: string;
  avatar_url?: string;
  default_voice_profile_id: string;
  default_emotion: NarrationEmotion;
  default_speed: number;
  notes?: string;
  segment_count: number;
}

export interface VoiceProfile {
  id: string;
  name: string;
  gender: "Female" | "Male" | "Neutral";
  age_group: "Young" | "Adult" | "Elderly";
  timbre: string; // e.g. "Deep & Resonant", "Breathless & Airy"
  recommended_emotions: NarrationEmotion[];
  sample_quote: string;
  sample_audio_available: boolean;
  sample_audio_uri?: string;
  model_family: string; // e.g. "F5-TTS", "Chatterbox", "Dia"
  is_mock: boolean;
}

export interface NarrationChapter {
  project_id: string;
  project_title: string;
  chapter_id: string;
  chapter_title: string;
  chapter_number: number;
  segments: NarrationSegment[];
  characters: CharacterProfile[];
  voice_profiles: VoiceProfile[];
  page_scripts?: Record<string, PageScriptRecord>;
  created_at: string;
  updated_at: string;
}

export interface NarrationFilterState {
  search_query: string;
  selected_character_id: string | null;
  selected_status: ReviewStatus | "ALL";
  selected_speaker_type: SpeakerType | "ALL";
}

export interface NarrationJobItem {
  job_id: string;
  segment_id: string;
  sequence: number;
  speaker_name: string;
  text_preview: string;
  status: JobStatus;
  progress: number;
  target_revision: number;
  content_hash: string;
  error_message?: string | null;
  enqueued_at: string;
  updated_at: string;
}

/**
 * Storytelling Continuity Analysis result
 */
export interface ContinuityCheckResult {
  has_issue: boolean;
  severity: "info" | "warning" | "alert";
  message: string;
  suggested_action?: string;
  previous_speaker?: string;
  previous_emotion?: NarrationEmotion;
  next_speaker?: string;
}

/**
 * Chapter 3 Timeline Integration Contract (Schema 5A-v2)
 *
 * Defines how this narration module serializes data so that a future
 * timeline adapter can transform approved NarrationSegments into
 * Timeline NarrationClips without requiring runtime coupling now.
 */
export interface NarrationToTimelineContract {
  schema_version: "5A-v2";
  project_id: string;
  chapter_id: string;
  exported_at: string;
  clips: Array<{
    narration_segment_id: string;
    sequence: number;
    scene_id?: string;
    linked_to_scene: boolean;
    scene_offset_sec: number;
    speaker: string;
    text: string;
    text_revision: number;
    content_hash: string;
    emotion: NarrationEmotion;
    speed: number;
    estimated_duration_sec: number;
    measured_duration_sec?: number | null;
    audio_asset_uri?: string | null;
    previous_audio_asset_uri?: string | null;
    generated_audio_revision?: number | null;
    review_status: ReviewStatus;
    generation_status: JobStatus;
    source_panel_ids: string[];
    voice_profile_id: string;
    performance_intent: string;
  }>;
}

export interface NarrationStudioProps {
  initialChapter?: NarrationChapter;
  initialSegmentId?: string;
  projectId?: string;
  scenes?: any[];
  pages?: any[];
  panels?: any[];
  onChapterSave?: (chapter: NarrationChapter) => void;
  onSegmentApproved?: (segment: NarrationSegment) => void;
  onExportTimelineContract?: (contract: NarrationToTimelineContract) => void;
  onAddToTimeline?: (mode: "all" | "selected", segmentId?: string) => void;
  onClose?: () => void;
}
