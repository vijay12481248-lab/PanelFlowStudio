import test from "node:test";
import assert from "node:assert/strict";
import type { Job } from "@panelflow/shared-types";
import { analysisView, formatSpan } from "../analysisModel";

const NOW = Date.parse("2026-11-08T12:00:00Z");
const job = (over: Partial<Job> = {}) => ({
  job_id: "j", project_id: "p", job_type: "STORY_ANALYSIS", status: "RUNNING", progress: 0.3, message: "", input: {}, output: {}, error: null,
  created_at: "2026-11-08T11:58:00Z", started_at: null, finished_at: null, ...over,
}) as Job;
const activity = (over: Record<string, unknown> = {}) => ({ phase: "generating", model: "qwen3.5:9b", updated_at: "2026-11-08T11:59:58Z", output_characters: 4000, output_token_limit: 8192, attempt: 1, max_attempts: 1, ...over });

test("spans are shown as minutes and padded seconds, never negative", () => {
  assert.equal(formatSpan(125), "2m 05s");
  assert.equal(formatSpan(0), "0m 00s");
  assert.equal(formatSpan(-5), "0m 00s");
  assert.equal(formatSpan(59.9), "0m 59s");
});

test("no job yet says the analysis is being submitted", () => {
  const v = analysisView(null, NOW);
  assert.equal(v.headline, "Submitting the analysis to the engine.");
  assert.equal(v.panels, null);
  assert.equal(v.model, null);
});

test("a queued job waits for a worker", () => {
  assert.equal(analysisView(job({ status: "QUEUED" }), NOW).headline, "Queued. Waiting for a worker.");
});

test("the headline follows the model's phase, or says it is waiting for telemetry", () => {
  const phase = (p: string | undefined) => analysisView(job({ output: p ? { model_activity: activity({ phase: p }) } : {} }), NOW).headline;
  assert.equal(phase("preparing"), "Preparing model input");
  assert.equal(phase("validating"), "Validating generated structure");
  assert.equal(phase("generating"), "Receiving model output");
  assert.equal(phase(undefined), "Waiting for model telemetry");
});

test("elapsed time runs from creation, and a timestamp without a zone is read as UTC", () => {
  assert.equal(analysisView(job(), NOW).elapsed, "2m 00s");
  assert.equal(analysisView(job({ created_at: "2026-11-08T11:57:00" }), NOW).elapsed, "3m 00s");
  assert.equal(analysisView(job({ created_at: null, started_at: "2026-11-08T11:59:30Z" }), NOW).elapsed, "0m 30s");
});

test("retries use the job's own limit, defaulting to 3", () => {
  assert.equal(analysisView(job({ retry_count: 1 }), NOW).retries, "Job retries: 1/3");
  assert.equal(analysisView(job({ retry_count: 2, max_retries: 5 }), NOW).retries, "Job retries: 2/5");
  assert.equal(analysisView(job(), NOW).retries, "Job retries: 0/3");
});

test("panels checked come from the total, the progress and the message", () => {
  assert.equal(analysisView(job({ input: {} }), NOW).panels, null);
  assert.deepEqual(analysisView(job({ input: { total_panels: 40 }, progress: 0.9 }), NOW).panels, { done: 40, total: 40 });
  assert.deepEqual(analysisView(job({ input: { total_panels: 40 }, progress: 0.4, message: "12 panel checkpoints complete" }), NOW).panels, { done: 12, total: 40 });
  assert.deepEqual(analysisView(job({ input: { total_panels: 40 }, progress: 0.4, message: "Vision analysis: panel 7/40" }), NOW).panels, { done: 7, total: 40 });
  assert.deepEqual(analysisView(job({ input: { total_panels: 40 }, progress: 0.1, message: "starting" }), NOW).panels, { done: 0, total: 40 });
});

test("a repeated model attempt is shown, and a repair is named", () => {
  const view = (a: number, max: number) => analysisView(job({ output: { model_activity: activity({ attempt: a, max_attempts: max }) } }), NOW).attempt;
  assert.equal(view(1, 1), null);
  assert.equal(view(1, 3), "Model attempt 1/3");
  assert.equal(view(2, 3), "Model attempt 2/3 · repairing invalid output");
});

test("model rows show exact numbers when the model reported them and estimates when it did not", () => {
  const exact = analysisView(job({ output: { model_activity: activity({ output_tokens: 1234, input_tokens: 9000, tokens_per_second: 21.5 }) } }), NOW).model!;
  const row = (label: string) => exact.find((r) => r.label === label)?.value;
  assert.equal(row("Model"), "qwen3.5:9b");
  assert.equal(row("Output tokens"), "1,234");
  assert.equal(row("Input tokens"), "9,000");
  assert.equal(row("Last model activity"), "0m 02s ago");
  assert.equal(row("Output received"), "4,000 characters");
  assert.equal(row("Output budget (limit)"), "8,192 tokens");
  assert.equal(row("Generation speed"), "21.5 tokens/s");
  const est = analysisView(job({ output: { model_activity: activity() } }), NOW).model!;
  assert.equal(est.find((r) => r.label === "Output tokens")?.value, "~1,000 (estimate)");
  assert.equal(est.find((r) => r.label === "Input tokens")?.value, "Reported when request finishes");
  assert.equal(est.find((r) => r.label === "Generation speed"), undefined);
});

test("fresh activity is live and gives no note; stale or missing activity explains the heartbeat", () => {
  const fresh = analysisView(job({ output: { model_activity: activity() } }), NOW);
  assert.equal(fresh.live, true);
  assert.equal(fresh.note, null);
  const stale = analysisView(job({ lease_expires_at: "2026-11-08T12:05:00Z", output: { model_activity: activity({ updated_at: "2026-11-08T11:58:00Z" }) } }), NOW);
  assert.equal(stale.live, false);
  assert.equal(stale.note, "Worker heartbeat is current. No new model output recently; the model may be preparing input or waiting. This does not confirm a freeze.");
  const none = analysisView(job({ lease_expires_at: "2026-11-08T11:00:00Z" }), NOW);
  assert.equal(none.note, "Worker heartbeat is delayed. Live token details are unavailable for this worker. They will appear for jobs started after the updated engine is loaded.");
});

test("the previous attempt's error is kept only when the job was retried", () => {
  assert.equal(analysisView(job({ retry_count: 1, error: "timeout" }), NOW).previousError, "timeout");
  assert.equal(analysisView(job({ retry_count: 0, error: "timeout" }), NOW).previousError, null);
  assert.equal(analysisView(job({ retry_count: 1, error: null }), NOW).previousError, null);
});
