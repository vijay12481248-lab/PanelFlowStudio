import type { NarrationClip, StoryEditorState, VideoScene } from "@panelflow/shared-types";

/** Absolute, non-overlapping intervals. Missing/stale legacy starts follow the previous end. */
export function resolveSceneTiming(scenes: readonly VideoScene[]): VideoScene[] {
  let end = 0;
  return scenes.map((scene, index) => {
    const start = Number.isFinite(scene.start_time_sec) ? Math.max(end, scene.start_time_sec) : end;
    end = start + scene.duration_sec;
    return { ...scene, sequence: index + 1, start_time_sec: start };
  });
}

export function packSceneTiming(scenes: readonly VideoScene[]): VideoScene[] {
  let end = 0;
  return scenes.map((scene, index) => {
    const result = { ...scene, sequence: index + 1, start_time_sec: end };
    end += scene.duration_sec;
    return result;
  });
}

export function sceneTimelineDuration(scenes: readonly VideoScene[]): number {
  return resolveSceneTiming(scenes).reduce((end, scene) => Math.max(end, scene.start_time_sec + scene.duration_sec), 0);
}

export function sceneAtTime(scenes: readonly VideoScene[], time: number): VideoScene | null {
  return resolveSceneTiming(scenes).find(scene => time >= scene.start_time_sec && time < scene.start_time_sec + scene.duration_sec) ?? null;
}

export function alignLinkedNarration(scenes: readonly VideoScene[], clips: readonly NarrationClip[], previousScenes: readonly VideoScene[] = scenes): NarrationClip[] {
  const before = resolveSceneTiming(previousScenes);
  const after = resolveSceneTiming(scenes);
  return clips.map(clip => {
    if (!clip.scene_id || clip.linked_to_scene === false) return clip;
    const parent = after.find(scene => scene.id === clip.scene_id);
    if (!parent) return clip;
    const previous = before.find(scene => scene.id === clip.scene_id);
    const offset = clip.scene_offset_sec ?? Math.max(0, clip.start_time_sec - (previous?.start_time_sec ?? parent.start_time_sec));
    return { ...clip, scene_offset_sec: offset, start_time_sec: Math.round((parent.start_time_sec + offset) * 100) / 100 };
  });
}

/** Insert without moving anchored scenes: use the requested free gap, otherwise append. */
export function insertSceneTiming(scenes: readonly VideoScene[], scene: VideoScene, index: number, ripple = true): VideoScene[] {
  const timed = resolveSceneTiming(scenes);
  const at = Math.max(0, Math.min(index, timed.length));
  if (ripple) {
    timed.splice(at, 0, scene);
    return packSceneTiming(timed);
  }
  const start = at > 0 ? timed[at - 1].start_time_sec + timed[at - 1].duration_sec : 0;
  const fits = !timed[at] || start + scene.duration_sec <= timed[at].start_time_sec;
  const placed = { ...scene, start_time_sec: fits ? start : sceneTimelineDuration(timed) };
  timed.push(placed);
  return resolveSceneTiming(timed.sort((a, b) => a.start_time_sec - b.start_time_sec));
}

/** Apply the same policy to inspector duration edits (including callers that used to repack). */
export function reconcileSceneDurationEdit(previous: StoryEditorState, next: StoryEditorState): StoryEditorState {
  if (next.scenes === previous.scenes || next.scenes.length !== previous.scenes.length ||
      next.scenes.some((scene, i) => scene.id !== previous.scenes[i].id) ||
      !next.scenes.some((scene, i) => scene.duration_sec !== previous.scenes[i].duration_sec)) return next;
  const before = resolveSceneTiming(previous.scenes);
  const anchored = next.scenes.map((scene, i) => ({ ...scene, start_time_sec: before[i].start_time_sec,
    duration_sec: next.ripple_edit === false && before[i + 1]
      ? Math.min(scene.duration_sec, before[i + 1].start_time_sec - before[i].start_time_sec) : scene.duration_sec,
  }));
  const scenes = next.ripple_edit === false ? anchored : packSceneTiming(anchored);
  const clips = next.narration_clips.map(clip => {
    const original = previous.narration_clips.find(item => item.id === clip.id);
    return original && clip.scene_offset_sec == null ? { ...clip, start_time_sec: original.start_time_sec } : clip;
  });
  return { ...next, scenes, narration_clips: alignLinkedNarration(scenes, clips, before) };
}

/** OFF anchors every existing scene; growing is bounded by the next fixed start. */
export function trimSceneTiming(state: StoryEditorState, id: string, duration: number): StoryEditorState {
  const before = resolveSceneTiming(state.scenes);
  const index = before.findIndex(scene => scene.id === id);
  if (index < 0) return state;
  const maxDuration = state.ripple_edit === false && before[index + 1]
    ? before[index + 1].start_time_sec - before[index].start_time_sec : Infinity;
  const next = before.map((scene, i) => i === index ? { ...scene, duration_sec: Math.min(maxDuration, Math.max(0.8, duration)) } : scene);
  const scenes = state.ripple_edit === false ? next : packSceneTiming(next);
  return { ...state, scenes, narration_clips: alignLinkedNarration(scenes, state.narration_clips, before) };
}
