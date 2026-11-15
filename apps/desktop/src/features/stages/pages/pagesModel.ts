import type { Page } from "@panelflow/shared-types";

export type ViewMode = "fit-width" | "fit-page" | "original";

/** A new array with the item at `from` moved to `to`. An index out of range returns an unchanged copy. */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
  const out = [...items];
  if (from < 0 || from >= out.length || to < 0 || to >= out.length) return out;
  const [moved] = out.splice(from, 1);
  out.splice(to, 0, moved);
  return out;
}

export function pageIdsAfterMove(pages: Page[], from: number, to: number): string[] {
  return moveItem(pages, from, to).map((p) => p.id);
}

export function canConfirm(pages: Page[]): { ok: boolean; reason: string | null } {
  return pages.some((p) => p.status === "READY") ? { ok: true, reason: null } : { ok: false, reason: "No pages are ready yet. Go back to Acquire." };
}

/** Very tall pages (webtoon strips) open fit-width so they can be scrolled; the rest open fit-page. */
export function defaultViewMode(page: Pick<Page, "width" | "height">): ViewMode {
  return page.height > page.width * 1.8 ? "fit-width" : "fit-page";
}

export const clampZoom = (zoom: number, delta: number) => Math.min(400, Math.max(25, zoom + delta));
