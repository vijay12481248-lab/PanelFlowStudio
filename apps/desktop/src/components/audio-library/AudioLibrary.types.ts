/**
 * PanelFlow Studio — Chapter 6A: Audio Library Domain Types & Integration Contract
 *
 * Provides typed domain models for Music & Sound Effects library management,
 * metadata tagging, playback state, licensing, and future timeline track contracts.
 */

export type AudioType = "music" | "sfx";

export type AudioCategory =
  | "background_music"
  | "cinematic"
  | "suspense"
  | "emotional"
  | "action"
  | "fantasy"
  | "ambient"
  | "environmental"
  | "character"
  | "transitions"
  | "magic_fx"
  | "favorites";

export type AudioFormat = "mp3" | "wav" | "ogg" | "flac" | "aac";

export type AssetAvailability =
  | "AVAILABLE"      // Real local audio file is cached and ready to play
  | "MISSING_FILE"   // Asset entry exists in catalog but media file is missing on disk
  | "PREVIEW_ONLY"   // Low-bitrate streaming preview without local master
  | "PRO_ASSET";     // Premium catalog asset requiring download/unlock

export type AudioLicenseType =
  | "PanelFlow Built-in Royalty-Free"
  | "Creative Commons CC-BY 4.0"
  | "Public Domain (CC0)"
  | "Custom Commercial License";

export interface AudioLicenseMetadata {
  license_type: AudioLicenseType;
  author_or_source: string;
  attribution_required: boolean;
  commercial_use_allowed: boolean;
  source_url?: string;
  notes?: string;
}

export interface AudioAsset {
  id: string; // Stable unique identifier (e.g., "pf_bgm_d_minor_discovery")
  name: string;
  type: AudioType;
  category: AudioCategory;
  duration_sec: number;
  file_format: AudioFormat;
  file_url?: string | null;
  file_size_bytes?: number;
  sample_rate_hz?: number; // e.g. 44100, 48000
  channels?: "Stereo" | "Mono";
  tags: string[];
  availability: AssetAvailability;
  is_favorite: boolean;
  description: string;
  bpm?: number; // Musical beats per minute
  key?: string; // Musical harmonic key (e.g., "D Minor", "A Major")
  loopable?: boolean;
  license: AudioLicenseMetadata;
  recommended_timeline_track: "BGM" | "SFX";
  
  // Real measured audio waveform peaks (normalized 0.0 to 1.0)
  // undefined when audio file is not cached or measured
  measured_peaks?: number[];
  
  created_at: string;
}

export type AudioSortOption =
  | "name_asc"
  | "name_desc"
  | "duration_asc"
  | "duration_desc"
  | "recent"
  | "bpm_asc";

export interface AudioFilterState {
  search_query: string;
  selected_category: AudioCategory;
  selected_type: "all" | "music" | "sfx";
  sort_by: AudioSortOption;
  only_favorites: boolean;
  only_loopable: boolean;
}

export interface AudioPreviewState {
  playing_asset_id: string | null;
  is_playing: boolean;
  current_time_sec: number;
  duration_sec: number;
  volume: number; // 0.0 to 1.0
  is_muted: boolean;
  playback_error: string | null;
}

/**
 * Chapter 6B Future Timeline Integration Contract (Schema 6A-v1)
 *
 * Defines how an AudioAsset from this library is serialized and passed
 * to a future Story Editor timeline receiver (BGM Track or SFX Cue Track).
 */
export interface AudioAssetReference {
  asset_id: string;
  name: string;
  type: AudioType;
  category: AudioCategory;
  duration_sec: number;
  file_url: string;
  target_track: "BGM" | "SFX";
  volume: number;
  loop: boolean;
  fade_in_sec: number;
  fade_out_sec: number;
  bpm?: number;
  key?: string;
}

export interface AudioToTimelineContract {
  schema_version: "6A-v1";
  exported_at: string;
  reference: AudioAssetReference;
}

export interface AudioLibraryProps {
  initialAssets?: AudioAsset[];
  selectedAssetId?: string | null;
  initialType?: "all" | "music" | "sfx";
  projectId?: string;
  onSelectAsset?: (asset: AudioAsset) => void;
  onSendToTimeline?: (contract: AudioToTimelineContract) => void;
  onClose?: () => void;
}
