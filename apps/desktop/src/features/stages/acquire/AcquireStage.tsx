import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FolderOpen } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { Button, EmptyState, ErrorState, GlassPanel, Skeleton } from "@panelflow/ui-v2";
import { useError } from "../../../context/ErrorContext";
import { StageToolbar } from "../kit/StageToolbar";
import { PageThumb } from "../kit/PageThumb";
import { JobProgress } from "../kit/JobProgress";
import { isActiveJob, stageKeys, useJob, usePages, useProjectJobs } from "../kit/stageData";
import { acquireActions, acquirePhase, latestAcquisitionJob, pageCounts } from "./acquireModel";

export interface AcquireStageProps {
  project: Project;
  onReviewPages: () => void;
}

/** Acquire: download and check the source pages. Starting, cancelling and retrying are guarded against double clicks. */
export const AcquireStage: React.FC<AcquireStageProps> = ({ project, onReviewPages }) => {
  const queryClient = useQueryClient();
  const { reportError } = useError();
  const jobs = useProjectJobs(project.id);
  const [followedId, setFollowedId] = React.useState<string | undefined>();
  const latest = latestAcquisitionJob(jobs.data);
  const jobId = followedId ?? latest?.job_id;
  const followed = useJob(jobId);
  const job = followed.data ?? (followedId ? null : latest);
  const phase = acquirePhase(job);
  const active = isActiveJob(job);
  const pages = usePages(project.id, active);
  const counts = pageCounts(pages.data ?? []);
  const actions = acquireActions(phase, counts);
  const [error, setError] = React.useState<string | null>(null);
  const busy = React.useRef(false); // one start, cancel or retry at a time, even on a fast double click
  const [working, setWorking] = React.useState<"start" | "cancel" | "retry" | null>(null);

  // When a job ends, the page list and job list change once more.
  const lastStatus = React.useRef<string | undefined>(undefined);
  React.useEffect(() => {
    if (lastStatus.current && lastStatus.current !== job?.status && !active) {
      void queryClient.invalidateQueries({ queryKey: stageKeys.pages(project.id) });
      void queryClient.invalidateQueries({ queryKey: stageKeys.jobs(project.id) });
    }
    lastStatus.current = job?.status;
  }, [job?.status, active, project.id, queryClient]);

  const guarded = async (kind: "start" | "cancel" | "retry", run: () => Promise<void>) => {
    if (busy.current) return;
    busy.current = true;
    setWorking(kind);
    setError(null);
    try { await run(); } finally { busy.current = false; setWorking(null); }
  };

  /** Follow a job the engine just created: seed its cache so the status shows at once. */
  const follow = async (id: string) => {
    const created = await api.getJob(id);
    queryClient.setQueryData(stageKeys.job(id), created);
    setFollowedId(id);
    void queryClient.invalidateQueries({ queryKey: stageKeys.jobs(project.id) });
  };

  const start = () => guarded("start", async () => {
    try { await follow((await api.startAcquisition(project.id)).job_id); }
    catch { setError("Couldn't start acquisition. Check that the engine is running, then try again."); }
  });

  const cancel = () => guarded("cancel", async () => {
    if (!job) return;
    try {
      await api.cancelJob(job.job_id);
      queryClient.setQueryData(stageKeys.job(job.job_id), await api.getJob(job.job_id));
    } catch (err: any) {
      setError("Couldn't cancel the acquisition. Try again in a moment.");
      reportError({ title: "Cancel Job Failed", message: "Failed to cancel acquisition job.", severity: "warning", source: "pipeline", projectId: project.id, jobId: job.job_id, rawDetails: err });
    }
  });

  const retry = () => guarded("retry", async () => {
    try { await follow((await api.retryFailedPages(project.id)).job_id); }
    catch (err: any) {
      setError("Couldn't retry the failed pages. Check that the engine is running, then try again.");
      reportError({ title: "Page Download Retry Failed", message: "Failed to retry pages.", severity: "error", source: "pipeline", projectId: project.id, jobType: "ACQUISITION", rawDetails: err });
    }
  });

  const openFolder = async () => {
    try { await api.openProjectFolder(project.id); }
    catch (err: any) {
      reportError({ title: "Could Not Open Folder", message: "Failed to open project directory.", severity: "warning", source: "system", projectId: project.id, rawDetails: err });
    }
  };

  if (pages.isError) {
    return <ErrorState title="Couldn't load the pages" description="Check that the engine is running, then try again." onRetry={() => void pages.refetch()} />;
  }

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Acquire pages"
        description="Download the source pages and check each one before you review them."
        actions={
          <>
            <Button variant="secondary" size="sm" icon={<FolderOpen size={14} />} onClick={() => void openFolder()}>Open source folder</Button>
            {actions.review && (
              <Button variant={phase === "succeeded" ? "primary" : "secondary"} size="sm" onClick={onReviewPages}>{`Review pages (${counts.ready})`}</Button>
            )}
          </>
        }
      />

      <GlassPanel blur={false} className="grid grid-cols-1 gap-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-display text-sm font-semibold text-fg">Download</h3>
          {counts.total > 0 && <p className="text-sm text-fg-dim">{`${counts.ready} of ${counts.total} pages downloaded`}</p>}
        </div>
        <JobProgress job={job} idleLabel="Not started yet." />
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <div className="flex flex-wrap items-center gap-3">
          {actions.start && <Button variant="primary" loading={working === "start"} onClick={() => void start()}>{actions.start}</Button>}
          {actions.cancel && <Button variant="danger" loading={working === "cancel"} onClick={() => void cancel()}>Cancel acquisition</Button>}
          {actions.retryFailed !== null && (
            <Button variant="secondary" loading={working === "retry"} onClick={() => void retry()}>{`Retry failed pages (${actions.retryFailed})`}</Button>
          )}
        </div>
      </GlassPanel>

      <section className="grid grid-cols-1 gap-3" aria-label="Acquired pages">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-sm font-semibold text-fg">{`Pages (${counts.total})`}</h3>
          {counts.failed > 0 && <p className="text-sm font-medium text-bad">{`${counts.failed} failed`}</p>}
        </div>
        {!pages.data ? (
          <Skeleton className="h-40" />
        ) : pages.data.length === 0 ? (
          <GlassPanel blur={false}>
            <EmptyState
              title="No pages yet"
              description={active ? "Downloading. Pages appear here as each one is checked." : "Start acquisition to download the pages and check each one."}
            />
          </GlassPanel>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {pages.data.map((p) => (
              <div key={p.id} className="grid gap-1">
                <PageThumb
                  src={api.getPageImageUrl(project.id, p.id)}
                  label={`Page ${p.sequence}`}
                  failed={p.status === "FAILED"}
                  reason={p.status === "FAILED" ? p.error_message : null}
                />
                <p className="text-xs text-fg-faint">{`#${p.sequence}${p.status === "READY" ? ` · ${p.width}×${p.height}` : ""}`}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
