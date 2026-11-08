import type { RenderJob } from "@panelflow/shared-types";
import type { Tone } from "@panelflow/ui-v2";
import { EFFECTS, VIDEO_ENGINES } from "../motion/motionModel";

/** Exactly the statuses of a render in progress. `STALE` (a render the project has since changed under) is history, not work. */
export const RUNNING_RENDER: ReadonlySet<string> = new Set(["QUEUED", "PREPARING", "COMPOSING", "ENCODING", "MUXING", "VALIDATING"]);

export const isRunning = (job: Pick<RenderJob, "status">) => RUNNING_RENDER.has(job.status);

const time = (iso?: string) => (iso ? Date.parse(iso) : 0);

/** The newest render that is still running, or null. */
export function activeRender(renders: RenderJob[]): RenderJob | null {
  return [...renders].filter(isRunning).sort((a, b) => time(b.created_at) - time(a.created_at))[0] ?? null;
}

const STATUS: Record<string, { word: string; tone: Tone }> = {
  COMPLETE: { word: "Done", tone: "ok" },
  FAILED: { word: "Failed", tone: "bad" },
  CANCELLED: { word: "Cancelled", tone: "warn" },
  STALE: { word: "Out of date", tone: "warn" },
  QUEUED: { word: "Waiting", tone: "neutral" },
  PREPARING: { word: "Preparing", tone: "accent" },
  COMPOSING: { word: "Composing", tone: "accent" },
  ENCODING: { word: "Encoding", tone: "accent" },
  MUXING: { word: "Muxing", tone: "accent" },
  VALIDATING: { word: "Checking", tone: "accent" },
};

export function renderStatus(status: string): { word: string; tone: Tone } {
  if (STATUS[status]) return STATUS[status];
  const spaced = status.toLowerCase().replace(/_/g, " ");
  return { word: spaced.charAt(0).toUpperCase() + spaced.slice(1), tone: "neutral" };
}

export interface EngineProfile { id: string; name: string; description?: string; width?: number; height?: number; fps?: number }
export interface ProfileOption { id: string; label: string; hint: string }

/** The profiles the engine offers. With no list there are no options: an id is never invented. */
export function profileChoices(profiles: EngineProfile[] | null | undefined): { options: ProfileOption[]; defaultId: string | null; fromEngine: boolean } {
  if (!profiles || profiles.length === 0) return { options: [], defaultId: null, fromEngine: false };
  const options = profiles.map((p): ProfileOption => ({
    id: p.id,
    label: p.name || p.id,
    hint: p.width && p.height ? `${p.width}x${p.height}${p.fps ? ` · ${p.fps} fps` : ""}` : p.description ?? "",
  }));
  return { options, defaultId: options.find((o) => o.id === "standard_1080p")?.id ?? options[0].id, fromEngine: true };
}

export interface RenderSettings {
  profile: string;
  subtitles: boolean;
  bgmVolumeDb: number;
  dialogueGainDb: number;
  minPanelDuration: number;
  panelZoomMode: "fit" | "motion" | "cover";
  narrationSpeed: number;
  videoEngine: "fast_h3" | "ken_burns";
  motionFx: string;
  saveLocation: string;
}

/** The defaults of the old screen. The profile is chosen from the engine's list once it loads. */
export const DEFAULT_SETTINGS: RenderSettings = {
  profile: "", subtitles: false, bgmVolumeDb: -10, dialogueGainDb: 0, minPanelDuration: 4, panelZoomMode: "fit", narrationSpeed: 1, videoEngine: "fast_h3", motionFx: "none", saveLocation: "",
};

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));
const toStep = (n: number, step: number) => Math.round(n / step) * step;

/** Hold every value inside the range of the control that edits it. */
export function clampSettings(s: RenderSettings): RenderSettings {
  return {
    ...s,
    minPanelDuration: clamp(toStep(s.minPanelDuration, 0.5), 1.5, 8),
    bgmVolumeDb: clamp(Math.round(s.bgmVolumeDb), -30, 0),
    dialogueGainDb: clamp(toStep(s.dialogueGainDb, 0.5), -6, 6),
    narrationSpeed: clamp(s.narrationSpeed, 0.85, 1.2),
    panelZoomMode: s.panelZoomMode === "motion" || s.panelZoomMode === "cover" ? s.panelZoomMode : "fit",
    videoEngine: VIDEO_ENGINES.some((e) => e.value === s.videoEngine) ? s.videoEngine : "fast_h3",
    motionFx: EFFECTS.some((e) => e.value === s.motionFx) ? s.motionFx : "none",
  };
}

export interface StartRenderOptions {
  profileName?: string;
  customOutputPath?: string;
  subtitleEnabled: boolean;
  bgmVolumeDb: number;
  dialogueGainDb: number;
  isDraft: boolean;
  minPanelDuration: number;
  panelZoomMode: RenderSettings["panelZoomMode"];
  narrationSpeed: number;
  videoEngine: RenderSettings["videoEngine"];
  motionFx: string;
}

export function startOptions(settings: RenderSettings): StartRenderOptions {
  const s = clampSettings(settings);
  return {
    profileName: s.profile || undefined,
    customOutputPath: s.saveLocation.trim() || undefined,
    subtitleEnabled: s.subtitles,
    bgmVolumeDb: s.bgmVolumeDb,
    dialogueGainDb: s.dialogueGainDb,
    isDraft: s.profile === "draft_720p",
    minPanelDuration: s.minPanelDuration,
    panelZoomMode: s.panelZoomMode,
    narrationSpeed: s.narrationSpeed,
    videoEngine: s.videoEngine,
    motionFx: s.motionFx,
  };
}

export function formatBytes(n: number): string {
  if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MiB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${n} B`;
}

export const outputName = (path: string) => path.split(/[\\/]/).pop() ?? "";

export interface SummaryRow { label: string; value: string; tone: Tone; note?: string }

const num = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
const secs = (n: number, digits: number) => `${Number(n.toFixed(digits))}s`;

/**
 * The render checks in words. The overall verdict comes from the engine's gate status (or `is_valid`); a single check that
 * the engine reports as not confirmed on a render it still passed (the real `sync_valid: false` case) is explained, not shown as a failure.
 */
export function validationSummary(raw: unknown): { verdict: { word: string; tone: Tone }; rows: SummaryRow[]; warnings: string[] } {
  const r = (raw ?? null) as Record<string, any> | null;
  if (!r) return { verdict: { word: "No checks yet", tone: "neutral" }, rows: [], warnings: [] };
  const passed = r.gate_status ? r.gate_status === "PRODUCTION_READY" : Boolean(r.is_valid);
  const verdict = r.gate_status === "PRODUCTION_READY" ? { word: "Ready for production", tone: "ok" as Tone } : passed ? { word: "Passed", tone: "ok" as Tone } : { word: "Did not pass", tone: "bad" as Tone };

  const rows: SummaryRow[] = [];
  const flag = (label: string, value: unknown) => {
    if (typeof value !== "boolean") return;
    if (value) rows.push({ label, value: "Pass", tone: "ok" });
    else if (passed) rows.push({ label, value: "Not confirmed", tone: "warn", note: "The engine reports this check as not confirmed, but still passed the render as production ready." });
    else rows.push({ label, value: "Fail", tone: "bad" });
  };
  flag("Video", r.video_valid);
  flag("Audio", r.audio_valid);
  flag("Sync", r.sync_valid);
  const count = (label: string, n: unknown) => { if (num(n)) rows.push({ label, value: String(n), tone: n === 0 ? "ok" : "warn" }); };
  count("Black frames", r.black_frames_count);
  count("Timeline gaps", r.timeline_gaps_count);
  count("Clipping samples", r.clipping_samples_count);
  if (num(r.planned_duration_sec) && num(r.actual_duration_sec)) {
    rows.push({ label: "Duration", value: `Planned ${secs(r.planned_duration_sec, 2)} · actual ${secs(r.actual_duration_sec, 2)}${num(r.duration_diff_sec) ? ` (difference ${secs(r.duration_diff_sec, 3)})` : ""}`, tone: "neutral" });
  } else if (num(r.duration_sec)) rows.push({ label: "Duration", value: secs(r.duration_sec, 2), tone: "neutral" });
  if (num(r.file_size_bytes)) rows.push({ label: "File size", value: formatBytes(r.file_size_bytes), tone: "neutral" });
  return { verdict, rows, warnings: Array.isArray(r.warnings) ? r.warnings.map(String) : [] };
}
