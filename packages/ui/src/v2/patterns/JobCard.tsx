import React from "react";
import { Button } from "../primitives/Button";
import { GlassPanel } from "../primitives/GlassPanel";
import { Progress } from "../primitives/Progress";

export interface JobCardProps {
  title: string;
  detail: string;
  state: "running" | "queued" | "failed";
  progress?: number;
  onCancel?: () => void;
  onRetry?: () => void;
}

export const JobCard: React.FC<JobCardProps> = ({ title, detail, state, progress, onCancel, onRetry }) => (
  <GlassPanel className="grid gap-2 p-4">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-fg">{title}</p>
        <p className="truncate text-xs text-fg-dim">{detail}</p>
      </div>
      {state === "failed" && onRetry && <Button size="sm" variant="primary" onClick={onRetry}>Retry</Button>}
      {state !== "failed" && onCancel && <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>}
    </div>
    {state === "running" && progress !== undefined && <Progress value={progress} label={`${title} progress`} />}
    {state === "queued" && <p className="text-xs text-fg-faint">Waiting for a free slot</p>}
  </GlassPanel>
);
