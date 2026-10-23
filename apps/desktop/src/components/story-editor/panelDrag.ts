export interface PanelDragItem {
  panelId?: string;
  pageId?: string;
  pageSequence?: number;
  imageUrl?: string;
  cropFilename?: string;
  name?: string;
  crop?: { x: number; y: number; width: number; height: number };
}

/** Keep the first item at the top level for existing single-panel drop consumers. */
export function readPanelDrag(raw: string): PanelDragItem[] {
  try {
    const payload = JSON.parse(raw);
    const items = Array.isArray(payload?.panels) ? payload.panels : [payload];
    const seen = new Set<string>();
    return items.filter((item: unknown): item is PanelDragItem => {
      if (!item || typeof item !== "object") return false;
      const p = item as PanelDragItem;
      if (!(typeof p.panelId === "string" && p.panelId) && !(typeof p.pageId === "string" && p.pageId && typeof p.imageUrl === "string")) return false;
      const key = p.panelId || JSON.stringify([p.pageId, p.crop]);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  } catch { return []; }
}

/** A clip's left/right half selects its preceding/following scene boundary. */
export function panelInsertionIndex(scenes: readonly { start_time_sec: number; duration_sec: number }[], time: number): number {
  const index = scenes.findIndex(scene => time < scene.start_time_sec + scene.duration_sec / 2);
  return index < 0 ? scenes.length : index;
}
