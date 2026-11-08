import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Job } from "@panelflow/shared-types";
import { JobsPage } from "../JobsPage";

const job = (id: string, status: Job["status"], over: Partial<Job> = {}): Job => ({
  job_id: id, project_id: "p1", job_type: "RENDER", status, progress: 0.4, message: "", input: {}, output: {}, error: null,
  created_at: "2026-11-08T10:00:00Z", started_at: "2026-11-08T10:00:00Z", finished_at: status === "RUNNING" || status === "QUEUED" ? null : "2026-11-08T10:05:00Z", ...over,
});

function stub(jobs: Job[] | Error) {
  const calls = { retry: [] as string[], cancel: [] as string[] };
  (api as any).listAllJobs = async () => { if (jobs instanceof Error) throw jobs; return jobs; };
  (api as any).listProjects = async () => [{ id: "p1", title: "Dawn Gate" }];
  (api as any).getJob = async (id: string) => (Array.isArray(jobs) ? jobs.find((j) => j.job_id === id) : undefined);
  (api as any).retryJob = async (id: string) => { calls.retry.push(id); };
  (api as any).cancelJob = async (id: string) => { calls.cancel.push(id); return { status: "ok", message: "" }; };
  return calls;
}

const text = (doc: Document) => doc.body.textContent ?? "";
const button = (doc: Document, label: string) => [...doc.querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const tab = (doc: Document, prefix: string) => [...doc.querySelectorAll('[role="tab"]')].find((t) => t.textContent?.startsWith(prefix)) as HTMLElement;

test("the tabs count Active, Failed and Done jobs", async () => {
  stub([job("r", "RUNNING"), job("q", "QUEUED"), job("f1", "FAILED"), job("f2", "FAILED"), job("d1", "SUCCEEDED"), job("d2", "SUCCEEDED"), job("d3", "SUCCEEDED")]);
  const view = await mountPage(<JobsPage />);
  await view.settle();
  assert.deepEqual([...view.document.querySelectorAll('[role="tab"]')].map((t) => t.textContent), ["Active 2", "Failed 2", "Done 3"]);
  assert.ok(text(view.document).includes("1 running, 1 waiting"));
  await view.cleanup();
});

test("the Active tab lists running jobs before queued ones, named with their project", async () => {
  stub([job("q", "QUEUED", { job_type: "OCR_EXTRACTION", created_at: "2026-11-08T11:00:00Z" }), job("r", "RUNNING", { created_at: "2026-11-08T09:00:00Z" })]);
  const view = await mountPage(<JobsPage />);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.indexOf("Render, Dawn Gate") !== -1 && body.indexOf("OCR extraction, Dawn Gate") !== -1);
  assert.ok(body.indexOf("Render, Dawn Gate") < body.indexOf("OCR extraction, Dawn Gate"), "running first");
  assert.ok(view.document.querySelector('[role="progressbar"]'), "running job shows progress");
  await view.cleanup();
});

test("a failed job shows its first error line and Retry, and a quick double click retries once", async () => {
  const calls = stub([job("f", "FAILED", { error: "CUDA out of memory\nTraceback..." })]);
  const view = await mountPage(<JobsPage />);
  await view.settle();
  await view.press(tab(view.document, "Failed"));
  assert.ok(text(view.document).includes("CUDA out of memory"));
  assert.ok(!text(view.document).includes("Traceback"));
  const retry = button(view.document, "Retry")!;
  await view.clickTwice(retry);
  await view.settle();
  assert.deepEqual(calls.retry, ["f"]);
  await view.cleanup();
});

test("Cancel on an active job asks the engine once", async () => {
  const calls = stub([job("r", "RUNNING")]);
  const view = await mountPage(<JobsPage />);
  await view.settle();
  const cancel = button(view.document, "Cancel")!;
  await view.clickTwice(cancel);
  await view.settle();
  assert.deepEqual(calls.cancel, ["r"]);
  await view.cleanup();
});

test("opening a job shows its details, including the full error, in a drawer", async () => {
  stub([job("f", "FAILED", { error: "CUDA out of memory\nTraceback line two", message: "Render stopped" })]);
  const view = await mountPage(<JobsPage />);
  await view.settle();
  await view.press(tab(view.document, "Failed"));
  await view.click(view.document.querySelector("[data-job-open]") as HTMLElement);
  const drawer = view.document.querySelector('[role="dialog"]');
  assert.ok(drawer, "drawer opened");
  assert.ok(drawer!.textContent!.includes("Traceback line two"));
  assert.ok(drawer!.textContent!.includes("Render stopped"));
  await view.cleanup();
});

test("with no jobs at all there is one invitation instead of empty tabs", async () => {
  stub([]);
  const view = await mountPage(<JobsPage />);
  await view.settle();
  assert.ok(text(view.document).includes("No jobs yet. Start a pipeline stage and it shows up here."));
  await view.cleanup();
});

test("a tab with nothing in it says so while other tabs have jobs", async () => {
  stub([job("d", "SUCCEEDED")]);
  const view = await mountPage(<JobsPage />);
  await view.settle();
  assert.ok(text(view.document).includes("No jobs are running."));
  await view.press(tab(view.document, "Failed"));
  assert.ok(text(view.document).includes("Nothing has failed."));
  await view.cleanup();
});

test("when jobs cannot be loaded the page says what to do and offers Retry", async () => {
  stub(new Error("connection refused"));
  const view = await mountPage(<JobsPage />);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("Couldn't load jobs"));
  assert.ok(!body.includes("connection refused"), "no raw exception text");
  assert.ok(button(view.document, "Retry"));
  await view.cleanup();
});
