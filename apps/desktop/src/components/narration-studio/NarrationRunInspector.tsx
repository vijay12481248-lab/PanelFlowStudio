import React, { useState } from "react";
import type { NarrationRunDetail, NarrationRunSummary } from "@panelflow/shared-types";

export interface NarrationRunInspectorProps {
  projects: { id: string; title: string }[];
  projectId: string | null;
  runs: NarrationRunSummary[];
  runId: string | null;
  run: NarrationRunDetail | null;
  onSelectProject: (projectId: string) => void;
  onSelectRun: (runId: string) => void;
}

const selectCls = "bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-100";

export const NarrationRunInspector: React.FC<NarrationRunInspectorProps> = ({
  projects, projectId, runs, runId, run, onSelectProject, onSelectRun,
}) => {
  const [open, setOpen] = useState<string | null>(null);
  const steps = runs.find((r) => r.run_id === runId)?.steps ?? [];
  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 text-zinc-100 text-xs">
      <div className="flex gap-3">
        <select aria-label="Project" className={selectCls} value={projectId ?? ""} onChange={(e) => onSelectProject(e.target.value)}>
          <option value="">Select project</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
        </select>
        <select aria-label="Run" className={selectCls} value={runId ?? ""} onChange={(e) => onSelectRun(e.target.value)}>
          <option value="">Select run</option>
          {runs.map((r) => <option key={r.run_id} value={r.run_id}>{r.run_id}{r.gate ? ` (${r.gate})` : ""}</option>)}
        </select>
      </div>
      {steps.length > 0 && (
        <table aria-label="Steps" className="w-full text-left">
          <thead className="text-zinc-500 uppercase text-[10px]">
            <tr><th>Step</th><th>Status</th><th>Seconds</th><th>Model calls</th></tr>
          </thead>
          <tbody>
            {steps.map((s) => (
              <tr key={s.step} className="border-t border-zinc-800">
                <td>{s.step}</td><td>{s.status}</td><td>{s.seconds}</td><td>{s.model_calls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {run && (
        <table aria-label="Lines" className="w-full text-left">
          <thead className="text-zinc-500 uppercase text-[10px]">
            <tr><th>Line</th><th>Text</th><th>Status</th><th>Checks</th></tr>
          </thead>
          <tbody>
            {run.lines.map((l) => (
              <React.Fragment key={l.line_id}>
                <tr className="border-t border-zinc-800 align-top">
                  <td>
                    <button
                      type="button"
                      aria-label={`Toggle details for ${l.line_id}`}
                      aria-expanded={open === l.line_id}
                      onClick={() => setOpen(open === l.line_id ? null : l.line_id)}
                      className="font-mono text-indigo-400"
                    >
                      {l.line_id}
                    </button>
                  </td>
                  <td>{l.text}</td>
                  <td>{l.status}</td>
                  <td>{l.checks.filter((c) => !c.passed).map((c) => c.rule).join(", ") || "ok"}</td>
                </tr>
                {open === l.line_id && (
                  <tr>
                    <td colSpan={4} className="pb-2 text-zinc-400 font-mono">
                      <div>Facts: {l.facts}</div>
                      {l.take ? <div>Take: WER {l.take.wer}{l.take.flagged ? " (flagged)" : ""}, heard “{l.take.stt_text}”</div> : <div>No take</div>}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};
