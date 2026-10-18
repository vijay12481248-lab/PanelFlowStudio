import React, { useEffect, useState, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type { Job, Project, SystemResourcesResponse } from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons } from "@panelflow/ui";

interface MultiProjectQueueDashboardProps {
  projects: Project[];
  onNavigateProject?: (project: Project) => void;
}

export const MultiProjectQueueDashboard: React.FC<MultiProjectQueueDashboardProps> = ({
  projects,
  onNavigateProject,
}) => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [resources, setResources] = useState<SystemResourcesResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [activeFilter, setActiveFilter] = useState<"ALL" | "ACTIVE" | "FAILED" | "COMPLETED">("ALL");
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchQueueData = useCallback(async () => {
    try {
      const [allJobs, sysResources] = await Promise.all([
        api.listAllJobs(undefined, undefined, 40),
        api.getSystemResources().catch(() => null),
      ]);
      setJobs(allJobs);
      if (sysResources) {
        setResources(sysResources);
      }

      // Automatically expand on initial load if there are active running or queued jobs
      const hasActive = allJobs.some(
        (j) => j.status === "RUNNING" || j.status === "QUEUED"
      );
      if (hasActive) {
        setIsExpanded(true);
      }
    } catch (err: any) {
      console.warn("Queue dashboard fetch warning:", err.message);
    }
  }, []);

  useEffect(() => {
    fetchQueueData();

    // Check interval based on whether jobs are currently in flight
    const hasRunningOrQueued = jobs.some(
      (j) => j.status === "RUNNING" || j.status === "QUEUED"
    );
    const intervalMs = hasRunningOrQueued ? 3000 : 8000;

    const timer = setInterval(() => {
      fetchQueueData();
    }, intervalMs);

    return () => clearInterval(timer);
  }, [fetchQueueData, jobs.some((j) => j.status === "RUNNING" || j.status === "QUEUED")]);

  const handleRetryJob = async (jobId: string) => {
    setActionLoading((prev) => ({ ...prev, [jobId]: true }));
    setActionError(null);
    try {
      await api.retryJob(jobId);
      await fetchQueueData();
    } catch (err: any) {
      setActionError(`Retry failed: ${err.message}`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const handleCancelJob = async (jobId: string) => {
    setActionLoading((prev) => ({ ...prev, [jobId]: true }));
    setActionError(null);
    try {
      await api.cancelJob(jobId);
      await fetchQueueData();
    } catch (err: any) {
      setActionError(`Cancel failed: ${err.message}`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const runningJobs = jobs.filter((j) => j.status === "RUNNING");
  const queuedJobs = jobs.filter((j) => j.status === "QUEUED");
  const failedJobs = jobs.filter((j) => j.status === "FAILED" || j.status === "CANCELLED");
  const completedJobs = jobs.filter((j) => j.status === "SUCCEEDED");

  const filteredJobs = jobs.filter((j) => {
    if (activeFilter === "ACTIVE") return j.status === "RUNNING" || j.status === "QUEUED";
    if (activeFilter === "FAILED") return j.status === "FAILED" || j.status === "CANCELLED";
    if (activeFilter === "COMPLETED") return j.status === "SUCCEEDED";
    return true;
  });

  const getJobStatusBadge = (status: string) => {
    switch (status) {
      case "RUNNING":
        return <Badge variant="accent">RUNNING</Badge>;
      case "QUEUED":
        return <Badge variant="warning">QUEUED</Badge>;
      case "SUCCEEDED":
        return <Badge variant="success">COMPLETED</Badge>;
      case "FAILED":
        return <Badge variant="danger">FAILED</Badge>;
      case "CANCELLED":
        return <Badge variant="neutral">CANCELLED</Badge>;
      default:
        return <Badge variant="neutral">{status}</Badge>;
    }
  };

  const formatJobType = (jobType: string) => {
    return jobType
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  return (
    <Card className="bg-zinc-900/90 border-zinc-800 shadow-md transition-all">
      {/* Top Header & Telemetry Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors"
            title={isExpanded ? "Collapse Queue Dashboard" : "Expand Queue Dashboard"}
          >
            {isExpanded ? (
              <Icons.ChevronUp className="w-5 h-5" />
            ) : (
              <Icons.ChevronDown className="w-5 h-5" />
            )}
          </button>

          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-zinc-100">
                Multi-Project Job Queue
              </h3>
              {runningJobs.length > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-950 text-indigo-400 border border-indigo-800 animate-pulse">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
                  {runningJobs.length} Running
                </span>
              )}
              {queuedJobs.length > 0 && (
                <Badge variant="warning">
                  {queuedJobs.length} Queued
                </Badge>
              )}
              {runningJobs.length === 0 && queuedJobs.length === 0 && (
                <Badge variant="neutral">Idle</Badge>
              )}
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              Resource-aware fair scheduler across projects with crash recovery and GPU admission gating.
            </p>
          </div>
        </div>

        {/* Admission Controls & Telemetry Badges */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {resources && (
            <>
              {/* GPU Admission Meter */}
              <div
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border ${
                  resources.scheduler.active_count >= resources.scheduler.effective_limit
                    ? "bg-amber-950/40 border-amber-800/80 text-amber-300"
                    : "bg-zinc-950 border-zinc-800 text-zinc-300"
                }`}
                title="Active GPU tasks vs concurrency admission limit"
              >
                <Icons.Cpu className="w-3.5 h-3.5 text-zinc-400" />
                <span>
                  GPU Slots:{" "}
                  <strong className="font-semibold text-zinc-100">
                    {resources.scheduler.active_count} / {resources.scheduler.effective_limit}
                  </strong>{" "}
                  ({resources.scheduler.concurrency_mode})
                </span>
              </div>

              {/* VRAM Headroom */}
              {resources.gpu.available && (
                <div
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-300"
                  title={`${resources.gpu.device_name}: ${(resources.gpu.used_mb / 1024).toFixed(1)} GB used of ${(resources.gpu.total_mb / 1024).toFixed(1)} GB`}
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                  <span>
                    VRAM Headroom:{" "}
                    <strong className="text-zinc-100">
                      {(resources.gpu.headroom_mb / 1024).toFixed(1)} GB
                    </strong>
                  </span>
                </div>
              )}
            </>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={fetchQueueData}
            title="Refresh job queue status"
          >
            <Icons.Refresh className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {actionError && (
        <div className="mt-3 p-2.5 bg-rose-950/60 border border-rose-800 rounded-lg text-xs text-rose-200 flex items-center justify-between">
          <span>{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            className="text-rose-400 hover:text-rose-200 text-sm font-bold ml-2"
          >
            ×
          </button>
        </div>
      )}

      {queuedJobs.length > 0 && resources?.scheduler.concurrency_mode === "MANUAL" && (
        <div className="mt-3 rounded-lg border border-amber-800/70 bg-amber-950/30 px-3 py-2 text-xs text-amber-200">
          GPU jobs are waiting for manual admission. Keep this queue open while a worker becomes available, or switch the scheduler to automatic admission in Tools &amp; Models.
        </div>
      )}

      {/* Collapsed mini-progress indicator */}
      {!isExpanded && runningJobs.length > 0 && (
        <div className="mt-3 pt-3 border-t border-zinc-800/80">
          <div className="flex items-center justify-between text-xs text-zinc-300 mb-1">
            <span className="font-medium text-indigo-300">
              {formatJobType(runningJobs[0].job_type)}: {runningJobs[0].message || "Processing..."}
            </span>
            <span className="text-zinc-400 font-mono">
              {Math.round((runningJobs[0].progress || 0) * 100)}%
            </span>
          </div>
          <ProgressBar progress={runningJobs[0].progress || 0} />
        </div>
      )}

      {/* Expanded Table & Job Cards */}
      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-zinc-800 space-y-3">
          {/* Filter Pills */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 bg-zinc-950 p-1 rounded-lg border border-zinc-800">
              <button
                onClick={() => setActiveFilter("ALL")}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                  activeFilter === "ALL"
                    ? "bg-zinc-800 text-zinc-100 font-medium"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                All ({jobs.length})
              </button>
              <button
                onClick={() => setActiveFilter("ACTIVE")}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                  activeFilter === "ACTIVE"
                    ? "bg-indigo-900/60 text-indigo-200 font-medium"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Active ({runningJobs.length + queuedJobs.length})
              </button>
              <button
                onClick={() => setActiveFilter("FAILED")}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                  activeFilter === "FAILED"
                    ? "bg-rose-950/80 text-rose-300 font-medium"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Failed / Interrupted ({failedJobs.length})
              </button>
              <button
                onClick={() => setActiveFilter("COMPLETED")}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                  activeFilter === "COMPLETED"
                    ? "bg-zinc-800 text-zinc-100 font-medium"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Completed ({completedJobs.length})
              </button>
            </div>

            <div className="text-xs text-zinc-500 font-mono">
              Auto-refreshing queue (SQLite persistent)
            </div>
          </div>

          {/* Jobs Listing */}
          {filteredJobs.length === 0 ? (
            <div className="py-8 text-center text-xs text-zinc-500 bg-zinc-950/40 rounded-lg border border-zinc-800/60">
              No jobs found for filter &quot;{activeFilter}&quot;.
            </div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
              {filteredJobs.map((job) => {
                const targetProject = projects.find((p) => p.id === job.project_id);
                const isActionActive = actionLoading[job.job_id] || false;

                return (
                  <div
                    key={job.job_id}
                    className="p-3 bg-zinc-950/70 border border-zinc-800/90 rounded-lg hover:border-zinc-700 transition-colors space-y-2 text-xs"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        {getJobStatusBadge(job.status)}

                        <span className="font-semibold text-zinc-200">
                          {formatJobType(job.job_type)}
                        </span>

                        {targetProject ? (
                          <button
                            onClick={() => onNavigateProject?.(targetProject)}
                            className="text-indigo-400 hover:text-indigo-300 hover:underline font-medium"
                            title="Jump to project view"
                          >
                            {targetProject.title}
                          </button>
                        ) : (
                          <span className="text-zinc-400 font-mono">
                            {job.project_id.slice(0, 8)}...
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {job.requires_gpu && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-zinc-800 text-zinc-300 border border-zinc-700">
                            GPU {job.gpu_vram_mb || 4096} MB
                          </span>
                        )}

                        {job.worker_lease_id && (
                          <span
                            className="px-2 py-0.5 rounded text-[10px] font-mono text-zinc-400 bg-zinc-900 border border-zinc-800"
                            title={`Worker Lease ID: ${job.worker_lease_id}`}
                          >
                            Lease: {job.worker_lease_id.slice(0, 12)}
                          </span>
                        )}

                        {(job.retry_count ?? 0) > 0 && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold text-amber-400 bg-amber-950/50 border border-amber-800">
                            Retry {job.retry_count}/{job.max_retries || 3}
                          </span>
                        )}

                        {/* Action buttons */}
                        {(job.status === "FAILED" || job.status === "CANCELLED") && (
                          <Button
                            variant="outline"
                            size="sm"
                            loading={isActionActive}
                            onClick={() => handleRetryJob(job.job_id)}
                            className="text-xs h-7 px-2.5 text-indigo-300 border-indigo-700/60 hover:bg-indigo-950/50"
                          >
                            <Icons.Refresh className="w-3 h-3 mr-1" />
                            Retry
                          </Button>
                        )}

                        {(job.status === "RUNNING" || job.status === "QUEUED") && (
                          <Button
                            variant="destructive"
                            size="sm"
                            loading={isActionActive}
                            onClick={() => handleCancelJob(job.job_id)}
                            className="text-xs h-7 px-2.5"
                          >
                            Cancel
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Progress Bar & Message */}
                    <div className="space-y-1">
                      <div className="flex justify-between text-[11px] text-zinc-400">
                        <span className="truncate max-w-md">
                          {job.message || (job.status === "QUEUED" ? "Waiting for available slot..." : "In progress")}
                        </span>
                        <span className="font-mono">
                          {Math.round((job.progress || 0) * 100)}%
                        </span>
                      </div>
                      <ProgressBar progress={job.progress || 0} />
                    </div>

                    {/* Error display if failed */}
                    {job.error && (
                      <div className="p-2 bg-rose-950/40 border border-rose-900/60 rounded text-[11px] text-rose-300 font-mono break-words">
                        {job.error}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </Card>
  );
};
