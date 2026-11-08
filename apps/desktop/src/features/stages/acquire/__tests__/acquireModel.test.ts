import test from "node:test";
import assert from "node:assert/strict";
import type { Job, Page } from "@panelflow/shared-types";
import { acquireActions, acquirePhase, latestAcquisitionJob, pageCounts } from "../acquireModel";

const job = (status: Job["status"], over: Partial<Job> = {}) => ({ job_id: "j", job_type: "ACQUISITION", status, ...over }) as Job;
const page = (status: Page["status"], sequence = 1) => ({ id: `p${sequence}${status}`, status, sequence }) as Page;

test("the phase follows the newest acquisition job", () => {
  assert.equal(acquirePhase(null), "ready");
  assert.equal(acquirePhase(undefined), "ready");
  assert.equal(acquirePhase(job("RUNNING")), "running");
  assert.equal(acquirePhase(job("QUEUED")), "running");
  assert.equal(acquirePhase(job("SUCCEEDED")), "succeeded");
  assert.equal(acquirePhase(job("FAILED")), "failed");
  assert.equal(acquirePhase(job("CANCELLED")), "cancelled");
});

test("only acquisition and retry jobs count, newest first", () => {
  const jobs = [job("SUCCEEDED", { job_id: "norm", job_type: "NORMALIZATION" }), job("FAILED", { job_id: "retry", job_type: "RETRY_PAGES" }), job("SUCCEEDED", { job_id: "acq" })];
  assert.equal(latestAcquisitionJob(jobs)?.job_id, "retry");
  assert.equal(latestAcquisitionJob([job("RUNNING", { job_type: "RENDER" })]), null);
  assert.equal(latestAcquisitionJob([]), null);
  assert.equal(latestAcquisitionJob(undefined), null);
});

test("page counts split ready, failed and the rest", () => {
  assert.deepEqual(pageCounts([]), { total: 0, ready: 0, failed: 0 });
  assert.deepEqual(pageCounts([page("READY", 1), page("READY", 2), page("FAILED", 3), page("PENDING", 4)]), { total: 4, ready: 2, failed: 1 });
});

test("the action matrix for every phase, with and without failed or ready pages", () => {
  const none = { total: 0, ready: 0, failed: 0 };
  const some = { total: 5, ready: 3, failed: 2 };
  assert.deepEqual(acquireActions("ready", none), { start: "Start acquisition", cancel: false, retryFailed: null, review: false });
  assert.deepEqual(acquireActions("running", some), { start: null, cancel: true, retryFailed: null, review: true });
  assert.deepEqual(acquireActions("succeeded", some), { start: null, cancel: false, retryFailed: 2, review: true });
  assert.deepEqual(acquireActions("succeeded", { total: 3, ready: 3, failed: 0 }), { start: null, cancel: false, retryFailed: null, review: true });
  assert.deepEqual(acquireActions("failed", some), { start: "Restart acquisition", cancel: false, retryFailed: 2, review: true });
  assert.deepEqual(acquireActions("failed", none), { start: "Restart acquisition", cancel: false, retryFailed: null, review: false });
  assert.deepEqual(acquireActions("cancelled", none), { start: "Restart acquisition", cancel: false, retryFailed: null, review: false });
  // pages already on disk but no job listed (an older project): the user can still review them and start again
  assert.deepEqual(acquireActions("ready", some), { start: "Start acquisition", cancel: false, retryFailed: 2, review: true });
});
