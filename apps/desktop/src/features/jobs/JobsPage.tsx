import React from "react";
import type { Job } from "@panelflow/shared-types";
import { EmptyState, ErrorState, GlassPanel, PageHeader, Skeleton, Tabs } from "@panelflow/ui-v2";
import { useCancelJob, useJobs, useProjects, useRetryJob } from "../data/queries";
import { JobDetailsDrawer } from "./JobDetailsDrawer";
import { JobRow } from "./JobRow";
import { groupJobs, type JobTab } from "./jobsView";

const EMPTY_TAB: Record<JobTab, { title: string; description: string }> = {
  active: { title: "No jobs are running.", description: "Start a pipeline stage and its progress shows up here." },
  failed: { title: "Nothing has failed.", description: "Jobs that fail or are cancelled appear here with a way to retry them." },
  done: { title: "No finished jobs yet.", description: "Completed jobs are listed here." },
};

export const JobsPage: React.FC = () => {
  const jobs = useJobs();
  const projects = useProjects();
  const retry = useRetryJob();
  const cancel = useCancelJob();
  const [tab, setTab] = React.useState<JobTab>("active");
  const [selected, setSelected] = React.useState<Job | null>(null);
  const [busy, setBusy] = React.useState<ReadonlySet<string>>(new Set());
  const inFlight = React.useRef(new Set<string>()); // set synchronously so a fast double click cannot submit twice

  const titles = React.useMemo(() => new Map((projects.data ?? []).map((p) => [p.id, p.title])), [projects.data]);
  const groups = React.useMemo(() => groupJobs(jobs.data ?? []), [jobs.data]);

  const run = async (jobId: string, action: (id: string) => Promise<unknown>) => {
    if (inFlight.current.has(jobId)) return;
    inFlight.current.add(jobId);
    setBusy(new Set(inFlight.current));
    try {
      await action(jobId);
    } finally {
      inFlight.current.delete(jobId);
      setBusy(new Set(inFlight.current));
    }
  };

  const running = groups.active.filter((j) => j.status === "RUNNING").length;
  const waiting = groups.active.length - running;
  const list = groups[tab];

  let body: React.ReactNode;
  if (jobs.isError) {
    body = <ErrorState title="Couldn't load jobs" description="Check that the engine is running, then try again." onRetry={() => void jobs.refetch()} />;
  } else if (jobs.isLoading || !jobs.data) {
    body = <div className="grid gap-2"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>;
  } else if (jobs.data.length === 0) {
    body = <EmptyState title="No jobs yet. Start a pipeline stage and it shows up here." />;
  } else if (list.length === 0) {
    body = <EmptyState {...EMPTY_TAB[tab]} />;
  } else {
    body = (
      <div className="grid gap-2">
        {list.map((job) => (
          <JobRow
            key={job.job_id}
            job={job}
            projectTitle={titles.get(job.project_id) ?? "Unknown project"}
            busy={busy.has(job.job_id)}
            onOpen={() => setSelected(job)}
            onRetry={() => void run(job.job_id, retry.mutateAsync)}
            onCancel={() => void run(job.job_id, cancel.mutateAsync)}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-5 p-6 md:p-8">
      <PageHeader title="Jobs" meta={<span>{`${running} running, ${waiting} waiting`}</span>} />
      <GlassPanel className="p-4">
        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as JobTab)}
          tabs={[
            { value: "active", label: `Active ${groups.active.length}` },
            { value: "failed", label: `Failed ${groups.failed.length}` },
            { value: "done", label: `Done ${groups.done.length}` },
          ]}
        >
          {body}
        </Tabs>
      </GlassPanel>
      <JobDetailsDrawer job={selected} projectTitle={selected ? titles.get(selected.project_id) ?? "Unknown project" : ""} open={selected !== null} onOpenChange={(open) => { if (!open) setSelected(null); }} />
    </div>
  );
};
