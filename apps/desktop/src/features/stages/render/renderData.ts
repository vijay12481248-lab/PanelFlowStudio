import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { RenderJob } from "@panelflow/shared-types";
import { useEngine } from "../../../app/providers";
import { workbenchKeys } from "../../workbench/queries";
import { isRunning, type EngineProfile } from "./renderModel";

/** A project's renders (the cache Publish shares), refreshed every second while one is running. */
export function useRenderList(projectId: string) {
  const { connected } = useEngine();
  return useQuery<RenderJob[]>({
    queryKey: workbenchKeys.renders(projectId),
    queryFn: () => api.listRenders(projectId),
    enabled: connected,
    retry: 1,
    refetchInterval: (query) => ((query.state.data ?? []).some(isRunning) ? 1000 : false),
  });
}

export function useRenderProfiles() {
  const { connected } = useEngine();
  return useQuery<{ profiles: EngineProfile[] }>({ queryKey: ["stages", "render", "profiles"], queryFn: () => api.getRenderProfiles(), enabled: connected, retry: false });
}

export function useQuickDestinations(projectId: string) {
  const { connected } = useEngine();
  return useQuery({
    queryKey: ["stages", "render", "destinations", projectId],
    queryFn: () => api.getQuickDestinations(projectId).catch(() => ({ destinations: [], default_directory: "" })),
    enabled: connected,
    retry: false,
  });
}
