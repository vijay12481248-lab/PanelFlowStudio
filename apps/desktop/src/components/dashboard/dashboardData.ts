import type { api } from "@panelflow/api-client";
import type { Project, Job, SystemResourcesResponse } from "@panelflow/shared-types";

type DashboardClient = Pick<typeof api, "listProjects" | "listAllJobs" | "getSystemResources" | "listPages" | "getPageImageUrl">;
interface DashboardUpdates {
  projects: (projects: Project[]) => void;
  jobs: (jobs: Job[]) => void;
  resources: (resources: SystemResourcesResponse) => void;
  cover: (projectId: string, url: string | undefined) => void;
  loading: (loading: boolean) => void;
  error: (message: string | null) => void;
}

// Projects are the critical path. Telemetry and cover requests publish independently.
// A slow stream cannot block another stream's first load or its subsequent polls.
export function createDashboardLoader(client: DashboardClient, updates: DashboardUpdates) {
  let disposed = false;
  const pending = new Map<string, Promise<void>>();
  const versions = new Map<string, string>();
  const loadedCovers = new Map<string, string>();
  const removed = new Set<string>();

  function run(key: string, task: () => Promise<void>): Promise<void> {
    if (disposed) return Promise.resolve();
    const existing = pending.get(key);
    if (existing) return existing;
    const request = Promise.resolve().then(task).finally(() => {
      if (pending.get(key) === request) pending.delete(key);
    });
    pending.set(key, request);
    return request;
  }

  function loadCover(project: Project) {
    const version = `${project.updated_at}:${project.total_pages}`;
    versions.set(project.id, version);
    if (loadedCovers.get(project.id) === version) return;
    void run(`cover:${project.id}`, async () => {
      try {
        const pages = await client.listPages(project.id);
        if (disposed || removed.has(project.id) || versions.get(project.id) !== version) return;
        const first = pages.find((page) => page.sequence === 1) || pages[0];
        updates.cover(project.id, first ? client.getPageImageUrl(project.id, first.id) : undefined);
        loadedCovers.set(project.id, version);
      } catch { /* A failed optional cover is retried on the next project refresh. */ }
    });
  }

  return {
    refresh(ready: boolean): Promise<void> {
      if (!ready || disposed) return Promise.resolve();
      void run("jobs", async () => {
        try {
          const jobs = await client.listAllJobs(undefined, undefined, 40);
          if (!disposed) updates.jobs(jobs);
        } catch { /* Keep the last successful job snapshot. */ }
      });
      void run("resources", async () => {
        try {
          const resources = await client.getSystemResources();
          if (!disposed) updates.resources(resources);
        } catch { /* Optional telemetry must never hide project cards. */ }
      });
      return run("projects", async () => {
        try {
          const projects = (await client.listProjects()).filter((project) => !removed.has(project.id));
          if (disposed) return;
          updates.projects(projects);
          updates.error(null);
          // Display the cards before any page inventory or image request completes.
          updates.loading(false);
          for (const project of projects) loadCover(project);
        } catch {
          if (!disposed) updates.error("Could not load projects. Check the engine connection and retry.");
        } finally {
          if (!disposed) updates.loading(false);
        }
      });
    },
    removeProject(projectId: string) {
      removed.add(projectId);
      versions.delete(projectId);
      loadedCovers.delete(projectId);
    },
    dispose() {
      disposed = true;
    },
  };
}
