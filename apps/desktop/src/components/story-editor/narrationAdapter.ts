import type {
  StoryEditorState,
  VideoScene,
  NarrationClip,
} from "@panelflow/shared-types";
import {
  type NarrationChapter,
  type NarrationSegment,
  type NarrationToTimelineContract,
  type CharacterProfile,
  type VoiceProfile,
  type NarrationEmotion,
  type ReviewStatus,
  type JobStatus,
  computeContentHash,
} from "../narration-studio/NarrationStudio.types.ts";
import {
  MOCK_CHARACTERS,
  MOCK_VOICE_PROFILES,
} from "../narration-studio/NarrationStudio.mock.ts";

/**
 * Estimate reading duration in seconds from script text and delivery speed
 */
export function estimateReadingDuration(text: string, speed: number = 1.0): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  // Standard speech rate: ~140 words per minute (2.33 words per second)
  const baseSeconds = (words / 2.33);
  const adjusted = baseSeconds / Math.max(0.5, speed);
  return Math.max(1.8, Math.round((adjusted + 0.5) * 10) / 10);
}

/**
 * Build initial NarrationChapter from project scenes and panels
 */
export function buildInitialNarrationChapter(
  projectId: string,
  projectTitle: string,
  scenes: VideoScene[],
  existingChapter?: NarrationChapter
): NarrationChapter {
  if (existingChapter && existingChapter.segments && existingChapter.segments.length > 0) {
    return existingChapter;
  }

  const defaultSpeaker = MOCK_CHARACTERS[0]; // The Narrator
  const segments: NarrationSegment[] = scenes.map((scene, idx) => {
    const primaryLayer = scene.layers[0];
    const text = idx % 2 === 0
      ? `Scene ${scene.sequence}: The silent expanse stretched outward as echoes resonated through the obsidian halls.`
      : `Scene ${scene.sequence}: With cautious steps, the explorers approached the pulsating crystal matrix.`;

    const emotion: NarrationEmotion = idx % 2 === 0 ? "Mysterious" : "Suspenseful";
    const speed = 1.0;
    const estimatedDuration = estimateReadingDuration(text, speed);

    return {
      id: `narr_${scene.id}`,
      sequence: idx + 1,
      scene_id: scene.id,
      scene_title: scene.title,
      linked_to_scene: true,
      scene_offset_sec: 0.0,
      speaker_id: defaultSpeaker.id,
      speaker_name: defaultSpeaker.name,
      speaker_type: "NARRATOR",
      voice_profile_id: defaultSpeaker.default_voice_profile_id,
      narration_text: text,
      text_revision: 1,
      content_hash: computeContentHash(text, emotion, speed, "short"),
      source_context: {
        page_id: primaryLayer?.source_page_id || `page_${idx + 1}`,
        page_number: primaryLayer?.page_sequence || idx + 1,
        panel_ids: primaryLayer?.source_panel_id ? [primaryLayer.source_panel_id] : [`panel_${idx + 1}`],
        panel_labels: [primaryLayer?.name || `Panel #${primaryLayer?.page_sequence || idx + 1}`],
        panel_preview_url: primaryLayer?.image_url,
        raw_ocr_dialogue: "",
        visual_description: `Scene ${scene.sequence} visual framing and composition.`,
        story_context: `Narrative progression for ${scene.title}.`,
      },
      delivery: {
        emotion,
        intensity: 0.6,
        speech_speed: speed,
        pause: {
          preset: "short",
          duration_ms: 300,
          placement: "after_first_sentence",
        },
        performance_notes: "Grounded, atmospheric delivery.",
        pronunciation_guide: [],
      },
      review_status: "APPROVED" as ReviewStatus,
      generation_status: "READY" as JobStatus,
      generation_progress: 100,
      audio_asset_uri: "/assets/demo/aria_narration_sample.mp3",
      previous_audio_asset_uri: null,
      generated_audio_revision: 1,
      estimated_duration_sec: estimatedDuration,
      measured_duration_sec: estimatedDuration,
      updated_at: new Date().toISOString(),
    };
  });

  return {
    project_id: projectId,
    project_title: projectTitle,
    chapter_id: `chap_${projectId}`,
    chapter_title: `${projectTitle} — Chapter 01`,
    chapter_number: 1,
    segments,
    characters: MOCK_CHARACTERS,
    voice_profiles: MOCK_VOICE_PROFILES,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

/**
 * Synchronize NarrationChapter domain model to Timeline NarrationClip array
 */
export function syncChapterToTimelineClips(
  chapter: NarrationChapter,
  scenes: VideoScene[],
  existingClips: NarrationClip[] = []
): NarrationClip[] {
  const existingMap = new Map<string, NarrationClip>();
  for (const clip of existingClips) {
    existingMap.set(clip.id, clip);
  }

  let unlinkedAccumulatedSec = 0;

  return chapter.segments.map((segment) => {
    const existing = existingMap.get(segment.id);

    // Smart Scene Binding: Match by scene_id, or reliable unambiguous source panel match
    let matchingScene: VideoScene | undefined;
    if (segment.scene_id) {
      matchingScene = scenes.find((s) => s.id === segment.scene_id);
    }

    if (!matchingScene && segment.source_context?.panel_ids?.length > 0) {
      // Find all scenes using this panel
      const targetPanelId = segment.source_context.panel_ids[0];
      const matchingScenes = scenes.filter((s) =>
        s.layers.some((l) => l.source_panel_id === targetPanelId)
      );
      // Only bind if exactly 1 scene matches (never guess when multiple scenes share a panel)
      if (matchingScenes.length === 1) {
        matchingScene = matchingScenes[0];
      }
    }

    const duration = segment.measured_duration_sec || segment.estimated_duration_sec || 3.5;
    const isLinked = segment.linked_to_scene !== false;

    let startTimeSec: number;
    if (isLinked && matchingScene) {
      startTimeSec = matchingScene.start_time_sec + (segment.scene_offset_sec || 0);
    } else if (existing && existing.start_time_sec !== undefined) {
      // Preserve existing unlinked absolute position
      startTimeSec = existing.start_time_sec;
    } else {
      startTimeSec = unlinkedAccumulatedSec;
    }

    unlinkedAccumulatedSec = Math.max(unlinkedAccumulatedSec, startTimeSec + duration + 0.5);

    return {
      id: segment.id,
      scene_id: matchingScene?.id || segment.scene_id,
      panel_id: segment.source_context?.panel_ids?.[0],
      speaker: segment.speaker_name,
      text: segment.narration_text,
      emotion: segment.delivery.emotion,
      speed: segment.delivery.speech_speed,
      status: segment.generation_status as NarrationClip["status"],
      start_time_sec: Math.round(startTimeSec * 100) / 100,
      duration_sec: Math.round(duration * 10) / 10,
      audio_url: segment.audio_asset_uri || undefined,
      linked_to_scene: isLinked,
      speaker_id: segment.speaker_id,
      voice_profile_id: segment.voice_profile_id,
      speaker_type: segment.speaker_type,
      text_revision: segment.text_revision,
      content_hash: segment.content_hash,
      delivery_intensity: segment.delivery.intensity,
      scene_offset_sec: segment.scene_offset_sec || 0,
      review_status: segment.review_status,
      previous_audio_asset_uri: segment.previous_audio_asset_uri,
      source_panel_ids: segment.source_context.panel_ids,
      performance_intent: segment.delivery.performance_notes,
      pause_preset: segment.delivery.pause?.preset,
    };
  });
}

/**
 * Smart Scene Binding: Relink unlinked narration clip to a target scene
 * Offers explicit choice: snap to start (offset 0) or preserve existing offset
 */
export function relinkClipToScene(
  clip: NarrationClip,
  targetScene: VideoScene,
  mode: "snap_to_start" | "preserve_offset"
): NarrationClip {
  let offsetSec = 0;
  let newStartSec = targetScene.start_time_sec;

  if (mode === "preserve_offset") {
    offsetSec = Math.max(0, Math.round((clip.start_time_sec - targetScene.start_time_sec) * 10) / 10);
    newStartSec = targetScene.start_time_sec + offsetSec;
  }

  return {
    ...clip,
    scene_id: targetScene.id,
    linked_to_scene: true,
    scene_offset_sec: offsetSec,
    start_time_sec: newStartSec,
  };
}

/**
 * Smart Scene Binding: Unlink narration clip from scene
 * Preserves the current exact absolute timeline position
 */
export function unlinkClipFromScene(clip: NarrationClip): NarrationClip {
  return {
    ...clip,
    linked_to_scene: false,
    // start_time_sec is preserved as-is
  };
}

/**
 * Ripple shift all linked narration clips when scenes are moved or trimmed
 * Unlinked narration clips remain at their exact absolute timeline coordinates
 */
export function rippleShiftLinkedNarration(
  scenes: VideoScene[],
  clips: NarrationClip[]
): NarrationClip[] {
  const sceneMap = new Map<string, VideoScene>();
  for (const sc of scenes) {
    sceneMap.set(sc.id, sc);
  }

  return clips.map((clip) => {
    if (clip.linked_to_scene === false || !clip.scene_id) {
      return clip; // unlinked: keep absolute time
    }

    const parentScene = sceneMap.get(clip.scene_id);
    if (!parentScene) {
      // Scene no longer exists (e.g. deleted). Safely convert to unlinked floating clip
      // so the creator's written lines, emotion, and audio takes are never lost or orphaned.
      return {
        ...clip,
        linked_to_scene: false,
      };
    }

    const targetStart = parentScene.start_time_sec + (clip.scene_offset_sec || 0);
    return {
      ...clip,
      start_time_sec: Math.round(targetStart * 100) / 100,
    };
  });
}

/**
 * Audio Regeneration Policy:
 * When script text is edited on a READY narration clip, mark generation_status = OUTDATED,
 * preserve previous audio take reference, increment text_revision, and update duration.
 */
export function updateClipScriptText(
  clip: NarrationClip,
  newText: string,
  chapter?: NarrationChapter
): { updatedClip: NarrationClip; updatedChapter?: NarrationChapter } {
  const isTextModified = newText.trim() !== clip.text.trim();
  const nextRevision = isTextModified ? (clip.text_revision || 1) + 1 : (clip.text_revision || 1);
  const newHash = computeContentHash(
    newText,
    clip.emotion || "Neutral",
    clip.speed || 1.0,
    clip.pause_preset || "short"
  );
  const nextDuration = estimateReadingDuration(newText, clip.speed || 1.0);

  // If audio was ready and text changed, invalidate to OUTDATED and preserve previous take
  const isPreviouslyReady = clip.status === "READY" && isTextModified;
  const nextStatus: NarrationClip["status"] = isPreviouslyReady ? "OUTDATED" : clip.status;
  const previousAsset = isPreviouslyReady ? (clip.audio_url || clip.previous_audio_asset_uri || null) : clip.previous_audio_asset_uri;
  const activeAsset = isPreviouslyReady ? undefined : clip.audio_url;

  const updatedClip: NarrationClip = {
    ...clip,
    text: newText,
    text_revision: nextRevision,
    content_hash: newHash,
    status: nextStatus,
    duration_sec: nextDuration,
    audio_url: activeAsset,
    previous_audio_asset_uri: previousAsset,
  };

  let updatedChapter: NarrationChapter | undefined = undefined;
  if (chapter) {
    updatedChapter = {
      ...chapter,
      updated_at: new Date().toISOString(),
      segments: chapter.segments.map((seg) => {
        if (seg.id !== clip.id) return seg;
        return {
          ...seg,
          narration_text: newText,
          text_revision: nextRevision,
          content_hash: newHash,
          generation_status: (isPreviouslyReady ? "OUTDATED" : seg.generation_status) as JobStatus,
          estimated_duration_sec: nextDuration,
          previous_audio_asset_uri: previousAsset,
          audio_asset_uri: activeAsset || null,
          updated_at: new Date().toISOString(),
        };
      }),
    };
  }

  return { updatedClip, updatedChapter };
}

/**
 * Ingest Schema 5A-v2 contract into Timeline NarrationClip array
 */
export function syncTimelineContractToState(
  contract: NarrationToTimelineContract,
  scenes: VideoScene[],
  existingClips: NarrationClip[] = []
): NarrationClip[] {
  const sceneMap = new Map<string, VideoScene>();
  for (const sc of scenes) {
    sceneMap.set(sc.id, sc);
  }

  return contract.clips.map((clip) => {
    const parentScene = clip.scene_id ? sceneMap.get(clip.scene_id) : undefined;
    const duration = clip.measured_duration_sec || clip.estimated_duration_sec;
    const isLinked = clip.linked_to_scene !== false;

    let startTime = 0;
    if (isLinked && parentScene) {
      startTime = parentScene.start_time_sec + (clip.scene_offset_sec || 0);
    } else {
      const existing = existingClips.find((c) => c.id === clip.narration_segment_id);
      startTime = existing?.start_time_sec ?? 0;
    }

    return {
      id: clip.narration_segment_id,
      scene_id: clip.scene_id,
      panel_id: clip.source_panel_ids[0],
      speaker: clip.speaker,
      text: clip.text,
      text_revision: clip.text_revision,
      content_hash: clip.content_hash,
      emotion: clip.emotion,
      speed: clip.speed,
      status: clip.generation_status as NarrationClip["status"],
      start_time_sec: Math.round(startTime * 100) / 100,
      duration_sec: Math.round(duration * 10) / 10,
      audio_url: clip.audio_asset_uri || undefined,
      linked_to_scene: isLinked,
      scene_offset_sec: clip.scene_offset_sec || 0,
      review_status: clip.review_status,
      previous_audio_asset_uri: clip.previous_audio_asset_uri,
      source_panel_ids: clip.source_panel_ids,
      performance_intent: clip.performance_intent,
    };
  });
}

/**
 * Stale Async Generation Guard:
 * Applies completed audio generation job result to a narration clip.
 * Strictly guards against stale results by verifying revision identity:
 * jobResult.target_revision MUST match clip.text_revision exactly.
 * If target_revision does not match, the stale result is rejected:
 * the clip remains/becomes OUTDATED, active audio is not overwritten,
 * and a clear diagnostic rejection reason is returned.
 */
export function applyGeneratedAudioResult(
  clip: NarrationClip,
  jobResult: {
    target_revision: number;
    audio_asset_uri: string;
    measured_duration_sec?: number;
    content_hash?: string;
  },
  chapter?: NarrationChapter
): {
  success: boolean;
  updatedClip: NarrationClip;
  updatedChapter?: NarrationChapter;
  rejectionReason?: string;
} {
  const currentRevision = clip.text_revision || 1;

  // Stale async result guard: Revision identity check
  if (jobResult.target_revision !== currentRevision) {
    const rejectionReason = `Stale synthesis rejected: Clip is currently at Rev #${currentRevision}, but async job returned Rev #${jobResult.target_revision}.`;
    return {
      success: false,
      updatedClip: {
        ...clip,
        status: "OUTDATED",
      },
      updatedChapter: chapter,
      rejectionReason,
    };
  }

  // Revision matches!
  const measuredDur = jobResult.measured_duration_sec ?? clip.duration_sec;
  const updatedClip: NarrationClip = {
    ...clip,
    status: "READY",
    audio_url: jobResult.audio_asset_uri,
    duration_sec: Math.round(measuredDur * 10) / 10,
    generated_audio_revision: jobResult.target_revision,
  };

  let updatedChapter = chapter;
  if (chapter) {
    updatedChapter = {
      ...chapter,
      updated_at: new Date().toISOString(),
      segments: chapter.segments.map((seg) => {
        if (seg.id !== clip.id) return seg;
        return {
          ...seg,
          generation_status: "READY" as JobStatus,
          audio_asset_uri: jobResult.audio_asset_uri,
          generated_audio_revision: jobResult.target_revision,
          measured_duration_sec: Math.round(measuredDur * 10) / 10,
          generation_error: null,
          updated_at: new Date().toISOString(),
        };
      }),
    };
  }

  return {
    success: true,
    updatedClip,
    updatedChapter,
  };
}
