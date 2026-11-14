import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Panel, Project } from "@panelflow/shared-types";
import { useError } from "../../../context/ErrorContext";
import { refusal } from "../kit/engineReason";
import type { Box, Size } from "../kit/canvas/geometry";
import { panelKeys } from "./panelsData";
import { globalReorder, panelsOnPage, sortPanels } from "./panelsModel";
import type { Page } from "@panelflow/shared-types";

export interface PanelEditingOptions {
  project: Pick<Project, "id">;
  pages: Page[];
  /** Called after any change the engine accepted (refresh undo and redo, crops). */
  onChanged: () => void;
}

/**
 * Every change to a panel, one at a time across the whole screen. A change the engine refuses leaves the panels as they were
 * and is reported in words. Each operation resolves true when it was saved.
 */
export function usePanelEditing({ project, pages, onChanged }: PanelEditingOptions) {
  const queryClient = useQueryClient();
  const { reportError } = useError();
  const flight = React.useRef(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const key = panelKeys.list(project.id);

  const read = () => queryClient.getQueryData<Panel[]>(key) ?? [];
  const write = (update: (all: Panel[]) => Panel[]) => queryClient.setQueryData<Panel[]>(key, (all) => update(all ?? []));
  const replace = (next: Panel) => write((all) => all.map((p) => (p.id === next.id ? next : p)));
  const replacePage = (pageId: string, panels: Panel[]) => write((all) => [...all.filter((p) => p.page_id !== pageId), ...panels]);

  const run = async (change: () => Promise<void>, failure: string, title: string): Promise<boolean> => {
    if (flight.current) return false;
    flight.current = true;
    setBusy(true);
    setError(null);
    try {
      await change();
      onChanged();
      return true;
    } catch (err) {
      setError(refusal(failure, err, "Try again."));
      reportError({ title, message: failure, severity: "warning", source: "pipeline", projectId: project.id, rawDetails: err as Record<string, any> });
      return false;
    } finally { flight.current = false; setBusy(false); }
  };

  /** Save a panel's box. The position it had is what the screen shows if the engine refuses. */
  const saveBox = (panel: Panel, box: Box, extra?: { status: string; panelType: string }) =>
    run(async () => { replace(extra ? await api.updatePanel(project.id, panel.id, box.x, box.y, box.w, box.h, extra.status, extra.panelType) : await api.updatePanel(project.id, panel.id, box.x, box.y, box.w, box.h)); }, "Couldn't save the new position. It was put back.", "Panel Update Failed");

  return {
    busy,
    error,
    clearError: () => setError(null),
    move: (panel: Panel, box: Box) => saveBox(panel, box),

    /** Add a panel to a page. Resolves the new panel, or null. */
    add: async (pageId: string, box: Box): Promise<Panel | null> => {
      let created: Panel | null = null;
      const ok = await run(async () => { created = await api.addPanel(project.id, pageId, box.x, box.y, box.w, box.h); write((all) => [...all, created!]); }, "Couldn't add the panel.", "Add Panel Failed");
      return ok ? created : null;
    },

    split: (panel: Panel, type: "horizontal" | "vertical") =>
      run(async () => { replacePage(panel.page_id, await api.splitPanel(project.id, panel.id, type, 0.5)); }, "Couldn't split the panel.", "Split Failed"),

    merge: async (ids: string[]): Promise<Panel | null> => {
      let merged: Panel | null = null;
      const ok = await run(async () => { merged = await api.mergePanels(project.id, ids); await queryClient.invalidateQueries({ queryKey: key }); }, "Couldn't merge the panels.", "Merge Failed");
      return ok ? merged : null;
    },

    markFullPage: (panel: Panel, image: Size) => saveBox(panel, { x: 0, y: 0, w: image.w, h: image.h }, { status: "CONFIRMED", panelType: "FULL_PAGE" }),

    remove: (panel: Panel) => run(async () => { await api.deletePanel(project.id, panel.id); write((all) => all.filter((p) => p.id !== panel.id)); }, "Couldn't delete the panel. Nothing was removed.", "Delete Panel Failed"),

    /** Put a page's panels in a new order. The project's other pages keep their places. Shown at once, put back if refused. */
    reorder: (pageId: string, pageOrder: string[]) => {
      const previous = read();
      return run(async () => {
        const sorted = sortPanels(previous, pages);
        const ids = globalReorder(sorted, pageId, pageOrder);
        write((all) => all.map((p) => (p.page_id === pageId ? { ...p, page_sequence: pageOrder.indexOf(p.id) + 1 } : p)));
        try { queryClient.setQueryData(key, await api.reorderPanels(project.id, ids)); }
        catch (err) { queryClient.setQueryData(key, previous); throw err; }
      }, "Couldn't save the new order. The panels are back in their old order.", "Panel Reorder Failed");
    },
    pagePanels: (pageId: string) => panelsOnPage(read(), pageId),
  };
}
