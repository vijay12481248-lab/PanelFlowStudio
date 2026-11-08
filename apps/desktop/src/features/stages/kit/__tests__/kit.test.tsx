import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import type { Job } from "@panelflow/shared-types";
import { StageToolbar } from "../StageToolbar";
import { ConfirmDialog } from "../ConfirmDialog";
import { PageThumb } from "../PageThumb";
import { JobProgress } from "../JobProgress";

const text = (d: Document) => d.body.textContent ?? "";
const job = (over: Partial<Job> = {}) => ({ job_id: "j1", project_id: "p1", job_type: "ACQUISITION", status: "RUNNING", progress: 0.4, message: "Downloading page 4", input: {}, output: {}, error: null, created_at: null, started_at: null, finished_at: null, ...over }) as Job;

test("the toolbar renders one h2 and no h1, with its description and actions", async () => {
  const view = await mountPage(<StageToolbar title="Review pages" description="Confirm the order." actions={<button>Go</button>} />);
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.equal(view.document.querySelectorAll("h2").length, 1);
  assert.equal(view.document.querySelector("h2")!.textContent, "Review pages");
  assert.ok(text(view.document).includes("Confirm the order."));
  assert.ok([...view.document.querySelectorAll("button")].some((b) => b.textContent === "Go"));
  await view.cleanup();
});

function confirmHarness(calls: { confirm: number; cancel: number }, open = true) {
  return <ConfirmDialog open={open} title="Delete page 3?" description="The rest are renumbered." confirmLabel="Delete page" danger onConfirm={() => { calls.confirm++; }} onCancel={() => { calls.cancel++; }} />;
}
const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;

test("a closed confirm dialog renders nothing", async () => {
  const view = await mountPage(confirmHarness({ confirm: 0, cancel: 0 }, false));
  assert.equal(view.document.querySelector('[role="dialog"]'), null);
  await view.cleanup();
});

test("the confirm dialog shows its question, Cancel only cancels, and a double click confirms once", async () => {
  const calls = { confirm: 0, cancel: 0 };
  const view = await mountPage(confirmHarness(calls));
  assert.ok(view.document.querySelector('[role="dialog"]'));
  assert.ok(text(view.document).includes("Delete page 3?"));
  assert.ok(text(view.document).includes("The rest are renumbered."));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.deepEqual(calls, { confirm: 0, cancel: 1 });
  await view.clickTwice(dialogButton(view.document, "Delete page")!);
  assert.equal(calls.confirm, 1, "confirmed once");
  await view.cleanup();
});

test("Escape cancels the confirm dialog", async () => {
  const calls = { confirm: 0, cancel: 0 };
  const view = await mountPage(confirmHarness(calls));
  await act(async () => { view.document.querySelector('[role="dialog"]')!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  assert.equal(calls.cancel, 1);
  assert.equal(calls.confirm, 0);
  await view.cleanup();
});

test("a page thumbnail whose image fails shows its label and Failed, never a broken image", async () => {
  const view = await mountPage(<PageThumb src="/missing.png" label="Page 3" />);
  const img = view.document.querySelector("img")!;
  assert.ok(img);
  await view.fire(img, "error");
  assert.equal(view.document.querySelector("img"), null);
  assert.ok(text(view.document).includes("Page 3"));
  assert.ok(text(view.document).includes("Failed"));
  await view.cleanup();
});

test("a thumbnail marked failed never loads an image and opens on click", async () => {
  let opened = 0;
  const view = await mountPage(<PageThumb src="/x.png" label="Page 1" failed onOpen={() => { opened++; }} />);
  assert.equal(view.document.querySelector("img"), null);
  assert.ok(text(view.document).includes("Failed"));
  await view.click(view.document.querySelector("button")!);
  assert.equal(opened, 1);
  await view.cleanup();
});

test("job progress shows percent, message and status in words, and the idle label with no job", async () => {
  const view = await mountPage(<JobProgress job={job()} idleLabel="Not started" />);
  assert.equal(view.document.querySelector('[role="progressbar"]')!.getAttribute("aria-valuenow"), "40");
  assert.ok(text(view.document).includes("Downloading page 4"));
  assert.ok(text(view.document).includes("Running"));
  await view.cleanup();
  const idle = await mountPage(<JobProgress job={null} idleLabel="Not started" />);
  assert.ok(text(idle.document).includes("Not started"));
  assert.equal(idle.document.querySelector('[role="progressbar"]'), null);
  await idle.cleanup();
});

test("job progress names every status in words", async () => {
  for (const [status, word] of [["QUEUED", "Waiting"], ["SUCCEEDED", "Done"], ["FAILED", "Failed"], ["CANCELLED", "Cancelled"]] as const) {
    const view = await mountPage(<JobProgress job={job({ status, progress: 1 })} idleLabel="x" />);
    assert.ok(text(view.document).includes(word), word);
    await view.cleanup();
  }
});
