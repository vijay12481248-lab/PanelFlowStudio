import type { StoryEditorState, VisualLayer } from "@panelflow/shared-types";

export function createEmptyEditorState(projectId: string): StoryEditorState {
  return {
    schema_version: 2, project_id: projectId, aspect_ratio: "16:9", mode: "simple",
    ripple_edit: true, scenes: [], narration_clips: [], bgm_tracks: [], sfx_cues: [],
    track_states: {
      Narration: { visible: true, locked: false }, Visuals: { visible: true, locked: false },
      "Layer 2": { visible: true, locked: false }, "Motion / FX": { visible: true, locked: false },
      Music: { visible: true, locked: false }, SFX: { visible: true, locked: false },
    },
    selected_object: null, playhead_sec: 0, is_playing: false, zoom_level: 100,
  };
}

// Viewport zoom changes only the workspace preview, never persisted layer transforms.
export function fitCompositionFrame(ratio: StoryEditorState["aspect_ratio"], availableWidth: number, availableHeight: number, zoomPercent = 100, customWidth = 1920, customHeight = 1080) {
  const aspect = ratio === "custom" && Number.isFinite(customWidth) && Number.isFinite(customHeight) && customWidth > 0 && customHeight > 0
    ? customWidth / customHeight : ratio === "4:5" ? 4 / 5 : ratio === "9:16" ? 9 / 16 : ratio === "1:1" ? 1 : 16 / 9;
  const width = Math.max(1, Number.isFinite(availableWidth) ? availableWidth : 1);
  const height = Math.max(1, Number.isFinite(availableHeight) ? availableHeight : 1);
  const zoom = Number.isFinite(zoomPercent) ? Math.max(25, Math.min(200, zoomPercent)) / 100 : 1;
  const fittedWidth = Math.min(width, height * aspect);
  return { width: fittedWidth * zoom, height: fittedWidth / aspect * zoom };
}

export function resetLayerTransform(transform: VisualLayer["transform"]): VisualLayer["transform"] {
  return { ...transform, x: 0, y: 0, scale: 1, rotation: 0, opacity: 1 };
}
