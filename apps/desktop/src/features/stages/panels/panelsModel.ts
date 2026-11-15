import type { Page, Panel, PipelineStage, ProjectHistoryState } from "@panelflow/shared-types";
import type { Tone } from "@panelflow/ui-v2";

const STATUS: Record<string, { word: string; tone: Tone }> = {
  DETECTED: { word: "Detected", tone: "accent" },
  CONFIRMED: { word: "Confirmed", tone: "ok" },
  APPROVED: { word: "Approved", tone: "ok" },
  NEEDS_REVIEW: { word: "Needs review", tone: "warn" },
  MANUAL: { word: "Added by hand", tone: "accent" },
  IGNORED: { word: "Excluded", tone: "neutral" },
};

export function panelStatus(status: string): { word: string; tone: Tone } {
  if (STATUS[status]) return STATUS[status];
  const spaced = status.toLowerCase().replace(/_/g, " ");
  return { word: spaced.charAt(0).toUpperCase() + spaced.slice(1), tone: "neutral" };
}

export const panelsOnPage = (panels: Panel[], pageId: string): Panel[] => panels.filter((p) => p.page_id === pageId).sort((a, b) => a.page_sequence - b.page_sequence);

/** Every panel in the project's order: by page, then by place on the page. A panel of an unknown page goes last. */
export function sortPanels(panels: Panel[], pages: Page[]): Panel[] {
  const order = new Map(pages.map((p) => [p.id, p.sequence]));
  return [...panels].sort((a, b) => (order.get(a.page_id) ?? Infinity) - (order.get(b.page_id) ?? Infinity) || a.page_sequence - b.page_sequence);
}

export function canConfirmPanels(panels: Panel[]): { ok: boolean; reason: string | null } {
  return panels.some((p) => p.status !== "IGNORED") ? { ok: true, reason: null } : { ok: false, reason: "Detect or add at least one panel first." };
}

const CONFIRMED_ONWARD: ReadonlySet<PipelineStage> = new Set<PipelineStage>([
  "PANELS_DETECTED", "OCR_COMPLETE", "OCR_APPROVED", "STORY_ANALYZED", "STORY_APPROVED", "SCRIPT_GENERATED", "SCRIPT_APPROVED", "VOICE_GENERATED", "AUDIO_APPROVED", "SHOT_PLAN_GENERATED", "MOTION_APPROVED", "RENDERED", "QA_APPROVED", "EXPORTED",
]);
export const isPanelsConfirmed = (stage: PipelineStage) => CONFIRMED_ONWARD.has(stage);

/** Panels per page, leaving out excluded panels, and how many pages have none. */
export function pageCounts(panels: Panel[], pages: Page[]): { perPage: Record<string, number>; empty: number } {
  const perPage: Record<string, number> = Object.fromEntries(pages.map((p) => [p.id, 0]));
  for (const p of panels) if (p.status !== "IGNORED" && p.page_id in perPage) perPage[p.page_id]++;
  return { perPage, empty: Object.values(perPage).filter((n) => n === 0).length };
}

export function historyAvailability(state: ProjectHistoryState | null, busy: boolean): { canUndo: boolean; canRedo: boolean; blocked: string | null } {
  if (!state) return { canUndo: false, canRedo: false, blocked: null };
  if (state.conflicted) return { canUndo: false, canRedo: false, blocked: "The project changed somewhere else. Reload the page before undoing." };
  if (state.recoveryRequired) return { canUndo: false, canRedo: false, blocked: "The undo history needs recovery. Reload the page." };
  return { canUndo: !busy && state.canUndo, canRedo: !busy && state.canRedo, blocked: null };
}

/**
 * The whole project's panel order after one page's panels are reordered: the page's panels take the places the page already
 * held, so every other page keeps its position (the old screen sent the page's panels after all the others).
 */
export function globalReorder(all: Panel[], pageId: string, newPageOrder: string[]): string[] {
  const queue = [...newPageOrder];
  return all.map((p) => (p.page_id === pageId ? (queue.shift() ?? p.id) : p.id));
}

/** The pages the strip draws: all of them when there are few, otherwise a window around the selected page. */
export function pageWindow(total: number, selected: number, size: number): { start: number; end: number } {
  if (total <= size) return { start: 0, end: total };
  const start = Math.min(Math.max(0, selected - Math.floor(size / 2)), total - size);
  return { start, end: start + size };
}
