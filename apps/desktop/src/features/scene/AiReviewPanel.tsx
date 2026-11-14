import React from "react";
import type { SceneRun } from "@panelflow/api-client";
import { Chip, GlassPanel } from "@panelflow/ui-v2";
import { itemRows, type ItemRow } from "./sceneView";

const TONE: Record<ItemRow["status"], "ok" | "accent" | "warn" | "bad" | "neutral"> = { agreed: "ok", resolved: "accent", single: "neutral", disputed: "warn", unjudged: "bad" };

const Row: React.FC<{ row: ItemRow }> = ({ row }) => (
  <li
    data-status={row.status}
    data-highlight={row.highlight ? "true" : "false"}
    className={`grid gap-1 rounded-ctl border px-3 py-2 ${row.highlight ? "border-warn/70 bg-warn/10" : "border-edge bg-glass"}`}
  >
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm font-semibold text-fg">{row.label}</span>
      <span className="text-sm text-fg">{row.valueText}</span>
      <Chip tone={TONE[row.status]}>{row.statusText}</Chip>
      <Chip>{row.confidencePct}% sure ({row.confidence})</Chip>
    </div>
    {row.perJudge.length > 0 && (row.status !== "agreed" || row.perJudge.some((j) => j.evidence)) && (
      <ul className="grid gap-0.5 text-xs text-fg-dim">
        {row.perJudge.map((j) => (
          <li key={j.judge}>
            <span className="font-data text-fg">{j.judge}</span>: {j.round1 ?? "no answer"}
            {j.round2 !== null && j.round2 !== j.round1 ? ` → ${j.round2}` : ""}
            {j.evidence ? ` (${j.evidence})` : ""}
          </li>
        ))}
      </ul>
    )}
    {row.flipped.length > 0 && <p className="text-xs text-warn">{row.flipped.join(", ")} changed its answer without giving a new reason: treat this with care.</p>}
  </li>
);

/** What the two vision judges (and the system's own check) said about the picture. */
export const AiReviewPanel: React.FC<{ run: SceneRun }> = ({ run }) => {
  const analysis = run.analysis ?? null;
  const rows = analysis ? itemRows(analysis.crosscheck as never) : [];
  const unmet = run.system_review?.unmet ?? [];
  return (
    <GlassPanel className="grid gap-3 p-4" aria-label="AI review">
      <h2 className="font-display text-base font-semibold text-fg">What the AI judges saw</h2>
      {!analysis && <p className="text-sm text-fg-dim">The two vision models are still looking at this picture. This page updates by itself.</p>}
      {analysis && (analysis.error || rows.length === 0) && (
        <p className="text-sm text-bad">The AI review could not be made{analysis.error ? `: ${analysis.error}` : "."} Your own verdict is all the more useful.</p>
      )}
      {analysis && !analysis.error && analysis.single_judge && (
        <p className="text-sm text-warn">Only one judge could look at this picture, so nothing was cross-checked.</p>
      )}
      {rows.length > 0 && <ul className="grid gap-2">{rows.map((r) => <Row key={r.key} row={r} />)}</ul>}
      <p className="text-xs text-fg-dim">
        The system drew it in {run.attempts} attempt{run.attempts === 1 ? "" : "s"} ({Math.round(run.seconds)} s).
        {unmet.length > 0 ? ` Its own check says this is still missing: ${unmet.join("; ")}.` : " Its own check found nothing missing."}
      </p>
    </GlassPanel>
  );
};
