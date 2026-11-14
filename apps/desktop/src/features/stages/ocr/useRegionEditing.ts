import React from "react";
import { api } from "@panelflow/api-client";
import type { TextRegion } from "@panelflow/shared-types";
import type { Box } from "../kit/canvas/geometry";
import { refusal } from "../kit/engineReason";
import { type EditForm, approvePatch, regionPatch } from "./ocrModel";

export interface RegionEditingOptions {
  projectId: string;
  /** The engine chosen for reading text. Null when none can be used. */
  engineId: string | null;
  /** Reload what a change touched. */
  onChanged: () => void | Promise<void>;
}

/**
 * Changes to one text region at a time. A second action while one is running is ignored; a failure becomes a sentence in `error`
 * and returns false, so the caller keeps what the person typed.
 */
export function useRegionEditing({ projectId, engineId, onChanged }: RegionEditingOptions) {
  const flight = React.useRef(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const run = async <T,>(failure: string, task: () => Promise<T>): Promise<T | null> => {
    if (flight.current) return null;
    flight.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await task();
      await onChanged();
      return result;
    } catch (err) {
      setError(refusal(failure, err));
      return null;
    } finally { flight.current = false; setBusy(false); }
  };

  return {
    busy,
    error,
    clearError: () => setError(null),
    /** Save what changed. Nothing changed means nothing is sent, and that counts as saved. */
    async save(region: TextRegion, form: EditForm): Promise<boolean> {
      const patch = regionPatch(region, form);
      if (Object.keys(patch).length === 0) return true;
      return (await run("Couldn't save the region.", async () => { await api.updateTextRegion(projectId, region.id, patch); return true; })) === true;
    },
    /** Confirm the region with its text. Blank text is refused: it must be typed or the region ignored. */
    async approve(region: TextRegion, form: EditForm): Promise<boolean> {
      const patch = approvePatch(region, form);
      if (!patch) { setError("Type the text, or ignore this region."); return false; }
      return (await run("Couldn't approve the region.", async () => { await api.updateTextRegion(projectId, region.id, patch); return true; })) === true;
    },
    /** REJECTED is the status the export contract and the audio step leave out. */
    async reject(region: TextRegion): Promise<boolean> {
      return (await run("Couldn't ignore the region.", async () => { await api.updateTextRegion(projectId, region.id, { status: "REJECTED" }); return true; })) === true;
    },
    async remove(region: TextRegion): Promise<boolean> {
      return (await run("Couldn't delete the region.", async () => { await api.deleteTextRegion(projectId, region.id); return true; })) === true;
    },
    async readOne(region: TextRegion): Promise<boolean> {
      if (!engineId) { setError("No OCR engine is available. Install one in Settings."); return false; }
      return (await run("Couldn't read the text again.", async () => { await api.ocrSingleRegion(projectId, region.id, engineId, "en"); return true; })) === true;
    },
    /** A region drawn by hand on a panel's crop. Returns the new region. */
    async createFromBox(panelId: string, box: Box): Promise<TextRegion | null> {
      return run("Couldn't add the text region.", () => api.createManualTextRegion(projectId, panelId, box.x, box.y, box.w, box.h));
    },
  };
}

export type RegionEditing = ReturnType<typeof useRegionEditing>;
