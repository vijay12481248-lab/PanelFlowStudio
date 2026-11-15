import React from "react";
import { api } from "@panelflow/api-client";
import { refusal } from "../engineReason";

export type BatchPreset = "TOP_WATERMARK" | "BOTTOM_SUBSCRIBE" | "ALL_TEXT_REGIONS" | "ENTIRE_PANEL";

/**
 * Blur and restore, one operation at a time. A result is returned to the caller to show; a failure becomes words in `error`.
 * `onChanged` is called after each change the engine accepted.
 */
export function useRedaction(projectId: string, onChanged: () => void) {
  const flight = React.useRef(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const run = async <T,>(change: () => Promise<T>, failure: string): Promise<T | null> => {
    if (flight.current) return null;
    flight.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await change();
      onChanged();
      return result;
    } catch (err) {
      setError(refusal(failure, err, "Try again."));
      return null;
    } finally { flight.current = false; setBusy(false); }
  };

  return {
    busy,
    error,
    clearError: () => setError(null),
    blurPanel: (panelId: string, radius = 32) => run(() => api.blurEntirePanel(projectId, panelId, radius), "Couldn't blur the panel."),
    /** Put a panel's original image back. Resolves false when the panel was not blurred, so there was nothing to restore. */
    reset: async (panelId: string) => {
      const result = await run(() => api.resetPanelImage(projectId, panelId), "Couldn't restore the panel.");
      if (result && !result.success) { setError("This panel isn't blurred, so there is nothing to restore."); return false; }
      return Boolean(result);
    },
    batchBlur: (preset: BatchPreset, heightPx: number) => run(() => api.batchBlurPanels(projectId, { preset, height_px: heightPx }), "Couldn't blur the panels."),
    batchReset: () => run(() => api.batchResetPanels(projectId), "Couldn't restore the panels."),
  };
}

export type Redaction = ReturnType<typeof useRedaction>;
