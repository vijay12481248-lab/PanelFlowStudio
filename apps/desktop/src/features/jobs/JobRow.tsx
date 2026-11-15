import React from "react";
import type { Job } from "@panelflow/shared-types";
import { Button, Chip, Progress, type Tone } from "@panelflow/ui-v2";
import { firstErrorLine, jobDuration, jobLabel } from "./jobsView";

const STATUS: Record<Job["status"], { word: string; tone: Tone }> = {
  RUNNING: { word: "Running", tone: "accent" },
  QUEUED: { word: "Waiting", tone: "neutral" },
  FAILED: { word: "Failed", tone: "bad" },
  CANCELLED: { word: "Cancelled", tone: "warn" },
  SUCCEEDED: { word: "Done", tone: "ok" },
};

export function jobSubtitle(job: Job, now: number): string {
  switch (job.status) {
    case "FAILED": return firstErrorLine(job);
    case "RUNNING": return job.message || "Working";
    case "QUEUED": return "Waiting for a free slot";
    case "CANCELLED": return "Cancelled";
    default: return jobDuration(job, now) ?? "Finished";
  }
}

export interface JobRowProps {
  job: Job;
  projectTitle: string;
  onOpen: () => void;
  onRetry: () => void;
  onCancel: () => void;
  busy: boolean;
}

export const JobRow: React.FC<JobRowProps> = ({ job, projectTitle, onOpen, onRetry, onCancel, busy }) => {
  const status = STATUS[job.status];
  return (
    <div className="flex items-center gap-3 rounded-ctl border border-edge bg-flat p-3">
      <button type="button" data-job-open onClick={onOpen} className="min-w-0 flex-1 text-left focus-visible:outline-2 focus-visible:outline-info">
        <span className="block truncate text-sm font-medium text-fg">{`${jobLabel(job.job_type)}, ${projectTitle}`}</span>
        <span className="block truncate text-xs text-fg-faint">{jobSubtitle(job, Date.now())}</span>
      </button>
      {job.status === "RUNNING" && <Progress className="w-32" value={Math.round((job.progress || 0) * 100)} label={`${jobLabel(job.job_type)} progress`} />}
      <Chip tone={status.tone}>{status.word}</Chip>
      {job.status === "FAILED" && <Button size="sm" variant="primary" loading={busy} onClick={onRetry}>Retry</Button>}
      {(job.status === "RUNNING" || job.status === "QUEUED") && <Button size="sm" variant="ghost" loading={busy} onClick={onCancel}>Cancel</Button>}
    </div>
  );
};
