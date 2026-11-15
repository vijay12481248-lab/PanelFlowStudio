import React from "react";
import type { Job } from "@panelflow/shared-types";
import { analysisView } from "./analysisModel";

/** Live detail for a running story analysis: phase, time, panels, retries and the model's own telemetry. */
export const AnalysisActivity: React.FC<{ job: Job | null; /** Fixed clock for tests. */ now?: number }> = ({ job, now }) => {
  const [tick, setTick] = React.useState(() => Date.now());
  React.useEffect(() => {
    const timer = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const view = analysisView(job, now ?? tick);
  return (
    <div className="grid grid-cols-1 gap-3 border-t border-edge pt-3 text-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-fg-dim" role="status" aria-live="polite">
        <span className="font-medium text-fg">{view.headline}</span>
        {job && <span>{`Elapsed ${view.elapsed}`}</span>}
        {job && <span>{view.retries}</span>}
        {view.panels && <span>{`Panels checked: ${view.panels.done}/${view.panels.total}`}</span>}
        {view.attempt && <span>{view.attempt}</span>}
      </div>
      {view.model && (
        <dl className="grid grid-cols-2 gap-3 text-fg-dim sm:grid-cols-4">
          {view.model.map((row) => (
            <div key={row.label}><dt className="text-xs text-fg-faint">{row.label}</dt><dd className="mt-0.5 break-all font-data text-fg">{row.value}</dd></div>
          ))}
        </dl>
      )}
      {view.explainer && <p className="text-fg-dim">{view.explainer}</p>}
      {view.note && <p className="text-warn">{view.note}</p>}
      {view.previousError && (
        <details className="text-warn">
          <summary className="cursor-pointer">Previous attempt failed. Retrying with saved checkpoints.</summary>
          <p className="mt-2 break-words">{view.previousError}</p>
        </details>
      )}
    </div>
  );
};
