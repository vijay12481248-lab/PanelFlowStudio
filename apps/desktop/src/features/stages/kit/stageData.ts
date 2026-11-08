import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Job, Page } from "@panelflow/shared-types";
import { useEngine } from "../../../app/providers";

export const stageKeys = {
  pages: (projectId: string) => ["stages", "pages", projectId] as const,
  jobs: (projectId: string) => ["stages", "jobs", projectId] as const,
  job: (jobId: string) => ["stages", "job", jobId] as const,
};

export const isActiveJob = (job: Job | null | undefined) => job?.status === "RUNNING" || job?.status === "QUEUED";

/** A project's pages. Polls every second only while `pollWhileActive` is true (an acquisition is running). */
export function usePages(projectId: string, pollWhileActive = false) {
  const { connected } = useEngine();
  return useQuery<Page[]>({
    queryKey: stageKeys.pages(projectId),
    queryFn: () => api.listPages(projectId),
    enabled: connected,
    retry: 1,
    refetchInterval: pollWhileActive ? 1000 : false,
  });
}

/** A project's jobs, newest first. Polls while the newest one is running or waiting. */
export function useProjectJobs(projectId: string) {
  const { connected } = useEngine();
  return useQuery<Job[]>({
    queryKey: stageKeys.jobs(projectId),
    queryFn: () => api.listProjectJobs(projectId),
    enabled: connected,
    retry: 1,
    refetchInterval: (query) => (isActiveJob(query.state.data?.[0]) ? 1500 : false),
  });
}

/** One job by id, polled every second while it is running or waiting. */
export function useJob(jobId: string | undefined) {
  const { connected } = useEngine();
  return useQuery<Job>({
    queryKey: stageKeys.job(jobId ?? ""),
    queryFn: () => api.getJob(jobId as string),
    enabled: connected && Boolean(jobId),
    retry: 1,
    refetchInterval: (query) => (isActiveJob(query.state.data) ? 1000 : false),
  });
}
