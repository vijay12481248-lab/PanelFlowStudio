import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Panel, ProjectHistoryState } from "@panelflow/shared-types";
import { useEngine } from "../../../app/providers";

export const panelKeys = { list: (projectId: string) => ["stages", "panels", "list", projectId] as const };

/** Every panel of the project. */
export function usePanels(projectId: string) {
  const { connected } = useEngine();
  return useQuery<Panel[]>({ queryKey: panelKeys.list(projectId), queryFn: () => api.listPanels(projectId), enabled: connected, retry: 1 });
}

/** The engine's undo and redo state for the project, seeded from the client's cache and replaced by each reply. */
export function useProjectHistory(projectId: string) {
  const [history, setHistory] = React.useState<ProjectHistoryState | null>(() => api.getCachedProjectHistory(projectId));
  return { history, setHistory, refresh: () => setHistory(api.getCachedProjectHistory(projectId)) };
}
