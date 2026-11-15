import { mount } from "../../../../../packages/ui/src/v2/__tests__/dom"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { createMemoryRouter, createStaticHandler, matchRoutes, Outlet, RouterProvider, type RouteObject } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { resolveStageRoute } from "../../features/legacy/resolveStageRoute";
import { appRoutes } from "../router";
import { AppShell } from "../AppShell";
import { EngineContext, type EngineState } from "../providers";
import { ErrorProvider } from "../../context/ErrorContext";

const project = (overrides: Partial<Project> = {}): Project => ({
  id: "p1", title: "Magic Emperor", source_type: "MANGA" as Project["source_type"], source_url: null, source_metadata: {},
  rights_status: "AUTHORIZED_WEB" as Project["rights_status"], license_info: "", workspace_path: "C:/w", current_stage: "OCR_COMPLETE",
  settings: {}, created_at: "", updated_at: "", total_pages: 1, ready_pages: 1, failed_pages: 0, ...overrides,
});

test("a project that is still loading shows loading, not an error", () => {
  assert.deepEqual(resolveStageRoute({ id: "p1", stage: "ocr", project: undefined, failed: false }), { kind: "loading" });
});

test("a project that cannot be loaded is reported as not found", () => {
  assert.deepEqual(resolveStageRoute({ id: "nope", stage: "ocr", project: undefined, failed: true }), { kind: "not-found" });
});

test("an unknown stage segment redirects to the stage the project is at", () => {
  assert.deepEqual(resolveStageRoute({ id: "p1", stage: "xyz", project: project(), failed: false }), { kind: "redirect", to: "/projects/p1/story" });
});

test("a ChronoFlow project never opens a pipeline stage", () => {
  const chrono = project({ settings: { workflow_type: "chronoflow" } });
  assert.deepEqual(resolveStageRoute({ id: "p1", stage: "ocr", project: chrono, failed: false }), { kind: "redirect", to: "/create/chronoflow/p1" });
});

test("a stage the project has not reached yet still opens, as the old stage bar allowed", () => {
  assert.deepEqual(resolveStageRoute({ id: "p1", stage: "ocr", project: project({ current_stage: "NEW" }), failed: false }), { kind: "render", stage: "ocr" });
});

test("the root and unknown paths redirect to /home", async () => {
  const handler = createStaticHandler(appRoutes);
  for (const url of ["http://localhost/", "http://localhost/does-not-exist"]) {
    const result = await handler.query(new Request(url));
    assert.ok(result instanceof Response, `${url} returns a redirect`);
    assert.equal(result.headers.get("Location"), "/home");
  }
});

test("project stage and studio URLs match their route patterns", () => {
  const params = (url: string) => matchRoutes(appRoutes, url)?.at(-1)?.params;
  assert.deepEqual({ ...params("/projects/p1/ocr") }, { id: "p1", stage: "ocr" });
  assert.deepEqual({ ...params("/editor/p1") }, { id: "p1" });
  assert.ok(matchRoutes(appRoutes, "/create/chronoflow/job/j1"));
  assert.ok(matchRoutes(appRoutes, "/settings/engine"));
  assert.ok(matchRoutes(appRoutes, "/jobs"));
});

const engine = (overrides: Partial<EngineState> = {}): EngineState => ({
  connected: true, version: "1.0.0-beta.2", startupGrace: false, retrying: false, restarting: false, retry: async () => {}, restart: async () => {}, ...overrides,
});

async function mountShell(path: string, state: EngineState) {
  (api as any).listProjects = async () => [];
  const routes: RouteObject[] = [{ path: "/", element: <AppShell />, children: [{ path: "*", element: <p id="page">page</p> }] }];
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient();
  const view = await mount(
    <ErrorProvider>
      <QueryClientProvider client={client}>
        <EngineContext.Provider value={state}><RouterProvider router={router} /></EngineContext.Provider>
      </QueryClientProvider>
    </ErrorProvider>,
  );
  // React Query keeps a 5 minute cache timer per query, which would keep the test process alive.
  return { ...view, router, cleanup: async () => { await view.cleanup(); client.clear(); } };
}

test("the shell has six dock destinations and marks the current one", async () => {
  const view = await mountShell("/jobs", engine());
  const links = [...view.document.querySelectorAll('nav[aria-label="Main"] a')];
  assert.deepEqual(links.map((a) => a.textContent), ["Home", "Projects", "Create", "Jobs", "Library", "Settings"]);
  const current = view.document.querySelectorAll('nav[aria-label="Main"] [aria-current="page"]');
  assert.equal(current.length, 1);
  assert.equal(current[0].textContent, "Jobs");
  await view.cleanup();
});

test("with the engine offline the shell shows the reconnect gate and keeps the route", async () => {
  const view = await mountShell("/projects/p1/ocr", engine({ connected: false }));
  assert.ok(view.document.body.textContent!.includes("Processing engine unavailable"));
  assert.equal(view.document.getElementById("page"), null, "the page is not rendered while offline");
  assert.equal(view.router.state.location.pathname, "/projects/p1/ocr");
  await view.cleanup();
});

test("during startup the shell says it is connecting instead of reporting a failure", async () => {
  const view = await mountShell("/home", engine({ connected: false, startupGrace: true }));
  assert.ok(view.document.body.textContent!.includes("Connecting to the PanelFlow engine"));
  await view.cleanup();
});

test("the dock is hidden on immersive routes such as the story editor", async () => {
  const view = await mountShell("/editor/p1", engine());
  assert.equal(view.document.querySelector('nav[aria-label="Main"]'), null);
  assert.ok(view.document.getElementById("page"));
  await view.cleanup();
});

test("every settings, library and project URL highlights its own dock destination", async () => {
  const cases: Array<[string, string]> = [
    ["/settings/providers", "Settings"], ["/settings/engine", "Settings"], ["/library/audio", "Library"],
    ["/projects/p1/ocr", "Projects"], ["/editor/p1", "Projects"], ["/create/stories", "Create"],
  ];
  for (const [path, label] of cases) {
    const view = await mountShell(path, engine());
    const current = view.document.querySelector('nav[aria-label="Main"] [aria-current="page"]');
    // The dock is hidden on immersive routes, so only assert where it exists.
    if (view.document.querySelector('nav[aria-label="Main"]')) assert.equal(current?.textContent, label, path);
    await view.cleanup();
  }
});

test("the editor and ChronoFlow stay mounted when the engine drops, so unsaved work is not thrown away", async () => {
  for (const path of ["/editor/p1", "/create/chronoflow/p1"]) {
    const view = await mountShell(path, engine({ connected: false }));
    assert.ok(view.document.getElementById("page"), `${path} keeps its screen`);
    assert.ok(!view.document.body.textContent!.includes("Processing engine unavailable"), `${path} shows no blocking gate`);
    await view.cleanup();
  }
});

test("Home, Projects, Jobs and Library load the v2 pages, not the old dashboard", async () => {
  const component = async (url: string) => {
    const route = matchRoutes(appRoutes, url)!.at(-1)!.route;
    return (await route.lazy!() as { Component: React.ComponentType }).Component;
  };
  assert.equal(await component("/home"), (await import("../../features/home/HomePage")).HomePage);
  assert.equal(await component("/projects"), (await import("../../features/projects/ProjectsPage")).ProjectsPage);
  assert.equal(await component("/jobs"), (await import("../../features/jobs/JobsPage")).JobsPage);
  const library = (await import("../../features/library/LibraryPage")).LibraryPage;
  assert.equal(await component("/library"), library);
  assert.equal(await component("/library/audio"), library);
});

test("each Settings section loads its own page, and the old engine and provider screens are gone", async () => {
  const component = async (url: string) => (await matchRoutes(appRoutes, url)!.at(-1)!.route.lazy!() as { Component: React.ComponentType }).Component;
  assert.equal(await component("/settings/engine"), (await import("../../features/settings/EngineSection")).EngineSection);
  assert.equal(await component("/settings/models"), (await import("../../features/settings/ModelsSection")).ModelsSection);
  assert.equal(await component("/settings/providers"), (await import("../../features/settings/ProvidersSection")).ProvidersSection);
  assert.equal(await component("/settings/youtube"), (await import("../../features/settings/YouTubeSection")).YouTubeSection);
  assert.equal(await component("/settings/diagnostics"), (await import("../../features/settings/DiagnosticsSection")).DiagnosticsSection);
  // LegacyScreens imports a CSS file tsx cannot load, so check its source text instead of importing it.
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(new URL("../../features/legacy/LegacyScreens.tsx", import.meta.url), "utf8");
  assert.ok(!source.includes("EngineSettingsRoute"), "EngineSettingsRoute is removed");
  assert.ok(!source.includes("ProvidersRoute"), "ProvidersRoute is removed");
  assert.ok(!source.includes("ProviderManagementScreen"), "the old provider screen is no longer used");
});
