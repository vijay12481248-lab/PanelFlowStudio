import type { Job } from "@panelflow/shared-types";

export type JobTab = "active" | "failed" | "done";

const ACRONYMS = new Set(["OCR", "H3", "PDF", "GPU", "TTS", "LLM", "AI", "SFX"]);

/** "OCR_EXTRACTION" becomes "OCR extraction". */
export function jobLabel(jobType: string): string {
  const words = jobType.split("_").filter(Boolean).map((word) => {
    const upper = word.toUpperCase();
    return ACRONYMS.has(upper) ? upper : word.toLowerCase();
  });
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const time = (value: string | null | undefined) => (value ? Date.parse(value) : 0);
const newestFirst = (when: (job: Job) => number) => (a: Job, b: Job) => when(b) - when(a);

export function groupJobs(jobs: Job[]): Record<JobTab, Job[]> {
  const created = newestFirst((job) => time(job.created_at));
  const finished = newestFirst((job) => time(job.finished_at ?? job.created_at));
  return {
    active: [...jobs.filter((j) => j.status === "RUNNING").sort(created), ...jobs.filter((j) => j.status === "QUEUED").sort(created)],
    failed: jobs.filter((j) => j.status === "FAILED" || j.status === "CANCELLED").sort(finished),
    done: jobs.filter((j) => j.status === "SUCCEEDED").sort(finished),
  };
}

export function jobDuration(job: Job, now: number): string | null {
  if (!job.started_at) return null;
  const seconds = Math.max(0, Math.round(((job.finished_at ? Date.parse(job.finished_at) : now) - Date.parse(job.started_at)) / 1000));
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
  return `${Math.floor(seconds / 3600)} h ${Math.floor((seconds % 3600) / 60)} min`;
}

/** The cause of a failure, without the traceback. */
export function firstErrorLine(job: Job): string {
  const line = (job.error ?? "").split("\n").map((l) => l.trim()).find(Boolean);
  const text = line || job.message || "No details were recorded.";
  return text.length > 160 ? text.slice(0, 160) : text;
}
