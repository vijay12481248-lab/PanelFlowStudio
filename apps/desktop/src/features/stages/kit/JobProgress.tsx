import React from "react";
import type { Job } from "@panelflow/shared-types";
import { Chip, Progress, type Tone } from "@panelflow/ui-v2";

const STATUS: Record<string, { word: string; tone: Tone }> = {
  RUNNING: { word: "Running", tone: "accent" },
  QUEUED: { word: "Waiting", tone: "neutral" },
  SUCCEEDED: { word: "Done", tone: "ok" },
  FAILED: { word: "Failed", tone: "bad" },
  CANCELLED: { word: "Cancelled", tone: "warn" },
};

/** A job's status in words, its engine message and a progress bar (job.progress is 0 to 1). */
export const JobProgress: React.FC<{ job: Job | null | undefined; idleLabel: string }> = ({ job, idleLabel }) => {
  if (!job) return <p className="text-sm text-fg-dim">{idleLabel}</p>;
  const status = STATUS[job.status] ?? { word: job.status, tone: "neutral" as Tone };
  return (
    <div className="grid grid-cols-1 gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={status.tone}>{status.word}</Chip>
        {job.message && <span className="text-sm text-fg-dim">{job.message}</span>}
      </div>
      <Progress value={Math.round((job.progress || 0) * 100)} label={`${status.word} progress`} />
    </div>
  );
};
