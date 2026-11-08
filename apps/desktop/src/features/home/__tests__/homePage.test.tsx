import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Job, PipelineStage, Project } from "@panelflow/shared-types";
import { HomePage } from "../HomePage";

const NOW = Date.now();
const ago = (ms: number) => new Date(NOW - ms).toISOString();
const DAY = 86_400_000;

const project = (id: string, stage: PipelineStage, over: Partial<Project> = {}): Project => ({
  id, title: `Title ${id}`, source_type: "MANGA" as Project["source_type"], source_url: null, source_metadata: {}, rights_status: "AUTHORIZED_WEB" as Project["rights_status"],
  license_info: "", workspace_path: "", current_stage: stage, settings: {}, created_at: ago(9 * DAY), updated_at: ago(DAY), total_pages: 3, ready_pages: 3, failed_pages: 0, ...over,
});
const job = (id: string, projectId: string, status: Job["status"], over: Partial<Job> = {}): Job => ({
  job_id: id, project_id: projectId, job_type: "RENDER", status, progress: 0.5, message: "Scene 9 of 14", input: {}, output: {}, error: null,
  created_at: ago(DAY), started_at: ago(DAY), finished_at: status === "RUNNING" || status === "QUEUED" ? null : ago(DAY), ...over,
});

function stub(projects: Project[], jobs: Job[] = []) {
  const calls = { retry: [] as string[] };
  Object.assign(api as any, {
    listProjects: async () => projects,
    listAllJobs: async () => jobs,
    listOriginalSeries: async () => [],
    listPages: async () => [{ id: "pg1", sequence: 1 }],
    getPageImageUrl: (pid: string) => `/cover/${pid}.png`,
    getJob: async (id: string) => jobs.find((j) => j.job_id === id),
    retryJob: async (id: string) => { calls.retry.push(id); },
  });
  return calls;
}

const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string) => [...d.querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const headings = (d: Document) => [...d.querySelectorAll("[data-inbox-group]")].map((h) => h.textContent);

test("the inbox groups items as Failed, Review, then Ready to publish", async () => {
  stub(
    [project("pub", "QA_APPROVED"), project("rev", "OCR_COMPLETE"), project("fail", "NORMALIZED")],
    [job("j", "fail", "FAILED", { error: "CUDA out of memory" })],
  );
  const view = await mountPage(<HomePage />);
  await view.settle();
  assert.deepEqual(headings(view.document), ["Failed", "Review", "Ready to publish"]);
  assert.ok(text(view.document).includes("CUDA out of memory"));
  await view.cleanup();
});

test("Retry on a failed row retries that job once", async () => {
  const calls = stub([project("fail", "NORMALIZED")], [job("j", "fail", "FAILED", { error: "boom" })]);
  const view = await mountPage(<HomePage />);
  await view.settle();
  await view.clickTwice(button(view.document, "Retry")!);
  await view.settle();
  assert.deepEqual(calls.retry, ["j"]);
  await view.cleanup();
});

test("a Review row opens the screen where that stage is approved", async () => {
  stub([project("rev", "OCR_COMPLETE")]);
  const view = await mountPage(<HomePage />);
  await view.settle();
  await view.click(button(view.document, "Review")!);
  assert.equal(view.router.state.location.pathname, "/projects/rev/ocr");
  await view.cleanup();
});

test("a long inbox shows 8 rows until Show all is pressed", async () => {
  stub(Array.from({ length: 12 }, (_, i) => project(`p${String(i).padStart(2, "0")}`, "OCR_COMPLETE", { updated_at: ago((i + 1) * 1000) })));
  const view = await mountPage(<HomePage />);
  await view.settle();
  assert.equal(view.document.querySelectorAll("[data-inbox-row]").length, 8);
  await view.click(button(view.document, "Show all 12")!);
  assert.equal(view.document.querySelectorAll("[data-inbox-row]").length, 12);
  await view.cleanup();
});

test("with no projects Home invites you to create one and shows no hero", async () => {
  stub([]);
  const view = await mountPage(<HomePage />);
  await view.settle();
  assert.ok(text(view.document).includes("Nothing needs you"));
  assert.ok(button(view.document, "Create a project"));
  assert.equal(view.document.querySelector("[data-hero]"), null);
  await view.cleanup();
});

test("the hero is the project behind the first inbox item", async () => {
  stub([project("old", "NEW", { updated_at: ago(30 * DAY) }), project("new", "NEW", { updated_at: ago(1000) }), project("rev", "OCR_COMPLETE", { updated_at: ago(5 * DAY) })]);
  const view = await mountPage(<HomePage />);
  await view.settle();
  assert.ok(view.document.querySelector("[data-hero]")!.textContent!.includes("Title rev"));
  await view.cleanup();
});

test("with nothing waiting the hero falls back to the latest project and Home says all clear", async () => {
  stub([project("old", "NEW", { updated_at: ago(30 * DAY) }), project("new", "NEW", { updated_at: ago(1000) })]);
  const view = await mountPage(<HomePage />);
  await view.settle();
  assert.ok(view.document.querySelector("[data-hero]")!.textContent!.includes("Title new"));
  assert.ok(text(view.document).includes("Nothing needs you"));
  await view.cleanup();
});

test("running jobs show with progress and a link to all jobs", async () => {
  stub([project("p", "NEW")], [job("r", "p", "RUNNING", { progress: 0.62 })]);
  const view = await mountPage(<HomePage />);
  await view.settle();
  const bar = view.document.querySelector('[role="progressbar"]');
  assert.equal(bar?.getAttribute("aria-valuenow"), "62");
  const link = [...view.document.querySelectorAll("a")].find((a) => a.textContent === "All jobs");
  assert.ok(link);
  await view.click(link!);
  assert.equal(view.router.state.location.pathname, "/jobs");
  await view.cleanup();
});

test("a project cover that fails to load never leaves a broken image in the hero", async () => {
  stub([project("p", "NEW")]);
  const view = await mountPage(<HomePage />);
  await view.settle();
  const img = view.document.querySelector("[data-hero] img") as HTMLImageElement;
  assert.ok(img);
  await view.fire(img, "error");
  assert.equal(view.document.querySelector("[data-hero] img"), null);
  await view.cleanup();
});
