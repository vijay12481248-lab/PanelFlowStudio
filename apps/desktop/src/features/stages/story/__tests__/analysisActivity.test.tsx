import { mount } from "../../../../../../../packages/ui/src/v2/__tests__/dom"; // first: installs jsdom
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import type { Job } from "@panelflow/shared-types";
import { AnalysisActivity } from "../AnalysisActivity";

const NOW = Date.parse("2026-11-08T12:00:00Z");
const job = (over: Partial<Job> = {}) => ({
  job_id: "j", project_id: "p", job_type: "STORY_ANALYSIS", status: "RUNNING", progress: 0.9, message: "", input: { total_panels: 40 }, output: {}, error: null,
  created_at: "2026-11-08T11:58:00Z", started_at: null, finished_at: null, retry_count: 1, ...over,
}) as Job;
const text = (d: Document) => d.body.textContent ?? "";

test("it shows the headline, elapsed time and panels checked", async () => {
  const view = await mount(<AnalysisActivity job={job({ error: "model timed out" })} now={NOW} />);
  const body = text(view.document);
  assert.ok(body.includes("Waiting for model telemetry"));
  assert.ok(body.includes("2m 00s"));
  assert.ok(body.includes("Panels checked: 40/40"));
  assert.ok(view.document.querySelector('[role="status"]'));
  await view.cleanup();
});

test("a previous attempt's error is inside a details block", async () => {
  const view = await mount(<AnalysisActivity job={job({ error: "model timed out" })} now={NOW} />);
  const details = view.document.querySelector("details")!;
  assert.ok(details);
  assert.ok(details.textContent!.includes("model timed out"));
  await view.cleanup();
});

test("text from the job is shown as text, not as markup", async () => {
  const view = await mount(<AnalysisActivity job={job({ error: "<img src=x onerror=alert(1)>" })} now={NOW} />);
  assert.equal(view.document.querySelector("img"), null);
  assert.ok(text(view.document).includes("<img src=x"));
  await view.cleanup();
});

test("it ticks once a second while mounted and stops when it unmounts", async () => {
  const realSet = globalThis.setInterval, realClear = globalThis.clearInterval;
  const live = new Set<unknown>();
  (globalThis as any).setInterval = (fn: () => void, ms: number) => { const h = realSet(fn, ms); live.add(h); return h; };
  (globalThis as any).clearInterval = (h: unknown) => { live.delete(h); realClear(h as any); };
  try {
    const view = await mount(<AnalysisActivity job={job()} />);
    assert.equal(live.size, 1, "one interval while mounted");
    await view.cleanup();
    assert.equal(live.size, 0, "cleared on unmount");
  } finally { globalThis.setInterval = realSet; globalThis.clearInterval = realClear; }
});
