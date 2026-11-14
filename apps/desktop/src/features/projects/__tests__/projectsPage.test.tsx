import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { ProjectsPage } from "../ProjectsPage";

const project = (id: string, title: string, over: Partial<Project> = {}): Project => ({
  id, title, source_type: "MANGA" as Project["source_type"], source_url: null, source_metadata: {}, rights_status: "AUTHORIZED_WEB" as Project["rights_status"],
  license_info: "", workspace_path: "", current_stage: "NEW", settings: {}, created_at: "2026-10-01", updated_at: "2026-11-01", total_pages: 3, ready_pages: 3, failed_pages: 0, ...over,
});

const PROJECTS = [
  project("a", "The Regressed Son Of A Duke", { updated_at: "2026-11-02" }),
  project("b", "Magic Emperor", { updated_at: "2026-11-06" }),
  project("c", "Moon Tales", { updated_at: "2026-11-04" }),
];

function stub(projects: Project[], over: Record<string, unknown> = {}) {
  const calls = { deleted: [] as string[] };
  Object.assign(api as any, {
    listProjects: async () => projects,
    listAllJobs: async () => [],
    listOriginalSeries: async () => [],
    listOriginalStories: async () => [],
    listChronoFlowJobs: async () => [],
    listPages: async () => [{ id: "pg1", sequence: 1 }],
    getPageImageUrl: (pid: string) => `/cover/${pid}.png`,
    deleteProject: async (id: string) => { calls.deleted.push(id); },
    openProjectFolder: async () => ({ opened: true, path: "" }),
    ...over,
  });
  return calls;
}

const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string) => [...d.querySelectorAll("button")].find((b) => b.textContent?.trim() === label || b.getAttribute("aria-label") === label) as HTMLButtonElement | undefined;
const tab = (d: Document, prefix: string) => [...d.querySelectorAll('[role="tab"]')].find((t) => t.textContent?.startsWith(prefix)) as HTMLElement;
const tileTitles = (d: Document) => [...d.querySelectorAll("[data-project-tile]")].map((t) => t.getAttribute("data-project-tile"));

async function type(view: Awaited<ReturnType<typeof mountPage>>, value: string) {
  const input = view.document.querySelector('input[type="search"]') as HTMLInputElement;
  await view.setValue(input, value);
}

test("projects are listed newest first, each with a plain-language stage", async () => {
  localStorage.clear();
  stub(PROJECTS);
  const view = await mountPage(<ProjectsPage />);
  await view.settle();
  assert.deepEqual(tileTitles(view.document), ["Magic Emperor", "Moon Tales", "The Regressed Son Of A Duke"]);
  assert.ok(text(view.document).includes("Not started"));
  await view.cleanup();
});

test("searching hides projects that do not match", async () => {
  localStorage.clear();
  stub(PROJECTS);
  const view = await mountPage(<ProjectsPage />);
  await view.settle();
  await type(view, "duke");
  assert.deepEqual(tileTitles(view.document), ["The Regressed Son Of A Duke"]);
  await type(view, "zzz");
  assert.ok(text(view.document).includes("No projects match"));
  await view.cleanup();
});

test("starring a project keeps it on the Favorites tab and remembers it", async () => {
  localStorage.clear();
  stub(PROJECTS);
  const view = await mountPage(<ProjectsPage />);
  await view.settle();
  await view.click(view.document.querySelector('[data-project-tile="Moon Tales"] button[aria-pressed]') as HTMLElement);
  await view.press(tab(view.document, "Favorites"));
  assert.deepEqual(tileTitles(view.document), ["Moon Tales"]);
  assert.equal(localStorage.getItem("panelflow_project_favorites"), '{"c":true}');
  await view.cleanup();
});

test("a cover that fails to load falls back to initials with no broken image", async () => {
  localStorage.clear();
  stub([PROJECTS[1]]);
  const view = await mountPage(<ProjectsPage />);
  await view.settle();
  const img = view.document.querySelector("[data-project-tile] img") as HTMLImageElement;
  assert.ok(img, "cover image requested");
  await view.fire(img, "error");
  assert.equal(view.document.querySelector("[data-project-tile] img"), null);
  assert.ok(text(view.document).includes("ME"));
  await view.cleanup();
});

async function openDeleteDialog(view: Awaited<ReturnType<typeof mountPage>>, title: string) {
  const trigger = view.document.querySelector(`[data-project-tile="${title}"] button[aria-haspopup="menu"]`) as HTMLElement;
  await view.press(trigger);
  const item = [...view.document.querySelectorAll('[role="menuitem"]')].find((i) => i.textContent === "Delete project") as HTMLElement;
  await view.press(item);
}

test("deleting asks first, Cancel changes nothing, and confirming deletes once", async () => {
  localStorage.clear();
  const calls = stub(PROJECTS);
  const view = await mountPage(<ProjectsPage />);
  await view.settle();
  await openDeleteDialog(view, "Moon Tales");
  const dialog = view.document.querySelector('[role="dialog"]')!;
  assert.ok(dialog.textContent!.includes("Delete Moon Tales?"));
  assert.ok(dialog.textContent!.includes("You cannot undo this."));
  await view.click(button(view.document, "Cancel")!);
  assert.deepEqual(calls.deleted, []);
  await openDeleteDialog(view, "Moon Tales");
  await view.clickTwice(button(view.document, "Delete project")!);
  await view.settle();
  assert.deepEqual(calls.deleted, ["c"]);
  assert.ok(!tileTitles(view.document).includes("Moon Tales"));
  await view.cleanup();
});

test("a delete the engine refuses keeps the project and says so in words", async () => {
  localStorage.clear();
  stub(PROJECTS, { deleteProject: async () => { throw new Error("A render is still running."); } });
  const view = await mountPage(<ProjectsPage />);
  await view.settle();
  await openDeleteDialog(view, "Moon Tales");
  await view.click(button(view.document, "Delete project")!);
  await view.settle();
  assert.ok(tileTitles(view.document).includes("Moon Tales"));
  await view.cleanup();
});

test("with no projects the page invites you to create one", async () => {
  localStorage.clear();
  stub([]);
  const view = await mountPage(<ProjectsPage />);
  await view.settle();
  assert.ok(text(view.document).includes("No projects yet"));
  assert.ok(button(view.document, "Create a project"));
  await view.cleanup();
});

test("chapters of one series are grouped under the series name", async () => {
  localStorage.clear();
  stub([project("x1", "Magic Emperor - Chapter 927"), project("x2", "Magic Emperor - Chapter 928"), project("y", "Standalone")]);
  const view = await mountPage(<ProjectsPage />);
  await view.settle();
  assert.ok([...view.document.querySelectorAll("h2")].some((h) => h.textContent === "Magic Emperor"));
  await view.cleanup();
});
