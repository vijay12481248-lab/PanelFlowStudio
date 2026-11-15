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
  audioUrl: (projectId: string, runId: string, lineId: string) => string;
  /** shown when the queue or run could not be loaded */
  loadError?: string | null;
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
  audioSrc: string | null;
  errors: string[];
  regenerating: boolean;
  onAction: (request: NarrationLineActionRequest) => void;
}> = ({ line, imageUrl, audioSrc, errors, regenerating, onAction }) => {
  const [draft, setDraft] = useState(line.text);
  const [hint, setHint] = useState("");
  return (
    <li className="flex gap-3 p-3 rounded-xl border border-edge bg-ink">
      <img src={imageUrl} alt={`Panel ${line.panel_id}`} className="w-28 h-28 object-contain rounded bg-navy shrink-0" />
      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-center gap-2 text-[10px] font-mono text-fg-faint">
          <span>{line.line_id}</span>
          <span className="uppercase font-bold text-warn">{line.status}</span>
        </div>
        <textarea
          aria-label={`Edit text for ${line.line_id}`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          className="w-full bg-navy border border-edge rounded-lg p-2 text-xs text-fg"
        />
        {errors.length > 0 && (
          <ul role="alert" className="text-xs text-bad list-disc pl-4">
            {errors.map((r) => <li key={r}>{r}</li>)}
          </ul>
        )}
        <ul className="text-[11px] space-y-0.5">
          {line.checks.filter((c) => !c.passed).map((c) => (
            <li key={c.rule} className={c.severity === "block" ? "text-bad" : "text-warn"}>
              <span className="font-bold uppercase">{c.severity}</span> {c.rule}: {c.reason}
            </li>
          ))}
        </ul>
        <p className="text-[11px] text-fg-faint font-mono">{line.facts}</p>
        {audioSrc && (
          <div className="flex items-center gap-2 text-[11px] text-fg-dim">
            <audio controls preload="none" src={audioSrc} aria-label={`Listen to ${line.line_id}`} />
            {line.take?.flagged && <span className="text-warn">flagged: heard “{line.take.stt_text}”</span>}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" aria-label={`Accept ${line.line_id}`} onClick={() => onAction({ action: "accept" })}>Accept</Button>
          <Button size="sm" variant="secondary" aria-label={`Save edit for ${line.line_id}`} onClick={() => onAction({ action: "edit", text: draft })}>Edit</Button>
          <Button size="sm" variant="secondary" aria-label={`Use fallback for ${line.line_id}`} onClick={() => onAction({ action: "fallback" })}>Fallback</Button>
          <input
            aria-label={`Regenerate hint for ${line.line_id}`}
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            placeholder="Hint"
            className="bg-navy border border-edge rounded px-2 py-1 text-xs text-fg"
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
  items, selected, run, imageUrl, audioUrl, loadError, onSelectRun, onLineAction, onApprove, errors, busy, approveProgress,
}) => {
  const byProject = new Map<string, NarrationReviewItem[]>();
  for (const it of items) byProject.set(it.project_id, [...(byProject.get(it.project_id) ?? []), it]);
  const flagged = new Set(run?.review?.line_ids ?? []);
  // blocked lines, plus passed lines the owner should hear first (a flagged take or a review reason)
  const lines = run?.lines.filter((l) => (l.status !== "passed" && l.status !== "repaired") || l.take?.flagged || flagged.has(l.line_id)) ?? [];
  const blocked = (run?.lines ?? []).some((l) => !RESOLVED.has(l.status));

  return (
    <div className="flex h-full min-h-0 text-fg">
      <nav aria-label="Pending runs" className="w-72 shrink-0 border-r border-edge overflow-y-auto p-3 space-y-4">
        {items.length === 0 && <p className="text-xs text-fg-faint">Nothing waiting for review.</p>}
        {[...byProject].map(([pid, runs]) => (
          <section key={pid}>
            <h3 className="text-xs font-bold uppercase tracking-wider text-fg-dim mb-1">{runs[0].project_title}</h3>
            <ul className="space-y-1">
              {runs.map((r) => (
                <li key={r.run_id}>
                  <button
                    type="button"
                    aria-label={`Open run ${r.run_id}`}
                    onClick={() => onSelectRun(pid, r.run_id)}
                    className={`w-full text-left p-2 rounded-lg border text-xs ${selected?.runId === r.run_id ? "border-accent bg-navy" : "border-edge hover:border-edge"}`}
                  >
                    <span className="block font-mono text-[10px] text-fg-faint">{r.created}</span>
                    {r.reasons.map((reason) => <span key={reason} className="block text-fg-dim">{reason}</span>)}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </nav>
      <div className="flex-1 min-w-0 overflow-y-auto p-4 space-y-3">
        {loadError && <p role="alert" className="text-xs text-bad">{loadError}</p>}
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
            {(errors.approve ?? []).length > 0 && (
              <ul role="alert" aria-label="Approve errors" className="text-xs text-bad list-disc pl-4">
                {errors.approve.map((r) => <li key={r}>{r}</li>)}
              </ul>
            )}
            <ul className="space-y-3">
              {lines.map((l) => (
                <LineCard
                  key={`${l.line_id}:${l.text}`}
                  line={l}
                  imageUrl={imageUrl(selected!.projectId, l.panel_id)}
                  audioSrc={l.take ? audioUrl(selected!.projectId, selected!.runId, l.line_id) : null}
                  errors={errors[l.line_id] ?? []}
                  regenerating={!!busy[l.line_id]}
                  onAction={(req) => onLineAction(l, req)}
                />
              ))}
            </ul>
          </>
        ) : (
          <p className="text-xs text-fg-faint">Select a run to review its lines.</p>
        )}
      </div>
    </div>
  );
};
