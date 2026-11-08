import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Job } from "@panelflow/shared-types";
import { isActiveJob, stageKeys, useJob, useProjectJobs } from "./stageData";

export interface FollowedJobOptions {
  projectId: string;
  /** Job types this stage owns. One of them already running when the stage opens is followed, not restarted. */
  types: string[];
  /** Called once when a followed job reaches an end state (succeeded, failed or cancelled). */
  onDone: (job: Job) => void;
}

/**
 * Follow one long job at a time through React Query: the job a person started (`follow(id)`) or one already running when the
 * stage opened. There is no local time limit; the job is over when the engine says so. Polling stops with the component.
 */
export function useFollowedJob({ projectId, types, onDone }: FollowedJobOptions) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = React.useState<string | undefined>();
  const handled = React.useRef(new Set<string>());
  const done = React.useRef(onDone);
  done.current = onDone;

  const jobs = useProjectJobs(projectId);
  const running = jobs.data?.find((j) => types.includes(j.job_type) && isActiveJob(j) && !handled.current.has(j.job_id));
  React.useEffect(() => { if (!jobId && running) setJobId(running.job_id); }, [jobId, running?.job_id, running?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const job = useJob(jobId);
  React.useEffect(() => {
    const finished = job.data;
    if (!jobId || !finished || isActiveJob(finished)) return;
    handled.current.add(jobId);
    setJobId(undefined);
    void queryClient.invalidateQueries({ queryKey: stageKeys.jobs(projectId) });
    done.current(finished);
  }, [jobId, job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    /** The followed job's id, while one is running. */
    jobId,
    job: job.data,
    active: jobId !== undefined,
    follow: (id: string) => setJobId(id),
    /** The engine could not be reached while following. */
    lost: job.isError,
    check: () => void job.refetch(),
  };
}
