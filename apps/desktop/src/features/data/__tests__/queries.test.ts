import test from "node:test";
import assert from "node:assert/strict";
import type { Job } from "@panelflow/shared-types";
import { coverVersion, jobsPollInterval, queryKeys } from "../queries";

const job = (status: Job["status"]): Job => ({
  job_id: "j", project_id: "p", job_type: "RENDER", status, progress: 0, message: "", input: {}, output: {}, error: null,
  created_at: null, started_at: null, finished_at: null,
});

test("jobs poll every 3 seconds while anything is running or queued, otherwise every 8", () => {
  assert.equal(jobsPollInterval(undefined), 8000);
  assert.equal(jobsPollInterval([]), 8000);
  assert.equal(jobsPollInterval([job("SUCCEEDED"), job("FAILED")]), 8000);
  assert.equal(jobsPollInterval([job("SUCCEEDED"), job("RUNNING")]), 3000);
  assert.equal(jobsPollInterval([job("QUEUED")]), 3000);
});

test("a cover is refetched only when the project's update time or page count changes", () => {
  assert.equal(coverVersion({ updated_at: "2026-11-06", total_pages: 78 }), "2026-11-06:78");
  assert.notEqual(coverVersion({ updated_at: "2026-11-06", total_pages: 78 }), coverVersion({ updated_at: "2026-11-06", total_pages: 79 }));
});

test("query keys are stable so invalidation reaches every consumer", () => {
  assert.deepEqual(queryKeys.projects, ["projects"]);
  assert.deepEqual(queryKeys.jobs, ["jobs"]);
  assert.deepEqual(queryKeys.cover("p1", "v"), ["cover", "p1", "v"]);
});
