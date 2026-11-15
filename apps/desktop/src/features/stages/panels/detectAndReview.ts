import type { api } from "@panelflow/api-client";
import { engineProblem, pickEngine } from "../kit/ocrEngine";

/** A failure to show to the person, already in words. */
export class ReviewError extends Error {}

export interface ReviewDeps {
  api: Pick<typeof api, "listOCREngines" | "detectPanels" | "getJob" | "cancelJob" | "listPanels" | "detectTextRegions" | "ocrSingleRegion" | "getPanelContentSuggestions">;
  sleep: (ms: number) => Promise<void>;
}

export interface ReviewRun {
  projectId: string;
  direction: "ltr" | "rtl";
  deps: ReviewDeps;
  /** True once the person cancelled or left the screen. Checked between every step and every poll. */
  isCancelled: () => boolean;
  onStep: (step: string) => void;
}

const CANCELLED = "Detect and review was cancelled.";

/**
 * Detect panels, find the text in them, read it with a real OCR engine, then look for promotional text.
 * Each step waits for the engine's job to end: there is no time limit that could call a running job failed. Cancelling
 * cancels the running job and stops. Throws a ReviewError with a sentence for the person.
 */
export async function runDetectAndReview({ projectId, direction, deps, isCancelled, onStep }: ReviewRun) {
  const { api, sleep } = deps;
  const stopIfCancelled = () => { if (isCancelled()) throw new ReviewError(CANCELLED); };

  onStep("Checking the OCR engine");
  const engines = await api.listOCREngines();
  stopIfCancelled();
  const engine = pickEngine(engines);
  if (!engine) throw new ReviewError(engineProblem(engines) ?? "No OCR engine is available. Install one in Settings.");

  onStep("Detecting panels. Pages with edits are kept.");
  const { job_id: jobId } = await api.detectPanels(projectId, direction, 0.02);
  for (;;) {
    if (isCancelled()) {
      await api.cancelJob(jobId).catch(() => undefined);
      throw new ReviewError(CANCELLED);
    }
    const job = await api.getJob(jobId);
    if (job.status === "SUCCEEDED") break;
    if (job.status === "FAILED" || job.status === "CANCELLED") throw new ReviewError(`Couldn't detect the panels. ${job.error || job.message || "The job stopped."}`.trim());
    await sleep(1000);
  }
  await api.listPanels(projectId);

  stopIfCancelled();
  onStep("Finding text regions");
  const regions = await api.detectTextRegions(projectId);
  const pending = regions.filter((r) => !r.raw_text && !r.corrected_text && r.status !== "IGNORED");
  for (let i = 0; i < pending.length; i++) {
    stopIfCancelled();
    onStep(`Reading text ${i + 1} of ${pending.length}`);
    await api.ocrSingleRegion(projectId, pending[i].id, engine);
  }

  stopIfCancelled();
  onStep("Looking for promotional text");
  return api.getPanelContentSuggestions(projectId);
}
