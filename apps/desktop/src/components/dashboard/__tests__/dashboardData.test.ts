import test from "node:test";
import assert from "node:assert/strict";
import { createDashboardLoader } from "../dashboardData";
import type { Project, Page, SystemResourcesResponse } from "@panelflow/shared-types";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
const project: Project = { id: "test-project", title: "Saved project", source_type: "LOCAL_FOLDER", source_url: null, source_metadata: {}, rights_status: "UNKNOWN", license_info: "", workspace_path: "test", current_stage: "NEW", settings: {}, created_at: "2026-10-20", updated_at: "2026-10-20", total_pages: 1, ready_pages: 1, failed_pages: 0 };
const flush = () => new Promise((resolve) => setImmediate(resolve));
function setup(overrides = {}) {
  const state = { projects: [] as Project[], covers: {} as Record<string, string | undefined>, loading: true, error: null as string | null, publications: 0 };
  const client = {
    listProjects: async () => [project], listAllJobs: async () => [],
    getSystemResources: async () => ({} as SystemResourcesResponse), listPages: async () => [] as Page[],
    getPageImageUrl: (id: string, page: string) => `image:${id}/${page}`, ...overrides,
  };
  const loader = createDashboardLoader(client, {
    projects: (value: Project[]) => { state.projects = value; state.publications++; },
    jobs: () => {}, resources: () => {}, cover: (id: string, url: string | undefined) => { state.covers[id] = url; },
    loading: (value: boolean) => { state.loading = value; }, error: (value: string | null) => { state.error = value; },
  });
  return { state, client, loader };
}

test("dashboard makes no authenticated requests until the engine is ready", async () => {
  let calls = 0;
  const { loader } = setup({ listProjects: async () => { calls++; return [project]; }, listAllJobs: async () => { calls++; return []; }, getSystemResources: async () => { calls++; return {}; } });
  await loader.refresh(false);
  assert.equal(calls, 0);
  await loader.refresh(true);
  assert.equal(calls, 3);
  loader.dispose();
});

test("projects publish before stalled telemetry, jobs and covers finish", async () => {
  const slow = deferred<never>();
  const { loader, state } = setup({ listAllJobs: () => slow.promise, getSystemResources: () => slow.promise, listPages: () => slow.promise });
  await loader.refresh(true);
  assert.deepEqual(state.projects, [project]);
  assert.equal(state.loading, false);
  assert.deepEqual(state.covers, {});
  await loader.refresh(true); // Slow optional requests must not block the next project refresh either.
  assert.equal(state.publications, 2);
  loader.dispose();
});

test("failed project refresh retains loaded projects and exposes a recoverable error", async () => {
  let failed = false;
  const { loader, state } = setup({ listProjects: async () => { if (failed) throw new Error("private backend details"); return [project]; } });
  await loader.refresh(true);
  failed = true;
  await loader.refresh(true);
  assert.deepEqual(state.projects, [project]);
  assert.match(state.error!, /Could not load projects/);
  assert.doesNotMatch(state.error!, /private backend/);
  failed = false;
  await loader.refresh(true);
  assert.equal(state.error, null);
  loader.dispose();
});

test("polling coalesces in-flight project requests and disposal rejects late publication", async () => {
  const pending = deferred<Project[]>();
  let calls = 0;
  const { loader, state } = setup({ listProjects: () => { calls++; return pending.promise; } });
  const first = loader.refresh(true); const second = loader.refresh(true);
  await flush();
  assert.equal(calls, 1);
  loader.dispose();
  pending.resolve([project]);
  await Promise.all([first, second]);
  assert.equal(state.publications, 0);
});

test("cover lookups are cached until project revision changes", async () => {
  let calls = 0;
  const { loader, state } = setup({ listPages: async () => { calls++; return [{ id: "first-page", sequence: 1 }] as Page[]; } });
  await loader.refresh(true); await flush();
  await loader.refresh(true); await flush();
  assert.equal(calls, 1);
  assert.equal(state.covers[project.id], "image:test-project/first-page");
  loader.dispose();
});

test("deleted projects cannot reappear from an older in-flight list response", async () => {
  const pending = deferred<Project[]>();
  const { loader, state } = setup({ listProjects: () => pending.promise });
  const request = loader.refresh(true);
  loader.removeProject(project.id);
  pending.resolve([project]);
  await request;
  assert.deepEqual(state.projects, []);
  loader.dispose();
});
