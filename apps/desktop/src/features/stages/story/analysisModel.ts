import type { Job } from "@panelflow/shared-types";

export interface ModelRow { label: string; value: string }

export interface AnalysisView {
  headline: string;
  elapsed: string;
  retries: string;
  panels: { done: number; total: number } | null;
  attempt: string | null;
  model: ModelRow[] | null;
  note: string | null;
  previousError: string | null;
  explainer: string;
  /** The model produced output in the last 10 seconds. */
  live: boolean;
}

/** A timestamp without a zone is UTC (the engine writes them that way). */
function time(value?: string | null): number {
  if (!value) return 0;
  return Date.parse(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`) || 0;
}

export function formatSpan(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}

const n = (value: number) => value.toLocaleString("en-US");

const PHASE: Record<string, string> = { preparing: "Preparing model input", validating: "Validating generated structure", generating: "Receiving model output" };

/** What the story-analysis job is doing, in words. `now` is passed in so the result is a pure function of the job and the clock. */
export function analysisView(job: Job | null, now: number): AnalysisView {
  if (!job) {
    return { headline: "Submitting the analysis to the engine.", elapsed: "0m 00s", retries: "Job retries: 0/3", panels: null, attempt: null, model: null, note: null, previousError: null, explainer: "", live: false };
  }
  const activity = job.output?.model_activity;
  const age = activity ? Math.max(0, (now - time(activity.updated_at)) / 1000) : null;
  const total = job.input?.total_panels;
  const done = job.progress >= 0.8 ? total : Number(job.message?.match(/(\d+) panel checkpoints complete/)?.[1] ?? job.message?.match(/Vision analysis: panel (\d+)\//)?.[1] ?? 0);
  const workerAlive = time(job.lease_expires_at) > now;
  const stale = !activity || (age !== null && age > 30);

  const model: ModelRow[] | null = activity
    ? [
        { label: "Model", value: String(activity.model) },
        { label: "Output tokens", value: activity.output_tokens != null ? n(activity.output_tokens) : `~${n(Math.ceil((activity.output_characters || 0) / 4))} (estimate)` },
        { label: "Input tokens", value: activity.input_tokens != null ? n(activity.input_tokens) : "Reported when request finishes" },
        { label: "Last model activity", value: age === null ? "Waiting" : `${formatSpan(age)} ago` },
        { label: "Output received", value: `${n(activity.output_characters || 0)} characters` },
        { label: "Output budget (limit)", value: `${n(activity.output_token_limit || 0)} tokens` },
        ...(activity.tokens_per_second != null ? [{ label: "Generation speed", value: `${activity.tokens_per_second} tokens/s` }] : []),
      ]
    : null;

  return {
    headline: job.status === "QUEUED" ? "Queued. Waiting for a worker." : PHASE[activity?.phase] ?? "Waiting for model telemetry",
    elapsed: formatSpan((now - time(job.created_at || job.started_at)) / 1000),
    retries: `Job retries: ${job.retry_count || 0}/${job.max_retries ?? 3}`,
    panels: total != null ? { done, total } : null,
    attempt: activity?.max_attempts > 1 ? `Model attempt ${activity.attempt}/${activity.max_attempts}${activity.attempt > 1 ? " · repairing invalid output" : ""}` : null,
    model,
    note: stale
      ? `${workerAlive ? "Worker heartbeat is current. " : "Worker heartbeat is delayed. "}${activity
          ? "No new model output recently; the model may be preparing input or waiting. This does not confirm a freeze."
          : "Live token details are unavailable for this worker. They will appear for jobs started after the updated engine is loaded."}`
      : null,
    previousError: (job.retry_count || 0) > 0 && job.error ? job.error : null,
    explainer: `${job.progress >= 0.8
      ? "Panel observations are complete. Story sections are rebuilt and saved one at a time, carrying character continuity forward."
      : "Panels are processed in order; finished observations are saved as checkpoints."} Overall progress moves at stage boundaries, not with each token.`,
    live: age !== null && age < 10,
  };
}
