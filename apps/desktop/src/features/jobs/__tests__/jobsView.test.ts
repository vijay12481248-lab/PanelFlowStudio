import test from "node:test";
import assert from "node:assert/strict";
import type { Job } from "@panelflow/shared-types";
import { firstErrorLine, groupJobs, jobDuration, jobLabel } from "../jobsView";

const base = (over: Partial<Job>): Job => ({
  job_id: "j", project_id: "p", job_type: "RENDER", status: "SUCCEEDED", progress: 0, message: "", input: {}, output: {}, error: null,
  created_at: "2026-11-08T10:00:00Z", started_at: null, finished_at: null, ...over,
});

test("jobLabel turns engine job types into sentence case and keeps acronyms", () => {
  assert.equal(jobLabel("OCR_EXTRACTION"), "OCR extraction");
  assert.equal(jobLabel("RENDER"), "Render");
  assert.equal(jobLabel("H3_CLIP"), "H3 clip");
  assert.equal(jobLabel("PANEL_DETECTION"), "Panel detection");
  assert.equal(jobLabel("GPU_WARMUP"), "GPU warmup");
});

test("groupJobs sorts into Active, Failed and Done with running before queued and newest first", () => {
  const jobs = [
    base({ job_id: "q", status: "QUEUED", created_at: "2026-11-08T11:00:00Z" }),
    base({ job_id: "r-old", status: "RUNNING", created_at: "2026-11-08T09:00:00Z" }),
    base({ job_id: "r-new", status: "RUNNING", created_at: "2026-11-08T10:30:00Z" }),
    base({ job_id: "f-old", status: "FAILED", finished_at: "2026-11-07T10:00:00Z" }),
    base({ job_id: "c", status: "CANCELLED", finished_at: "2026-11-08T08:00:00Z" }),
    base({ job_id: "d1", status: "SUCCEEDED", finished_at: "2026-11-06T10:00:00Z" }),
    base({ job_id: "d2", status: "SUCCEEDED", finished_at: "2026-11-08T07:00:00Z" }),
  ];
  const groups = groupJobs(jobs);
  assert.deepEqual(groups.active.map((j) => j.job_id), ["r-new", "r-old", "q"]);
  assert.deepEqual(groups.failed.map((j) => j.job_id), ["c", "f-old"]);
  assert.deepEqual(groups.done.map((j) => j.job_id), ["d2", "d1"]);
});

test("groupJobs of nothing is three empty lists", () => {
  assert.deepEqual(groupJobs([]), { active: [], failed: [], done: [] });
});

test("jobDuration reads like a person would say it", () => {
  const start = "2026-11-08T10:00:00Z";
  const at = (s: number) => new Date(Date.parse(start) + s * 1000).toISOString();
  assert.equal(jobDuration(base({ started_at: start, finished_at: at(45) }), 0), "45 s");
  assert.equal(jobDuration(base({ started_at: start, finished_at: at(192) }), 0), "3 min 12 s");
  assert.equal(jobDuration(base({ started_at: start, finished_at: at(3840) }), 0), "1 h 4 min");
  assert.equal(jobDuration(base({ started_at: start, finished_at: null, status: "RUNNING" }), Date.parse(start) + 60_000), "1 min 0 s");
  assert.equal(jobDuration(base({ started_at: null }), Date.now()), null);
});

test("firstErrorLine shows the cause, not the traceback", () => {
  assert.equal(firstErrorLine(base({ error: "\nCUDA out of memory\nTraceback (most recent call last):\n  File x" })), "CUDA out of memory");
  assert.equal(firstErrorLine(base({ error: "x".repeat(300) })).length, 160);
  assert.equal(firstErrorLine(base({ error: null, message: "Cancelled by user" })), "Cancelled by user");
  assert.equal(firstErrorLine(base({ error: null, message: "" })), "No details were recorded.");
});
