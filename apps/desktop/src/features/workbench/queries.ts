import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { RenderJob } from "@panelflow/shared-types";
import { useEngine } from "../../app/providers";

const RUNNING = new Set(["QUEUED", "PREPARING", "COMPOSING", "ENCODING", "MUXING", "VALIDATING"]);

export const workbenchKeys = {
  renders: (projectId: string) => ["workbench", "renders", projectId] as const,
  validation: (projectId: string, renderId: string) => ["workbench", "validation", projectId, renderId] as const,
};

/** A project's renders, refreshed every 5 seconds only while one is still running. */
export function useRenders(projectId: string) {
  const { connected } = useEngine();
  return useQuery<RenderJob[]>({
    queryKey: workbenchKeys.renders(projectId),
    queryFn: () => api.listRenders(projectId),
    enabled: connected,
    retry: 1,
    refetchInterval: (query) => ((query.state.data ?? []).some((r) => RUNNING.has(r.status)) ? 5000 : false),
  });
}

/** Only for a finished render whose job did not already carry its validation report. */
export function useRenderValidation(projectId: string, renderId: string | undefined, enabled: boolean) {
  const { connected } = useEngine();
  return useQuery({
    queryKey: workbenchKeys.validation(projectId, renderId ?? ""),
    queryFn: () => api.getRenderValidation(projectId, renderId as string),
    enabled: connected && enabled && Boolean(renderId),
    retry: false,
  });
}
