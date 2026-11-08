import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { ChronoFlowJobSummary, OriginalSeries, OriginalStorySummary } from "@panelflow/api-client";
import type { Job, Project, SystemResourcesResponse } from "@panelflow/shared-types";
import { useError } from "../../context/ErrorContext";
import { useEngine } from "../../app/providers";

export const queryKeys = {
  projects: ["projects"],
  jobs: ["jobs"],
  resources: ["resources"],
  cover: (projectId: string, version: string) => ["cover", projectId, version],
  series: ["original-series"],
  creations: ["creations"],
} as const;

const SLOW_POLL_MS = 8000;
const BUSY_POLL_MS = 3000;

/** Poll quickly while the engine is working so progress feels live, slowly otherwise. */
export function jobsPollInterval(jobs: Job[] | undefined): number {
  return jobs?.some((job) => job.status === "RUNNING" || job.status === "QUEUED") ? BUSY_POLL_MS : SLOW_POLL_MS;
}

/** A project's cover only changes when its pages do. */
export function coverVersion(project: Pick<Project, "updated_at" | "total_pages">): string {
  return `${project.updated_at}:${project.total_pages}`;
}

export function useProjects() {
  const { connected } = useEngine();
  return useQuery({ queryKey: queryKeys.projects, queryFn: () => api.listProjects(), enabled: connected, refetchInterval: SLOW_POLL_MS, retry: 1 });
}

export function useJobs(limit = 200) {
  const { connected } = useEngine();
  return useQuery({
    queryKey: queryKeys.jobs,
    queryFn: () => api.listAllJobs(undefined, undefined, limit),
    enabled: connected,
    refetchInterval: (query) => jobsPollInterval(query.state.data as Job[] | undefined),
    retry: 1,
  });
}

export function useResources() {
  const { connected } = useEngine();
  return useQuery<SystemResourcesResponse>({ queryKey: queryKeys.resources, queryFn: () => api.getSystemResources(), enabled: connected, refetchInterval: SLOW_POLL_MS, retry: 1 });
}

export function useOriginalSeries() {
  const { connected } = useEngine();
  return useQuery<OriginalSeries[]>({ queryKey: queryKeys.series, queryFn: () => api.listOriginalSeries(), enabled: connected, refetchInterval: 30_000, retry: 1 });
}

/** Original Stories and ChronoFlow videos are files, not project rows. A ChronoFlow job with no clip yet has nothing to open. */
export function useCreations(): { stories: OriginalStorySummary[]; chronoJobs: ChronoFlowJobSummary[]; failed: boolean } {
  const { connected } = useEngine();
  const query = useQuery({
    queryKey: queryKeys.creations,
    enabled: connected,
    retry: 1,
    queryFn: async () => {
      const [stories, chrono] = await Promise.allSettled([api.listOriginalStories(), api.listChronoFlowJobs()]);
      return {
        stories: stories.status === "fulfilled" ? stories.value : [],
        chronoJobs: chrono.status === "fulfilled" ? chrono.value.filter((job) => (job.chunks ?? []).some(Boolean) || job.master_video) : [],
        failed: stories.status === "rejected" || chrono.status === "rejected",
      };
    },
  });
  return query.data ?? { stories: [], chronoJobs: [], failed: false };
}

/** One small query per project; a failed cover is simply absent and the tile shows initials. */
export function useProjectCovers(projects: Project[]): Record<string, string | undefined> {
  const { connected } = useEngine();
  const results = useQueries({
    queries: projects.map((project) => ({
      queryKey: queryKeys.cover(project.id, coverVersion(project)),
      enabled: connected,
      staleTime: Infinity,
      retry: false,
      queryFn: async () => {
        const pages = await api.listPages(project.id);
        const first = pages.find((page) => page.sequence === 1) ?? pages[0];
        return first ? api.getPageImageUrl(project.id, first.id) : null;
      },
    })),
  });
  return Object.fromEntries(projects.map((project, index) => [project.id, results[index]?.data ?? undefined]));
}

/** Retry and cancel reuse the app's ErrorContext handlers, which check the job's state first and report failures in words. */
export function useRetryJob() {
  const { retryJob } = useError();
  const queryClient = useQueryClient();
  return useMutation<boolean, Error, string>({
    mutationFn: (jobId) => retryJob(jobId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.jobs }),
  });
}

export function useCancelJob() {
  const { cancelJob } = useError();
  const queryClient = useQueryClient();
  return useMutation<boolean, Error, string>({
    mutationFn: (jobId) => cancelJob(jobId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.jobs }),
  });
}
