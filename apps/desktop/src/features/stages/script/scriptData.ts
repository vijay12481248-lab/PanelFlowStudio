import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { ScriptValidationReport, StoryboardDocument, VideoScript } from "@panelflow/shared-types";
import { useEngine } from "../../../app/providers";

export const scriptKeys = {
  script: (projectId: string) => ["stages", "script", projectId] as const,
  storyboard: (projectId: string) => ["stages", "script", "storyboard", projectId] as const,
};

/** The saved script. No script is a normal state (the engine answers 404), shown as "no script yet". */
export function useScript(projectId: string) {
  const { connected } = useEngine();
  return useQuery<VideoScript | null>({ queryKey: scriptKeys.script(projectId), queryFn: () => api.getScript(projectId).catch(() => null), enabled: connected, retry: false });
}

export function useStoryboard(projectId: string) {
  const { connected } = useEngine();
  return useQuery<StoryboardDocument | null>({ queryKey: scriptKeys.storyboard(projectId), queryFn: () => api.getStoryboard(projectId).catch(() => null), enabled: connected, retry: false });
}

export type ValidationState = "idle" | "running" | "failed";

/**
 * Faithfulness validation. The engine's validate call recomputes and saves quality metrics, so it runs once when a script is
 * first seen (and again only when asked: after an edit, a refused approval, or the Validate button), never on every render.
 */
export function useScriptValidation(projectId: string, scriptId: string | undefined) {
  const [report, setReport] = React.useState<ScriptValidationReport | null>(null);
  const [state, setState] = React.useState<ValidationState>("idle");
  const running = React.useRef(false);
  const seen = React.useRef<string | undefined>(undefined);

  const run = React.useCallback(async () => {
    if (!scriptId || running.current) return;
    running.current = true;
    setState("running");
    try {
      setReport(await api.validateScript(projectId, scriptId));
      setState("idle");
    } catch {
      setState("failed"); // the report stays as it was; the caller shows "Validation unavailable"
    } finally { running.current = false; }
  }, [projectId, scriptId]);

  React.useEffect(() => {
    if (!scriptId) { seen.current = undefined; setReport(null); setState("idle"); return; }
    if (seen.current !== scriptId) { seen.current = scriptId; setReport(null); void run(); }
  }, [scriptId, run]);

  return {
    report,
    state,
    run,
    /** Drop the old report (an edit made it stale) and validate again once. */
    revalidate: async () => { setReport(null); await run(); },
    /** True when this script id has already been validated automatically. */
    hasSeen: (id: string | undefined) => Boolean(id) && seen.current === id,
  };
}
