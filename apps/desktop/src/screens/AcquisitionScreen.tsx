import React, { useEffect, useState, useRef } from "react";
import { api } from "@panelflow/api-client";
import type { Project, Job, Page } from "@panelflow/shared-types";
import { Button, Card, ProgressBar, Badge, Icons } from "@panelflow/ui";

interface AcquisitionScreenProps {
  project: Project;
  onBack: () => void;
  onReviewPages: () => void;
}

export const AcquisitionScreen: React.FC<AcquisitionScreenProps> = ({
  project,
  onBack,
  onReviewPages,
}) => {
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState<boolean>(false);
  const [retrying, setRetrying] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const pollTimerRef = useRef<number | null>(null);

  const loadCurrentState = async () => {
    try {
      // 1. Fetch pages
      const pageList = await api.listPages(project.id);
      setPages(pageList);

      // 2. Fetch project jobs to find latest
      const jobs = await api.listProjectJobs(project.id);
      if (jobs.length > 0) {
        setActiveJob(jobs[0]);
      }
    } catch (err: any) {
      console.error("Error loading acquisition state:", err);
    }
  };

  const startJob = async () => {
    setIsStarting(true);
    setErrorMsg(null);
    try {
      const res = await api.startAcquisition(project.id);
      const job = await api.getJob(res.job_id);
      setActiveJob(job);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to start acquisition job.");
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancel = async () => {
    if (!activeJob) return;
    setCancelling(true);
    try {
      await api.cancelJob(activeJob.job_id);
      const updated = await api.getJob(activeJob.job_id);
      setActiveJob(updated);
    } catch (err: any) {
      alert(`Could not cancel job: ${err.message}`);
    } finally {
      setCancelling(false);
    }
  };

  const handleRetryFailed = async () => {
    setRetrying(true);
    setErrorMsg(null);
    try {
      const res = await api.retryFailedPages(project.id);
      const job = await api.getJob(res.job_id);
      setActiveJob(job);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to retry pages.");
    } finally {
      setRetrying(false);
    }
  };

  const handleOpenFolder = async () => {
    try {
      await api.openProjectFolder(project.id);
    } catch (err: any) {
      alert(`Could not open folder: ${err.message}`);
    }
  };

  // Polling loop while job is running or queued
  useEffect(() => {
    loadCurrentState();

    pollTimerRef.current = window.setInterval(async () => {
      if (activeJob && (activeJob.status === "RUNNING" || activeJob.status === "QUEUED")) {
        try {
          const updatedJob = await api.getJob(activeJob.job_id);
          setActiveJob(updatedJob);

          // Update page thumbnails progressively
          const updatedPages = await api.listPages(project.id);
          setPages(updatedPages);
        } catch (e) {
          console.error("Job poll error:", e);
        }
      }
    }, 1000);

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [activeJob?.status]);

  const isJobActive = activeJob?.status === "RUNNING" || activeJob?.status === "QUEUED";
  const failedPagesCount = pages.filter((p) => p.status === "FAILED").length;
  const readyPagesCount = pages.filter((p) => p.status === "READY").length;

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      {/* Top Navigation & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <Icons.ArrowLeft className="w-4 h-4" />
            Projects
          </Button>
          <div>
            <h2 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
              {project.title}
            </h2>
            <div className="flex items-center gap-2 text-xs text-zinc-400 mt-0.5">
              <span>Source: {project.source_type}</span>
              <span>•</span>
              <Badge variant="success">{project.rights_status}</Badge>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={handleOpenFolder}>
            <Icons.Folder className="w-4 h-4" />
            Open Source Folder
          </Button>

          {pages.length > 0 && readyPagesCount > 0 && (
            <Button variant="primary" size="sm" onClick={onReviewPages}>
              Review Pages ({readyPagesCount})
              <Icons.ArrowRight className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Main Status & Control Card */}
      <Card className="space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-zinc-300">Acquisition Pipeline</span>
            {activeJob ? (
              <Badge
                variant={
                  activeJob.status === "SUCCEEDED"
                    ? "success"
                    : activeJob.status === "FAILED"
                    ? "danger"
                    : activeJob.status === "CANCELLED"
                    ? "warning"
                    : "accent"
                }
              >
                {activeJob.status}
              </Badge>
            ) : (
              <Badge variant="neutral">READY TO START</Badge>
            )}
          </div>

          <div className="text-xs text-zinc-400">
            {pages.length > 0 ? (
              <span>
                <strong className="text-zinc-100">{readyPagesCount}</strong> / {pages.length} pages downloaded
              </span>
            ) : null}
          </div>
        </div>

        {/* Progress Bar */}
        {activeJob && (
          <ProgressBar
            progress={activeJob.progress}
            label={activeJob.message || "Processing assets..."}
          />
        )}

        {/* Error Notification */}
        {errorMsg && (
          <div className="p-3 bg-rose-950/50 border border-rose-800 rounded-lg text-xs text-rose-200 flex items-center gap-2">
            <Icons.XCircle className="w-4 h-4 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-3 pt-2">
          {!activeJob || activeJob.status === "FAILED" || activeJob.status === "CANCELLED" ? (
            <Button variant="primary" size="md" onClick={startJob} loading={isStarting}>
              <Icons.Rotate className="w-4 h-4" />
              {activeJob ? "Restart Acquisition" : "Start Acquisition"}
            </Button>
          ) : null}

          {isJobActive && (
            <Button variant="destructive" size="md" onClick={handleCancel} loading={cancelling}>
              Cancel Acquisition
            </Button>
          )}

          {failedPagesCount > 0 && !isJobActive && (
            <Button variant="secondary" size="md" onClick={handleRetryFailed} loading={retrying}>
              <Icons.Refresh className="w-4 h-4" />
              Retry Failed Pages ({failedPagesCount})
            </Button>
          )}

          {activeJob?.status === "SUCCEEDED" && (
            <Button variant="primary" size="md" onClick={onReviewPages}>
              Proceed to Page Review
              <Icons.ArrowRight className="w-4 h-4" />
            </Button>
          )}
        </div>
      </Card>

      {/* Progressive Live Thumbnails View */}
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs text-zinc-400 px-1">
          <span className="font-semibold uppercase tracking-wider text-zinc-300">
            Acquired Pages ({pages.length})
          </span>
          {failedPagesCount > 0 && (
            <span className="text-rose-400 font-medium">
              {failedPagesCount} failed page{failedPagesCount > 1 ? "s" : ""}
            </span>
          )}
        </div>

        {pages.length === 0 ? (
          <Card className="text-center py-12 text-zinc-500 text-sm border-dashed">
            No pages acquired yet. Click &quot;Start Acquisition&quot; to begin downloading and validating assets.
          </Card>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {pages.map((p) => {
              const isFailed = p.status === "FAILED";
              return (
                <div
                  key={p.id}
                  className={`group relative rounded-xl border overflow-hidden bg-zinc-900 transition-all ${
                    isFailed
                      ? "border-rose-800 bg-rose-950/20"
                      : "border-zinc-800 hover:border-indigo-500/60"
                  }`}
                >
                  <div className="aspect-[3/4] w-full bg-zinc-950 flex items-center justify-center overflow-hidden">
                    {isFailed ? (
                      <div className="p-3 text-center space-y-1">
                        <Icons.AlertTriangle className="w-6 h-6 text-rose-500 mx-auto" />
                        <span className="text-[10px] text-rose-300 block line-clamp-3">
                          {p.error_message || "Validation Error"}
                        </span>
                      </div>
                    ) : (
                      <img
                        src={api.getPageImageUrl(project.id, p.id)}
                        alt={`Page ${p.sequence}`}
                        className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-200"
                        loading="lazy"
                      />
                    )}
                  </div>

                  <div className="p-2 bg-zinc-900/90 border-t border-zinc-800/80 flex items-center justify-between text-[11px]">
                    <span className="font-semibold text-zinc-200">#{p.sequence}</span>
                    {isFailed ? (
                      <Badge variant="danger" className="text-[9px] px-1.5 py-0">FAILED</Badge>
                    ) : (
                      <span className="text-zinc-500">{p.width}x{p.height}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
