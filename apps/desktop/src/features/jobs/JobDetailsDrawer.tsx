import React from "react";
import { Link } from "react-router";
import type { Job } from "@panelflow/shared-types";
import { Drawer } from "@panelflow/ui-v2";
import { paths } from "../../app/routes";
import { jobDuration, jobLabel } from "./jobsView";

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "Not yet");

export interface JobDetailsDrawerProps {
  job: Job | null;
  projectTitle: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const JobDetailsDrawer: React.FC<JobDetailsDrawerProps> = ({ job, projectTitle, open, onOpenChange }) => (
  <Drawer open={open && job !== null} onOpenChange={onOpenChange} title={job ? `${jobLabel(job.job_type)}, ${projectTitle}` : "Job details"}>
    {job && (
      <dl className="grid gap-3 text-sm grid-cols-1">
        <Row label="Status">{job.status.charAt(0) + job.status.slice(1).toLowerCase()}</Row>
        <Row label="Message">{job.message || "None"}</Row>
        <Row label="Started">{when(job.started_at)}</Row>
        <Row label="Finished">{when(job.finished_at)}</Row>
        <Row label="Duration">{jobDuration(job, Date.now()) ?? "Not started"}</Row>
        <Row label="Retries">{`${job.retry_count ?? 0} of ${job.max_retries ?? 0}`}</Row>
        {job.error && (
          <div>
            <dt className="mb-1 text-fg-faint">Error</dt>
            <dd><pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-ctl border border-edge bg-ink p-3 font-data text-xs text-fg-dim">{job.error}</pre></dd>
          </div>
        )}
        <Link to={paths.project(job.project_id)} className="text-info underline underline-offset-2">Open the project</Link>
      </dl>
    )}
  </Drawer>
);

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex justify-between gap-4">
    <dt className="text-fg-faint">{label}</dt>
    <dd className="text-right text-fg">{children}</dd>
  </div>
);
