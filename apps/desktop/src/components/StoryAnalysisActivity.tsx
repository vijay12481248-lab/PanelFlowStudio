import React, { useEffect, useState } from "react";
import type { Job } from "@panelflow/shared-types";

function timeValue(value?: string | null) {
  if (!value) return 0;
  return Date.parse(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`) || 0;
}

function duration(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}

export const StoryAnalysisActivity: React.FC<{ job: Job | null }> = ({ job }) => {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (!job) return <p className="text-xs text-zinc-400" role="status">Submitting analysis to the engine…</p>;
  const activity = job.output?.model_activity;
  const age = activity ? Math.max(0, (now - timeValue(activity.updated_at)) / 1000) : null;
  const elapsed = Math.max(0, (now - timeValue(job.created_at || job.started_at)) / 1000);
  const phase = activity?.phase === "preparing" ? "Preparing model input"
    : activity?.phase === "validating" ? "Validating generated structure"
    : activity?.phase === "generating" ? "Receiving model output" : "Waiting for model telemetry";
  const workerAlive = timeValue(job.lease_expires_at) > now;
  const totalPanels = job.input?.total_panels;
  const completedPanels = job.progress >= 0.8 ? totalPanels
    : Number(job.message.match(/(\d+) panel checkpoints complete/)?.[1] ?? job.message.match(/Vision analysis: panel (\d+)\//)?.[1] ?? 0);
  const number = (value: number) => value.toLocaleString();
  return (
    <div className="border-t border-indigo-900/60 pt-3 space-y-3 text-xs">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-zinc-300" role="status" aria-live="polite">
        <span className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${age !== null && age < 10 ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
          {job.status === "QUEUED" ? "Queued · waiting for a worker" : phase}
        </span>
        <span>Elapsed <strong className="font-mono text-zinc-100">{duration(elapsed)}</strong></span>
        <span>Job retries: {job.retry_count || 0}/{job.max_retries ?? 3}</span>
        {totalPanels != null && <span>Panels checked: {completedPanels}/{totalPanels}</span>}
        {activity?.max_attempts > 1 && <span>Model attempt: {activity.attempt}/{activity.max_attempts}{activity.attempt > 1 ? " · repairing invalid output" : ""}</span>}
      </div>
      {activity && <><p className="text-zinc-500">Current model request</p><dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-zinc-400">
        <div><dt>Model</dt><dd className="mt-1 text-zinc-200 break-all">{activity.model}</dd></div>
        <div><dt>Output tokens</dt><dd className="mt-1 font-mono text-zinc-200">{activity.output_tokens != null ? number(activity.output_tokens) : `~${number(Math.ceil((activity.output_characters || 0) / 4))} (estimate)`}</dd></div>
        <div><dt>Input tokens</dt><dd className="mt-1 font-mono text-zinc-200">{activity.input_tokens != null ? number(activity.input_tokens) : "Reported when request finishes"}</dd></div>
        <div><dt>Last model activity</dt><dd className="mt-1 font-mono text-zinc-200">{age === null ? "Waiting" : `${duration(age)} ago`}</dd></div>
        <div><dt>Output received</dt><dd className="mt-1 font-mono text-zinc-200">{number(activity.output_characters || 0)} characters</dd></div>
        <div><dt>Output budget (limit)</dt><dd className="mt-1 font-mono text-zinc-200">{number(activity.output_token_limit || 0)} tokens</dd></div>
        {activity.tokens_per_second != null && <div><dt>Generation speed</dt><dd className="mt-1 font-mono text-zinc-200">{activity.tokens_per_second} tokens/s</dd></div>}
      </dl></>}
      <p className="text-zinc-400 leading-relaxed">
        {job.progress >= 0.8 ? "Panel observations are complete. Story sections are reconstructed and saved individually, carrying character continuity forward. " : "Panels are processed in order; completed observations are checkpointed. "}
        Overall progress advances at stage boundaries, not with each token. Token estimates use output characters; exact counts arrive when the model request finishes.
      </p>
      {(!activity || (age !== null && age > 30)) && <p className="text-amber-200/80">
        {workerAlive ? "Worker heartbeat is current. " : "Worker heartbeat is delayed. "}
        {activity ? "No new model output recently; the model may be preparing input or waiting. This does not confirm a freeze." : "Live token details are unavailable for this worker. They will appear for jobs started after the updated engine is loaded."}
      </p>}
      {(job.retry_count || 0) > 0 && job.error && <details className="text-amber-200/80"><summary className="cursor-pointer">Previous attempt failed · retrying with saved checkpoints</summary><p className="mt-2 break-words">{job.error}</p></details>}
    </div>
  );
};
