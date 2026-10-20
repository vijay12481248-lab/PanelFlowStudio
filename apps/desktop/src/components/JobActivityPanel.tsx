import React, { useState, useEffect } from "react";
import type { Job } from "@panelflow/shared-types";

export const isActiveJob = (job: Job) => job.status === "QUEUED" || job.status === "RUNNING";
const timestamp = (value?: string | null) => value ? Date.parse(/(Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`) : 0;
const clock = (value?: string | null) => value ? new Date(timestamp(value)).toLocaleString() : "Not started";

export const JobActivityCard: React.FC<{
  job: Job; engineHealthy: boolean; onCancel: (id: string) => Promise<boolean>; onInspect?: () => void;
}> = ({ job, engineHealthy, onCancel, onInspect }) => {
  const [cancelling, setCancelling] = useState(false);
  const [cancelRequested, setCancelRequested] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const active = isActiveJob(job);
  const heartbeat = job.status === "RUNNING" ? (timestamp(job.lease_expires_at) > now ? "Current" : "Delayed / unavailable") : "Not applicable";
  return <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 space-y-2 text-xs text-zinc-300">
    <div className="flex justify-between gap-2"><strong>{job.job_type.replace(/_/g, " ")}</strong><span className="font-mono text-indigo-300">{job.status} · {Math.round(job.progress * 100)}%</span></div>
    <p className="break-all font-mono text-[10px]">Job: {job.job_id}</p>
    <p className="break-all text-[10px]">Project: {job.project_id}</p>
    <p>{job.message}</p>
    <progress className="w-full h-1.5 accent-indigo-500" max={1} value={job.progress} aria-label="Job progress" />
    <dl className="grid grid-cols-2 gap-2 text-[11px]">
      <div><dt className="text-zinc-500">Submitted</dt><dd>{clock(job.created_at)}</dd></div>
      <div><dt className="text-zinc-500">Started (current attempt)</dt><dd>{clock(job.started_at)}</dd></div>
      <div><dt className="text-zinc-500">Engine connection</dt><dd>{engineHealthy ? "Healthy" : "Unavailable"}</dd></div>
      <div><dt className="text-zinc-500">Worker heartbeat</dt><dd>{heartbeat}</dd></div>
      <div><dt className="text-zinc-500">Retries</dt><dd>{job.retry_count || 0}/{job.max_retries ?? 3}</dd></div>
      {job.finished_at && <div><dt className="text-zinc-500">Finished</dt><dd>{clock(job.finished_at)}</dd></div>}
    </dl>
    <div className="flex justify-between items-center gap-2">
      {onInspect && <button className="text-cyan-300 hover:underline" onClick={onInspect}>Job details</button>}
      {active && <button className="rounded border border-rose-800 px-3 py-1 text-rose-300 disabled:opacity-50" disabled={cancelling || cancelRequested || !engineHealthy}
        onClick={async () => { setCancelling(true); try { if (await onCancel(job.job_id)) setCancelRequested(true); } finally { setCancelling(false); } }}>
        {cancelling || cancelRequested ? "Cancellation requested…" : "Cancel job"}
      </button>}
    </div>
  </div>;
};

export const JobActivityPanel: React.FC<{
  jobs: Job[]; engineHealthy: boolean; onCancel: (id: string) => Promise<boolean>; onInspect: (job: Job) => void;
}> = ({ jobs, engineHealthy, onCancel, onInspect }) => {
  const [open, setOpen] = useState(false);
  const active = jobs.filter(isActiveJob);
  const visible = [...active, ...jobs.filter((job) => !isActiveJob(job))].slice(0, 15);
  return <aside className="fixed bottom-4 left-4 z-40 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-indigo-800 bg-zinc-950 shadow-2xl" aria-label="Job activity">
    <button onClick={() => setOpen(!open)} aria-expanded={open} className="w-full p-3 text-left text-xs text-zinc-200 flex justify-between">
      <span>Jobs · {active.length} active</span><span className={engineHealthy ? "text-emerald-400" : "text-amber-300"}>{engineHealthy ? "Engine healthy" : "Engine unavailable"} {open ? "▾" : "▴"}</span>
    </button>
    {open && <div className="p-3 pt-0 space-y-2 max-h-[65vh] overflow-y-auto">
      {visible.length === 0 && <p className="text-xs text-zinc-400">No jobs to display.</p>}
      {visible.map((job) => <JobActivityCard key={job.job_id} job={job} engineHealthy={engineHealthy} onCancel={onCancel} onInspect={() => onInspect(job)} />)}
    </div>}
  </aside>;
};
