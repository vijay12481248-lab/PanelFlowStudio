import React, { useState, useEffect } from "react";
import type { Job } from "@panelflow/shared-types";

// ——— Helpers ———
export const isActiveJob = (job: Job) => job.status === "QUEUED" || job.status === "RUNNING";
const timestamp = (value?: string | null) => value ? Date.parse(/(Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`) : 0;
const clock = (value?: string | null) => value ? new Date(timestamp(value)).toLocaleString() : "Not started";

// ——— Types ———
type EngineState = "healthy" | "starting" | "degraded" | "offline" | "unknown";

export interface EngineJobStatusProps {
  engineHealthy: boolean;
  jobs: Job[];
  onCancel: (id: string) => Promise<boolean>;
  onOpenManager?: () => void;
}

// ——— Card for individual job inside dropdown ———
export const JobActivityCard: React.FC<{
  job: Job; engineHealthy: boolean; onCancel: (id: string) => Promise<boolean>; onInspect?: () => void;
}> = ({ job, engineHealthy, onCancel, onInspect }) => {
  const [cancelling, setCancelling] = useState(false);
  const [cancelRequested, setCancelRequested] = useState(false);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const active = isActiveJob(job);
  const heartbeat = job.status === "RUNNING"
    ? (timestamp(job.lease_expires_at) > now ? "Current" : "Delayed / unavailable")
    : "Not applicable";

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 space-y-2 text-xs text-zinc-300">
      <div className="flex justify-between gap-2">
        <strong className="text-[11px]">{job.job_type.replace(/_/g, " ")}</strong>
        <span className="font-mono text-[11px] text-indigo-400">{job.status} · {Math.round(job.progress * 100)}%</span>
      </div>
      <p className="break-all font-mono text-[10px] text-zinc-500">Job: {job.job_id}</p>
      <p className="break-all text-[10px] text-zinc-500">Project: {job.project_id}</p>
      <p className="text-[10px]">{job.message || "No message"}</p>
      <progress className="w-full h-1.5 accent-indigo-600" max={1} value={job.progress} aria-label="Job progress" />
      <dl className="grid grid-cols-2 gap-2 text-[11px]">
        <div><dt className="text-zinc-500">Submitted</dt><dd>{clock(job.created_at)}</dd></div>
        <div><dt className="text-zinc-500">Started (current attempt)</dt><dd>{clock(job.started_at)}</dd></div>
        <div><dt className="text-zinc-500">Engine connection</dt><dd>{engineHealthy ? "Healthy" : "Unavailable"}</dd></div>
        <div><dt className="text-zinc-500">Worker heartbeat</dt><dd>{heartbeat}</dd></div>
        <div><dt className="text-zinc-500">Retries</dt><dd>{job.retry_count || 0}/{job.max_retries ?? 3}</dd></div>
        {job.finished_at && <div><dt className="text-zinc-500">Finished</dt><dd>{clock(job.finished_at)}</dd></div>}
      </dl>
      <div className="flex justify-between items-center gap-2 pt-1">
        {onInspect && (
          <button onClick={onInspect} className="text-[10px] text-cyan-400 hover:text-cyan-300 px-1.5 py-0.5 rounded bg-cyan-950/30">
            Job details
          </button>
        )}
        {active && (
          <button
            onClick={async () => {
              setCancelling(true);
              try { if (await onCancel(job.job_id)) setCancelRequested(true); } catch { /* ignore */ } finally { setCancelling(false); }
            }}
            disabled={cancelling || cancelRequested || !engineHealthy}
            className="rounded border border-rose-800/80 px-2.5 py-1 text-rose-400 disabled:opacity-40 bg-rose-950/20 hover:bg-rose-950/40 text-[11px]"
          >
            {cancelling || cancelRequested ? "Cancellation requested…" : "Cancel job"}
          </button>
        )}
      </div>
    </div>
  );
};

// ——— Main Engine Job Status (toolbar-integrated) ———
export const EngineJobStatus: React.FC<EngineJobStatusProps> = ({
  engineHealthy, jobs, onCancel, onOpenManager,
}) => {
  const [open, setOpen] = useState(false);
  const activeJobs = jobs.filter(isActiveJob);
  const queuedJobs = jobs.filter((j) => j.status === "QUEUED");
  const completedJobs = jobs.filter((j) => j.status === "SUCCEEDED");
  const failedJobs = jobs.filter((j) => j.status === "FAILED");
  const recentActive = activeJobs.slice(0, 6);

  // Determine engine display state
  const engineState: EngineState = !engineHealthy ? "offline" : activeJobs.length === 0 ? "healthy" : "starting";
  const isWide = typeof window !== "undefined" && window.innerWidth >= 1440;

  // Close on escape / outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  // Status dot colors based on state
  const statusColors: Record<EngineState, string> = {
    healthy: "bg-emerald-400 animate-pulse shadow-[0_0_6px_rgba(52,211,153,0.4)]",
    starting: "bg-amber-400 animate-pulse shadow-[0_0_6px_rgba(251,191,36,0.4)]",
    degraded: "bg-amber-500 shadow-sm",
    offline: "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.3)]",
    unknown: "bg-zinc-500 shadow-sm",
  };

  const statusLabel = { healthy: "Healthy", starting: "Starting", degraded: "Degraded", offline: "Offline", unknown: "Unknown" }[engineState];

  return (
    <div className="flex items-center relative">
      {/* Pill toggle */}
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="true"
        aria-expanded={open}
        className={`
          flex items-center gap-2 px-3 py-1 rounded-md border text-[11px] transition-all cursor-pointer
          ${open ? "bg-zinc-950 border-zinc-600 text-white shadow-inner" : "bg-zinc-900/80 border-zinc-800 hover:border-zinc-600 hover:bg-zinc-900"}
        `}
      >
        {/* Status dot */}
        <span className="flex-shrink-0">
          <span className={`inline-block w-2 h-2 rounded-full ${statusColors[engineState]}`} />
        </span>

        {/* Responsive text density */}
        <span className="text-zinc-400/90 font-medium flex-shrink-0 truncate max-w-[6rem]" title={engineHealthy ? "Engine healthy" : "Engine unavailable"}>
          {isWide ? `Engine ${statusLabel}` : statusLabel}
        </span>

        {/* Separator */}
        <span className="w-px h-3 bg-zinc-700/60 hidden sm:inline-block" />

        {/* Active count (always shown) */}
        <span className="text-zinc-400 font-medium flex-shrink-0">
          Jobs <strong className={activeJobs.length > 0 ? "text-zinc-100" : ""}>{activeJobs.length}</strong>
        </span>

        {/* Chevron */}
        <svg className={`w-3.5 h-3.5 text-zinc-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Dropdown — absolute positioned relative to this wrapper */}
      {open && (
        <div
          className="absolute top-10 left-[50%] -translate-x-[50%] z-[60] w-84 bg-zinc-950 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden"
          role="dialog"
          aria-label="Jobs and engine status"
        >
          {/* Header */}
          <div className="px-3 py-2 border-b border-zinc-800 bg-zinc-900/50 flex items-center justify-between">
            <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${statusColors[engineState]}`} />
              Background Jobs
            </span>
            <button onClick={() => setOpen(false)} className="text-zinc-600 hover:text-zinc-400 p-0.5" aria-label="Close dropdown">
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
            </button>
          </div>

          {/* Content */}
          <div className="p-3 space-y-3 max-h-[30rem] overflow-y-auto scrollbar-thin">
            {/* Engine + Job Counts Grid */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              {/* Engine */}
              <div className={`rounded-lg border p-2.5 ${engineHealthy ? "border-emerald-800/40 bg-emerald-950/20" : "border-rose-800/40 bg-rose-950/10"}`}>
                <span className={`block text-[11px] font-semibold ${engineHealthy ? "text-emerald-400" : "text-rose-400"}`}>Engine</span>
                <span className="text-zinc-400">{statusLabel}</span>
              </div>
              {/* Active jobs */}
              <div className={`rounded-lg border p-2.5 ${activeJobs.length > 0 ? "border-indigo-800/30 bg-indigo-950/15" : "border-zinc-800/40 bg-zinc-900/20"}`}>
                <span className="text-[11px] font-semibold text-zinc-400">Active</span>
                <span className="block text-xl font-bold text-white">{activeJobs.length}</span>
              </div>
            </div>

            {/* Job categories breakdown (only when no active jobs and no queued) */}
            {activeJobs.length === 0 && queuedJobs.length === 0 && (
              <div className="space-y-2">
                {[
                  [`${completedJobs.length} Completed`, "text-zinc-400"],
                  [`${failedJobs.length} Failed`, "text-amber-400"],
                  [`${queuedJobs.length} Queued`, "text-zinc-500"],
                ].map(([label, color]) => (
                  <div key={label} className="flex justify-between text-xs">
                    <span className={`px-2 py-1 rounded border ${color.replace("text-", "bg-").replace("/40", "/10")} ${color} border-zinc-800/60`}>
                      {label}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Active jobs list */}
            {recentActive.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                  Active Jobs ({recentActive.length})
                </span>
                <div className="space-y-2">
                  {recentActive.map((job) => (
                    <JobActivityCard
                      key={job.job_id}
                      job={job}
                      engineHealthy={engineHealthy}
                      onCancel={onCancel}
                      onInspect={() => console.log("Inspect job:", job.job_id)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Empty active state */}
            {activeJobs.length === 0 && (
              <div className="text-center py-8">
                <svg className="w-9 h-9 mx-auto mb-2 text-zinc-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="9 12 11 14 15 10" />
                </svg>
                <p className="text-xs text-zinc-600">All jobs idle</p>
              </div>
            )}

            {/* Footer actions */}
            {(onOpenManager || jobs.length > 0) && (
              <div className="pt-2 border-t border-zinc-800 flex justify-between items-center text-[11px]">
                {jobs.length > 0 && (
                  <span className="text-zinc-500">{jobs.length} total jobs</span>
                )}
                {onOpenManager && (
                  <button onClick={() => { onOpenManager(); setOpen(false); }} className="text-indigo-400 hover:text-indigo-300 font-medium px-2 py-1 rounded bg-indigo-950/30">
                    Open Job Manager →
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

