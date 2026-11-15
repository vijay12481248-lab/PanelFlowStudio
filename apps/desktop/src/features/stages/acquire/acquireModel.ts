import type { Job, Page } from "@panelflow/shared-types";

export type AcquirePhase = "ready" | "running" | "succeeded" | "failed" | "cancelled";

export interface PageCounts { total: number; ready: number; failed: number }

const ACQUISITION_JOBS = new Set(["ACQUISITION", "RETRY_PAGES"]);

/** The newest acquisition (or retry) job. The engine lists a project's jobs newest first. */
export function latestAcquisitionJob(jobs: Job[] | undefined): Job | null {
  return (jobs ?? []).find((job) => ACQUISITION_JOBS.has(job.job_type)) ?? null;
}

export function acquirePhase(job: Job | null | undefined): AcquirePhase {
  if (!job) return "ready";
  switch (job.status) {
    case "RUNNING":
    case "QUEUED": return "running";
    case "SUCCEEDED": return "succeeded";
    case "FAILED": return "failed";
    default: return "cancelled";
  }
}

export function pageCounts(pages: Page[]): PageCounts {
  return { total: pages.length, ready: pages.filter((p) => p.status === "READY").length, failed: pages.filter((p) => p.status === "FAILED").length };
}

export interface AcquireActions {
  start: "Start acquisition" | "Restart acquisition" | null;
  cancel: boolean;
  /** How many failed pages a retry would try again, or null when a retry is not offered. */
  retryFailed: number | null;
  review: boolean;
}

export function acquireActions(phase: AcquirePhase, counts: PageCounts): AcquireActions {
  const running = phase === "running";
  return {
    start: phase === "ready" ? "Start acquisition" : phase === "failed" || phase === "cancelled" ? "Restart acquisition" : null,
    cancel: running,
    retryFailed: !running && counts.failed > 0 ? counts.failed : null,
    review: counts.ready > 0,
  };
}
