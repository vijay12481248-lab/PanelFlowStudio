import type { MotionTimelineResponse, Panel } from "@panelflow/shared-types";

export interface Camera { center_x: number; center_y: number; zoom: number }

export interface ShotView {
  key: string;
  index: number;
  /** The scene this shot belongs to, when the plan is grouped in scenes. */
  title: string | null;
  motionType: string;
  easing: string;
  startSec: number;
  endSec: number;
  durationSec: number;
  startCamera: Camera;
  endCamera: Camera;
  caption: { speaker: string; text: string } | null;
  transition: string | null;
  /** The panel the shot names itself, when it does. */
  panelId: string | null;
}

const DEFAULT_CAMERA: Camera = { center_x: 0.5, center_y: 0.5, zoom: 1 };

/** Every shot in the plan, whichever shape the engine used: grouped in scenes, a flat list on the timeline, or on the response. */
export function extractShots(motion: MotionTimelineResponse | null | undefined): any[] {
  if (!motion) return [];
  const timeline: any = motion.timeline ?? {};
  const scenes: any[] = Array.isArray(timeline.scenes) ? timeline.scenes : [];
  if (scenes.length > 0) {
    return scenes.flatMap((scene) => (scene.shots ?? []).map((shot: any) => ({ ...shot, sceneTitle: scene.title || `Scene ${scene.sequence}`, sceneSeq: scene.sequence })));
  }
  for (const candidate of [timeline.shots, Array.isArray(timeline) ? timeline : undefined, (motion as any).shots]) {
    if (Array.isArray(candidate) && candidate.length > 0) return candidate;
  }
  return [];
}

/** One shot in the form the screen shows, with the old screen's fallbacks for missing fields. */
export function shotView(shot: any, index: number): ShotView {
  const start = shot.start_time ?? 0;
  const end = shot.end_time ?? 0;
  const cue = Array.isArray(shot.caption_cues) && shot.caption_cues[0] ? shot.caption_cues[0] : null;
  const t = shot.transition_in;
  const transition = !t ? null : typeof t === "string" ? t : `${t.transition_type}${t.duration_sec ? ` (${t.duration_sec}s)` : ""}`;
  return {
    key: shot.shot_id ? String(shot.shot_id) : String(index),
    index,
    title: shot.sceneTitle ?? null,
    motionType: shot.motion_type || shot.camera_motion_type || "CINEMATIC",
    easing: shot.easing || shot.easing_function || "SMOOTHSTEP",
    startSec: start,
    endSec: end,
    durationSec: shot.duration_sec ?? shot.duration ?? Math.max(0, end - start),
    startCamera: shot.camera_start || shot.start_rect || DEFAULT_CAMERA,
    endCamera: shot.camera_end || shot.end_rect || DEFAULT_CAMERA,
    caption: cue ? { speaker: cue.speaker || "Speaker", text: cue.text } : null,
    transition,
    panelId: shot.provenance?.panel_ids?.[0] ?? shot.source_panel_id ?? shot.panel_id ?? null,
  };
}

/** The panel a shot shows: named by the shot, then "panel_<n>" by sequence, then the panels in turn. */
export function matchPanel(shot: any, index: number, panels: Panel[]): Panel | undefined {
  const named: string[] = shot.provenance?.panel_ids || [];
  let found = panels.find((p) => named.includes(p.id) || shot.source_panel_id === p.id || shot.panel_id === p.id);
  if (!found && shot.source_panel_id) {
    const match = /panel_(\d+)/i.exec(String(shot.source_panel_id));
    if (match) found = panels.find((p) => p.sequence === parseInt(match[1], 10));
  }
  if (!found && panels.length > 0) found = panels[index % panels.length];
  return found;
}

export function formatClock(seconds: number): string {
  const total = Math.round(seconds);
  const secs = total % 60;
  return `${Math.floor(total / 60)}:${secs < 10 ? "0" : ""}${secs}`;
}

/** Append a quick tag to a prompt. A leading emoji or symbol on the tag is dropped. */
export function addTag(prompt: string, tag: string): string {
  const clean = tag.replace(/^[^\w\s]+/, "").trim();
  return prompt ? `${prompt}, ${clean}` : clean;
}

export const STYLE_PRESETS = [
  { value: "cinematic", label: "Cinematic (balanced)" },
  { value: "action_dynamic", label: "Action dynamic (fast pans)" },
  { value: "slow_burn", label: "Slow burn (deliberate)" },
  { value: "minimal", label: "Minimal (static holds)" },
  { value: "webtoon_scroll", label: "Webtoon scroll" },
] as const;

export const VIDEO_ENGINES = [
  { value: "ken_burns", label: "Ken Burns 2D" },
  { value: "fast_h3", label: "Fast H3 motion" },
] as const;

export const CAMERA_MOVES = [
  { value: "push_in", label: "Push in" }, { value: "pull_out", label: "Pull out" }, { value: "pan_left", label: "Pan left" },
  { value: "pan_right", label: "Pan right" }, { value: "tilt_up", label: "Tilt up" }, { value: "orbit", label: "Orbit" }, { value: "static", label: "Static hold" },
] as const;

export const INTENSITIES = [
  { value: "subtle", label: "Subtle (0.5x)" }, { value: "balanced", label: "Balanced (1.0x)" }, { value: "action", label: "Dynamic action (1.8x)" },
] as const;

export const EFFECTS = [
  { value: "none", label: "Clean (none)" }, { value: "letterbox", label: "Cinematic 2.39:1 scope" }, { value: "vignette", label: "Vignette and tone" },
  { value: "film_grain", label: "35mm film grain" }, { value: "action_shake", label: "Action camera shake" }, { value: "warm_cinema", label: "Warm cinema grade" },
] as const;

export const QUICK_TAGS = ["Wind in hair", "Breathing motion", "Glowing aura", "Rain droplets", "Action speed lines", "24fps cinema", "Bokeh depth"] as const;
