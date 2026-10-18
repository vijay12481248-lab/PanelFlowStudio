/**
 * PanelFlow Studio — Chapter 6B: Audio Adapter & Timeline Integration Service
 *
 * Bridges the independent Audio Library (Chapter 6A) with the Story Editor's
 * synchronized multitrack timeline (Chapter 3, 4, 5B).
 *
 * Handles:
 * - Conversion of AudioToTimelineContract (Schema 6A-v1) to BgmTrack and SfxCue clips
 * - Timeline placement, trimming, movement, duplication, and deletion
 * - Real HTML5 audio synchronization with editor playhead and playback controller
 * - Narration ducking calculations and volume management
 */

import type {
  StoryEditorState,
  BgmTrack,
  SfxCue,
  NarrationClip,
} from "@panelflow/shared-types";
import type {
  AudioToTimelineContract,
  AudioAssetReference,
  AudioAsset,
} from "../audio-library/AudioLibrary.types.ts";

/**
 * Converts a Schema 6A-v1 contract reference into a BgmTrack clip
 */
export function createBgmTrackFromContract(
  ref: AudioAssetReference,
  targetTimeSec: number = 0
): BgmTrack {
  const clipId = `bgm_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
  return {
    id: clipId,
    title: ref.name,
    volume: typeof ref.volume === "number" ? ref.volume : 0.8,
    start_time_sec: Math.max(0, Math.round(targetTimeSec * 10) / 10),
    duration_sec: Math.max(1.0, Math.round(ref.duration_sec * 10) / 10),
    loop: ref.loop ?? true,
    asset_id: ref.asset_id,
    file_url: ref.file_url || null,
    fade_in_sec: ref.fade_in_sec ?? 1.0,
    fade_out_sec: ref.fade_out_sec ?? 1.5,
    category: ref.category,
    bpm: ref.bpm,
    key: ref.key,
    ducking_enabled: true,
    ducking_amount_db: -12,
  };
}

/**
 * Converts a Schema 6A-v1 contract reference into an SfxCue clip
 */
export function createSfxCueFromContract(
  ref: AudioAssetReference,
  targetTimeSec: number = 0
): SfxCue {
  const clipId = `sfx_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
  return {
    id: clipId,
    name: ref.name,
    category: (ref.category as any) || "movement",
    start_time_sec: Math.max(0, Math.round(targetTimeSec * 10) / 10),
    duration_sec: Math.max(0.5, Math.round(ref.duration_sec * 10) / 10),
    volume: typeof ref.volume === "number" ? ref.volume : 0.85,
    asset_id: ref.asset_id,
    file_url: ref.file_url || null,
    fade_in_sec: ref.fade_in_sec ?? 0.0,
    fade_out_sec: ref.fade_out_sec ?? 0.0,
    loop: ref.loop ?? false,
  };
}

/**
 * Places an audio contract onto the timeline in StoryEditorState
 */
export function applyAudioContractToState(
  state: StoryEditorState,
  contract: AudioToTimelineContract,
  customStartTimeSec?: number
): StoryEditorState {
  const ref = contract.reference;
  const startTime = customStartTimeSec !== undefined ? customStartTimeSec : state.playhead_sec;

  if (ref.target_track === "BGM") {
    const newBgm = createBgmTrackFromContract(ref, startTime);
    return {
      ...state,
      bgm_tracks: [...state.bgm_tracks, newBgm],
      selected_object: { type: "bgm", id: newBgm.id },
    };
  } else {
    const newSfx = createSfxCueFromContract(ref, startTime);
    const existingSfx = state.sfx_cues || [];
    return {
      ...state,
      sfx_cues: [...existingSfx, newSfx],
      selected_object: { type: "sfx", id: newSfx.id },
    };
  }
}

/**
 * Updates a BGM clip in StoryEditorState
 */
export function updateBgmClip(
  state: StoryEditorState,
  clipId: string,
  updates: Partial<BgmTrack>
): StoryEditorState {
  return {
    ...state,
    bgm_tracks: state.bgm_tracks.map((b) => (b.id === clipId ? { ...b, ...updates } : b)),
  };
}

/**
 * Updates an SFX clip in StoryEditorState
 */
export function updateSfxClip(
  state: StoryEditorState,
  clipId: string,
  updates: Partial<SfxCue>
): StoryEditorState {
  return {
    ...state,
    sfx_cues: (state.sfx_cues || []).map((s) => (s.id === clipId ? { ...s, ...updates } : s)),
  };
}

/**
 * Deletes an audio clip (BGM or SFX) from StoryEditorState
 */
export function deleteAudioClip(
  state: StoryEditorState,
  clipId: string,
  trackType: "bgm" | "sfx"
): StoryEditorState {
  if (trackType === "bgm") {
    return {
      ...state,
      bgm_tracks: state.bgm_tracks.filter((b) => b.id !== clipId),
      selected_object: state.selected_object?.id === clipId ? null : state.selected_object,
    };
  } else {
    return {
      ...state,
      sfx_cues: (state.sfx_cues || []).filter((s) => s.id !== clipId),
      selected_object: state.selected_object?.id === clipId ? null : state.selected_object,
    };
  }
}

/**
 * Duplicates an audio clip (BGM or SFX) with a slight offset
 */
export function duplicateAudioClip(
  state: StoryEditorState,
  clipId: string,
  trackType: "bgm" | "sfx"
): StoryEditorState {
  if (trackType === "bgm") {
    const original = state.bgm_tracks.find((b) => b.id === clipId);
    if (!original) return state;
    const duplicated: BgmTrack = {
      ...original,
      id: `bgm_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      title: `${original.title} (Copy)`,
      start_time_sec: original.start_time_sec + original.duration_sec,
    };
    return {
      ...state,
      bgm_tracks: [...state.bgm_tracks, duplicated],
      selected_object: { type: "bgm", id: duplicated.id },
    };
  } else {
    const original = (state.sfx_cues || []).find((s) => s.id === clipId);
    if (!original) return state;
    const duplicated: SfxCue = {
      ...original,
      id: `sfx_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      name: `${original.name} (Copy)`,
      start_time_sec: original.start_time_sec + original.duration_sec + 0.5,
    };
    return {
      ...state,
      sfx_cues: [...(state.sfx_cues || []), duplicated],
      selected_object: { type: "sfx", id: duplicated.id },
    };
  }
}

/**
 * Computes ducking attenuation factor for BGM based on active narration
 * Returns a multiplier between 0.0 and 1.0 (1.0 = no ducking)
 */
export function computeBgmDuckingMultiplier(
  playheadSec: number,
  narrationClips: NarrationClip[],
  duckingEnabled: boolean = true,
  duckingAmountDb: number = -12
): number {
  if (!duckingEnabled) return 1.0;

  // Check if any narration clip is active at current playhead position
  const isNarrationActive = narrationClips.some((n) => {
    return playheadSec >= n.start_time_sec && playheadSec <= n.start_time_sec + n.duration_sec;
  });

  if (!isNarrationActive) return 1.0;

  // Convert dB attenuation to linear gain multiplier: gain = 10^(dB / 20)
  return Math.max(0.05, Math.pow(10, duckingAmountDb / 20));
}

/**
 * Computes fade-in and fade-out volume multiplier for a clip
 */
export function computeFadeMultiplier(
  elapsedInClipSec: number,
  durationSec: number,
  fadeInSec: number = 0,
  fadeOutSec: number = 0
): number {
  let multiplier = 1.0;

  // Fade In
  if (fadeInSec > 0 && elapsedInClipSec < fadeInSec) {
    multiplier = Math.min(multiplier, elapsedInClipSec / fadeInSec);
  }

  // Fade Out
  const timeUntilEnd = durationSec - elapsedInClipSec;
  if (fadeOutSec > 0 && timeUntilEnd < fadeOutSec) {
    multiplier = Math.min(multiplier, Math.max(0, timeUntilEnd / fadeOutSec));
  }

  return Math.max(0, Math.min(1, multiplier));
}
