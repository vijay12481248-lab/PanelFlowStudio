import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import { useEngine } from "../../app/providers";

export const sceneKeys = {
  unreviewed: ["scene-unreviewed"],
  runs: ["scene-runs"],
  run: (id: string) => ["scene-run", id],
} as const;

const POLL_MS = 8000;

/** How many pictures wait for the owner's review, and the newest one. One cheap request (limit 1) polled slowly; a failing request simply means "none". */
export function useUnreviewedCount(): { count: number; firstRunId: string | null } {
  const engine = useEngine();
  const query = useQuery({
    queryKey: sceneKeys.unreviewed,
    queryFn: () => api.listSceneRuns({ unreviewed: true, limit: 1 }),
    enabled: engine.connected,
    refetchInterval: POLL_MS,
    retry: false,
  });
  return { count: query.data?.total_unreviewed ?? 0, firstRunId: query.data?.items[0]?.id ?? null };
}
