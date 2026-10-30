import React, { useState } from "react";
import { Button, ProgressBar } from "@panelflow/ui";
import type {
  NarrationLine,
  NarrationLineActionRequest,
  NarrationReviewItem,
  NarrationRunDetail,
} from "@panelflow/shared-types";

// Statuses the server treats as resolved (engine/narration/review.py _OK) plus nothing else.
const RESOLVED = new Set(["passed", "repaired", "fallback"]);

export interface NarrationReviewQueueProps {
  items: NarrationReviewItem[];
  selected: { projectId: string; runId: string } | null;
  run: NarrationRunDetail | null;
  imageUrl: (projectId: string, panelId: string) => string;
  onSelectRun: (projectId: string, runId: string) => void;
  onLineAction: (line: NarrationLine, request: NarrationLineActionRequest) => void;
  onApprove: () => void;
  /** line_id -> server rejection reasons */
  errors: Record<string, string[]>;
  /** line_id -> true while a regenerate job runs */
  busy: Record<string, boolean>;
  /** 0..1 while the continue job runs, null/undefined otherwise */
  approveProgress?: number | null;
}

const LineCard: React.FC<{
  line: NarrationLine;
  imageUrl: string;
  errors: string[];
  regenerating: boolean;
  onAction: (request: NarrationLineActionRequest) => void;
}> = ({ line, imageUrl, errors, regenerating, onAction }) => {
  const [draft, setDraft] = useState(line.text);
  const [hint, setHint] = useState("");
  return (
    <li className="flex gap-3 p-3 rounded-xl border border-zinc-800 bg-zinc-950">
      <img src={imageUrl} alt={`Panel ${line.panel_id}`} className="w-28 h-28 object-contain rounded bg-zinc-900 shrink-0" />
      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-500">
          <span>{line.line_id}</span>
          <span className="uppercase font-bold text-amber-400">{line.status}</span>
        </div>
        <textarea
          aria-label={`Edit text for ${line.line_id}`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-100"
        />
        {errors.length > 0 && (
          <ul role="alert" className="text-xs text-red-400 list-disc pl-4">
            {errors.map((r) => <li key={r}>{r}</li>)}
          </ul>
        )}
        <ul className="text-[11px] space-y-0.5">
          {line.checks.filter((c) => !c.passed).map((c) => (
            <li key={c.rule} className={c.severity === "block" ? "text-red-400" : "text-amber-400"}>
              <span className="font-bold uppercase">{c.severity}</span> {c.rule}: {c.reason}
            </li>
          ))}
        </ul>
        <p className="text-[11px] text-zinc-500 font-mono">{line.facts}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" aria-label={`Accept ${line.line_id}`} onClick={() => onAction({ action: "accept" })}>Accept</Button>
          <Button size="sm" variant="secondary" aria-label={`Save edit for ${line.line_id}`} onClick={() => onAction({ action: "edit", text: draft })}>Edit</Button>
          <Button size="sm" variant="secondary" aria-label={`Use fallback for ${line.line_id}`} onClick={() => onAction({ action: "fallback" })}>Fallback</Button>
          <input
            aria-label={`Regenerate hint for ${line.line_id}`}
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            placeholder="Hint"
            className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-100"
          />
          <Button size="sm" variant="secondary" disabled={regenerating} aria-label={`Regenerate ${line.line_id}`} onClick={() => onAction({ action: "regenerate", hint })}>
            {regenerating ? "regenerating…" : "Regenerate"}
          </Button>
        </div>
      </div>
    </li>
  );
};

export const NarrationReviewQueue: React.FC<NarrationReviewQueueProps> = ({
  items, selected, run, imageUrl, onSelectRun, onLineAction, onApprove, errors, busy, approveProgress,
}) => {
  const byProject = new Map<string, NarrationReviewItem[]>();
  for (const it of items) byProject.set(it.project_id, [...(byProject.get(it.project_id) ?? []), it]);
  const lines = run?.lines.filter((l) => l.status !== "passed" && l.status !== "repaired") ?? [];
  const blocked = (run?.lines ?? []).some((l) => !RESOLVED.has(l.status));

  return (
    <div className="flex h-full min-h-0 text-zinc-100">
      <nav aria-label="Pending runs" className="w-72 shrink-0 border-r border-zinc-800 overflow-y-auto p-3 space-y-4">
        {items.length === 0 && <p className="text-xs text-zinc-500">Nothing waiting for review.</p>}
        {[...byProject].map(([pid, runs]) => (
          <section key={pid}>
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-300 mb-1">{runs[0].project_title}</h3>
            <ul className="space-y-1">
              {runs.map((r) => (
                <li key={r.run_id}>
                  <button
                    type="button"
                    aria-label={`Open run ${r.run_id}`}
                    onClick={() => onSelectRun(pid, r.run_id)}
                    className={`w-full text-left p-2 rounded-lg border text-xs ${selected?.runId === r.run_id ? "border-indigo-500 bg-zinc-900" : "border-zinc-800 hover:border-zinc-700"}`}
                  >
                    <span className="block font-mono text-[10px] text-zinc-500">{r.created}</span>
                    {r.reasons.map((reason) => <span key={reason} className="block text-zinc-300">{reason}</span>)}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </nav>
      <div className="flex-1 min-w-0 overflow-y-auto p-4 space-y-3">
        {run ? (
          <>
            <div className="flex items-center gap-3">
              <Button
                variant="primary"
                size="sm"
                aria-label="Approve chapter"
                disabled={blocked || approveProgress != null}
                onClick={onApprove}
              >
                Approve chapter
              </Button>
              {approveProgress != null && <ProgressBar progress={approveProgress} label="Continuing" className="max-w-xs" />}
            </div>
            <ul className="space-y-3">
              {lines.map((l) => (
                <LineCard
                  key={l.line_id}
                  line={l}
                  imageUrl={imageUrl(selected!.projectId, l.panel_id)}
                  errors={errors[l.line_id] ?? []}
                  regenerating={!!busy[l.line_id]}
                  onAction={(req) => onLineAction(l, req)}
                />
              ))}
            </ul>
          </>
        ) : (
          <p className="text-xs text-zinc-500">Select a run to review its lines.</p>
        )}
      </div>
    </div>
  );
};
