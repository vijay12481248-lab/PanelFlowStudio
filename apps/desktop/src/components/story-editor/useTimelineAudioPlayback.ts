import { useEffect, useRef } from "react";
import type { StoryEditorState } from "@panelflow/shared-types";
import { api } from "@panelflow/api-client";
import { computeBgmDuckingMultiplier, computeFadeMultiplier } from "./audioAdapter";

/**
 * Custom hook to synchronize real HTML5 audio playback for BGM, SFX, and Narration
 * with the Story Editor's playback controller and playhead position.
 */
export function useTimelineAudioPlayback(projectId: string, state: StoryEditorState) {
  // Map of active HTMLAudioElement instances by clip ID
  const audioInstancesRef = useRef<Map<string, HTMLAudioElement>>(new Map());

  // Cleanup helper for an audio element
  const cleanupAudio = (id: string) => {
    const audio = audioInstancesRef.current.get(id);
    if (audio) {
      try {
        audio.pause();
        audio.src = "";
      } catch {
        // Safe ignore
      }
      audioInstancesRef.current.delete(id);
    }
  };

  useEffect(() => {
    const instances = audioInstancesRef.current;
    const playhead = state.playhead_sec;
    const isPlaying = state.is_playing;

    const musicTrackState = state.track_states?.["Music"];
    const isMusicMuted = musicTrackState?.visible === false;

    const sfxTrackState = state.track_states?.["SFX"];
    const isSfxMuted = sfxTrackState?.visible === false;

    const narrationTrackState = state.track_states?.["Narration"];
    const isNarrationMuted = narrationTrackState?.visible === false;

    // Collect all valid clip IDs currently in state
    const currentClipIds = new Set<string>();

    // 1. Process BGM Tracks
    for (const bgm of state.bgm_tracks) {
      currentClipIds.add(bgm.id);
      if (!bgm.file_url) continue;

      let audio = instances.get(bgm.id);
      if (!audio) {
        audio = new Audio(bgm.file_url);
        audio.preload = "auto";
        instances.set(bgm.id, audio);
      }

      const isActive = playhead >= bgm.start_time_sec && playhead < bgm.start_time_sec + bgm.duration_sec;

      if (isPlaying && isActive && !isMusicMuted) {
        const rawElapsed = playhead - bgm.start_time_sec;
        const elapsedInClip = bgm.loop ? rawElapsed % bgm.duration_sec : rawElapsed;

        // Sync drift if greater than 0.25s
        if (Math.abs(audio.currentTime - elapsedInClip) > 0.25) {
          audio.currentTime = elapsedInClip;
        }

        // Apply volume, fades, and narration ducking
        const fadeMultiplier = computeFadeMultiplier(
          elapsedInClip,
          bgm.duration_sec,
          bgm.fade_in_sec,
          bgm.fade_out_sec
        );

        const duckingMultiplier = computeBgmDuckingMultiplier(
          playhead,
          state.narration_clips,
          bgm.ducking_enabled ?? true,
          bgm.ducking_amount_db ?? -12
        );

        const targetVolume = Math.max(
          0,
          Math.min(1, bgm.volume * fadeMultiplier * duckingMultiplier)
        );

        audio.volume = targetVolume;

        if (audio.paused) {
          audio.play().catch((err) => {
            // Browser autoplay policy or missing codec handled safely
            console.debug("Timeline BGM playback deferred:", err?.message);
          });
        }
      } else {
        if (!audio.paused) {
          audio.pause();
        }
      }
    }

    // 2. Process SFX Cues
    for (const sfx of state.sfx_cues || []) {
      currentClipIds.add(sfx.id);
      if (!sfx.file_url) continue;

      let audio = instances.get(sfx.id);
      if (!audio) {
        audio = new Audio(sfx.file_url);
        audio.preload = "auto";
        instances.set(sfx.id, audio);
      }

      const isActive = playhead >= sfx.start_time_sec && playhead < sfx.start_time_sec + sfx.duration_sec;

      if (isPlaying && isActive && !isSfxMuted) {
        const rawElapsed = playhead - sfx.start_time_sec;
        const elapsedInClip = sfx.loop ? rawElapsed % sfx.duration_sec : rawElapsed;

        if (Math.abs(audio.currentTime - elapsedInClip) > 0.25) {
          audio.currentTime = elapsedInClip;
        }

        const fadeMultiplier = computeFadeMultiplier(
          elapsedInClip,
          sfx.duration_sec,
          sfx.fade_in_sec,
          sfx.fade_out_sec
        );

        audio.volume = Math.max(0, Math.min(1, sfx.volume * fadeMultiplier));

        if (audio.paused) {
          audio.play().catch((err) => {
            console.debug("Timeline SFX playback deferred:", err?.message);
          });
        }
      } else {
        if (!audio.paused) {
          audio.pause();
        }
      }
    }

    // 3. Process Narration Clips
    // Determine the single active narration clip at the current playhead to prevent overlapping voices
    let activeNarrationId: string | null = null;
    let latestStartSec = -1;
    for (const narr of state.narration_clips) {
      if (!narr.audio_url) continue;
      const isActive = playhead >= narr.start_time_sec && playhead < narr.start_time_sec + narr.duration_sec;
      if (isActive && narr.start_time_sec > latestStartSec) {
        latestStartSec = narr.start_time_sec;
        activeNarrationId = narr.id;
      }
    }

    for (const narr of state.narration_clips) {
      currentClipIds.add(narr.id);
      if (!narr.audio_url) continue;

      let audio = instances.get(narr.id);
      if (!audio) {
        audio = new Audio(api.getAudioFileUrl(projectId, narr.audio_url));
        audio.preload = "auto";
        instances.set(narr.id, audio);
      }

      const shouldPlay = narr.id === activeNarrationId && isPlaying && !isNarrationMuted;

      if (shouldPlay) {
        const elapsed = playhead - narr.start_time_sec;
        if (Math.abs(audio.currentTime - elapsed) > 0.25) {
          audio.currentTime = elapsed;
        }
        audio.volume = 1.0;
        if (audio.paused) {
          audio.play().catch((err) => {
            console.debug("Timeline narration playback deferred:", err?.message);
          });
        }
      } else {
        if (!audio.paused) {
          audio.pause();
        }
      }
    }

    // Purge removed clips
    for (const [id] of instances) {
      if (!currentClipIds.has(id)) {
        cleanupAudio(id);
      }
    }
  }, [
    state.is_playing,
    state.playhead_sec,
    state.bgm_tracks,
    state.sfx_cues,
    state.narration_clips,
    state.track_states,
    projectId,
  ]);

  // Cleanup all on unmount
  useEffect(() => {
    return () => {
      audioInstancesRef.current.forEach((audio) => {
        try {
          audio.pause();
          audio.src = "";
        } catch {
          // ignore
        }
      });
      audioInstancesRef.current.clear();
    };
  }, []);
}
