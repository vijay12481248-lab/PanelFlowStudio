import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Job, Page, Project } from "@panelflow/shared-types";
import { AcquireStage } from "../AcquireStage";

const project = { id: "p1", title: "Dawn Gate", current_stage: "RIGHTS_APPROVED", rights_status: "AUTHORIZED_WEB", stale_stages: [] } as unknown as Project;
const job = (status: Job["status"], over: Partial<Job> = {}) => ({ job_id: "j1", project_id: "p1", job_type: "ACQUISITION", status, progress: 0.5, message: "Downloading", input: {}, output: {}, error: null, created_at: null, started_at: null, finished_at: null, ...over }) as Job;
const page = (n: number, status: Page["status"] = "READY") => ({ id: `pg${n}`, project_id: "p1", sequence: n, filename: `${n}.png`, status, error_message: status === "FAILED" ? "bad file" : null, width: 800, height: 1200 }) as Page;

interface Calls { start: number; getJob: number; cancel: number; retry: number; folder: number }
function stub(opts: { jobs?: Job[]; pages?: Page[]; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { start: 0, getJob: 0, cancel: 0, retry: 0, folder: 0 };
  let current = opts.jobs ?? [];
  Object.assign(api as any, {
    listPages: async () => opts.pages ?? [],
    listProjectJobs: async () => current,
    startAcquisition: async () => { calls.start++; return { job_id: "j2", message: "ok" }; },
    getJob: async (id: string) => { calls.getJob++; return current.find((j) => j.job_id === id) ?? job("RUNNING", { job_id: id }); },
    cancelJob: async () => { calls.cancel++; return { status: "ok", message: "" }; },
    retryFailedPages: async () => { calls.retry++; return { job_id: "j3", message: "ok" }; },
    openProjectFolder: async () => { calls.folder++; return { opened: true, path: "" }; },
    getPageImageUrl: (_p: string, id: string) => `/img/${id}.png`,
    ...opts.over,
  });
  return { calls, setJobs: (jobs: Job[]) => { current = jobs; } };
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;

async function show(onReview: () => void = () => {}) {
  const view = await mountPage(<AcquireStage project={project} onReviewPages={onReview} />);
  await view.settle();
  return view;
}

test("nothing acquired yet: it invites Start acquisition, and pressing it twice starts one job and follows it", async () => {
  const { calls } = stub();
  const view = await show();
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.ok(text(view.document).includes("No pages yet"));
  assert.equal(button(view.document, "Cancel acquisition"), undefined);
  await view.clickTwice(button(view.document, "Start acquisition")!);
  await view.settle();
  assert.equal(calls.start, 1, "started once");
  assert.ok(button(view.document, "Cancel acquisition"), "now following the new job");
  assert.equal(button(view.document, "Start acquisition"), undefined);
  await view.cleanup();
});

test("a job already running when the stage opens is followed, not restarted, and polling stops after leaving", async () => {
  const { calls } = stub({ jobs: [job("RUNNING")], pages: [page(1)] });
  const view = await show();
  assert.ok(button(view.document, "Cancel acquisition"));
  assert.equal(button(view.document, "Start acquisition"), undefined);
  assert.equal(calls.start, 0);
  assert.ok(text(view.document).includes("Running"));
  await view.cleanup();
  const after = calls.getJob;
  await new Promise((resolve) => setTimeout(resolve, 1300));
  assert.equal(calls.getJob, after, "no polling after the stage unmounted");
});

test("Cancel acquisition cancels once", async () => {
  const { calls } = stub({ jobs: [job("RUNNING")] });
  const view = await show();
  await view.clickTwice(button(view.document, "Cancel acquisition")!);
  await view.settle();
  assert.equal(calls.cancel, 1);
  await view.cleanup();
});

test("a failed job with failed pages offers Restart acquisition and Retry failed pages, and shows the failed page", async () => {
  const { calls } = stub({ jobs: [job("FAILED", { progress: 0.3 })], pages: [page(1), page(2, "FAILED"), page(3, "FAILED")] });
  const view = await show();
  assert.ok(button(view.document, "Restart acquisition"));
  const retry = button(view.document, "Retry failed pages (2)")!;
  assert.ok(retry);
  assert.ok(text(view.document).includes("Failed"));
  assert.ok(text(view.document).includes("1 of 3 pages downloaded"));
  await view.clickTwice(retry);
  await view.settle();
  assert.equal(calls.retry, 1);
  await view.cleanup();
});

test("a finished acquisition with ready pages offers Review pages", async () => {
  stub({ jobs: [job("SUCCEEDED", { progress: 1 })], pages: [page(1), page(2)] });
  let reviewed = 0;
  const view = await show(() => { reviewed++; });
  await view.click(button(view.document, /^Review pages \(2\)/)!);
  assert.equal(reviewed, 1);
  assert.equal(button(view.document, "Start acquisition"), undefined);
  await view.cleanup();
});

test("a rejected start explains what to do and never shows the raw exception", async () => {
  stub({ over: { startAcquisition: async () => { throw new Error("ECONNRESET at C:\\engine\\secret.py line 9"); } } });
  const view = await show();
  await view.click(button(view.document, "Start acquisition")!);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("Couldn't start acquisition"));
  assert.ok(!body.includes("ECONNRESET") && !body.includes("secret.py"));
  assert.ok(button(view.document, "Start acquisition"), "can try again");
  await view.cleanup();
});

test("Open source folder asks the engine to open the project folder", async () => {
  const { calls } = stub();
  const view = await show();
  await view.click(button(view.document, "Open source folder")!);
  assert.equal(calls.folder, 1);
  await view.cleanup();
});

test("a page whose image is missing shows the page label, not a broken image", async () => {
  stub({ jobs: [job("SUCCEEDED", { progress: 1 })], pages: [page(1)] });
  const view = await show();
  const img = view.document.querySelector("img")!;
  await view.fire(img, "error");
  assert.equal(view.document.querySelector("img"), null);
  assert.ok(text(view.document).includes("Page 1"));
  await view.cleanup();
});
