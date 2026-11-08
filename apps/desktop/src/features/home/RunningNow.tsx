import React from "react";
import { Link } from "react-router";
import type { Job } from "@panelflow/shared-types";
import { JobCard } from "@panelflow/ui-v2";
import { paths } from "../../app/routes";
import { groupJobs, jobLabel } from "../jobs/jobsView";

const SHOWN = 3;

export const RunningNow: React.FC<{ jobs: Job[]; projectTitles: ReadonlyMap<string, string> }> = ({ jobs, projectTitles }) => {
  const active = groupJobs(jobs).active;
  return (
    <section aria-label="Running now" className="grid gap-2">
      <div className="flex items-center justify-between px-2">
        <h3 className="text-xs font-medium text-fg-faint">Running now</h3>
        <Link to={paths.jobs()} className="text-xs text-info underline underline-offset-2">All jobs</Link>
      </div>
      {active.length === 0 && <p className="px-2 text-sm text-fg-dim">Nothing is running right now.</p>}
      {active.slice(0, SHOWN).map((job) => (
        <JobCard
          key={job.job_id}
          title={`${jobLabel(job.job_type)}, ${projectTitles.get(job.project_id) ?? "Unknown project"}`}
          detail={job.message || (job.status === "RUNNING" ? "Working" : "Waiting for a free slot")}
          state={job.status === "RUNNING" ? "running" : "queued"}
          progress={job.status === "RUNNING" ? Math.round((job.progress || 0) * 100) : undefined}
        />
      ))}
    </section>
  );
};
