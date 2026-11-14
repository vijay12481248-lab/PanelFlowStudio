import React from "react";
import { Chip, GlassPanel } from "@panelflow/ui-v2";
import { validationSummary } from "./renderModel";

/** The render checks in words: a verdict, one row per check, and the engine's warnings. */
export const ValidationReport: React.FC<{ report: unknown }> = ({ report }) => {
  const summary = validationSummary(report);
  return (
    <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4" aria-label="Render checks">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-display text-sm font-semibold text-fg">Render checks</h3>
        <Chip tone={summary.verdict.tone}>{summary.verdict.word}</Chip>
      </div>
      {summary.rows.length > 0 && (
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {summary.rows.map((row) => (
            <div key={row.label} className="grid gap-0.5 rounded-ctl border border-edge bg-glass p-2.5">
              <dt className="text-xs text-fg-faint">{row.label}</dt>
              <dd className="flex flex-wrap items-center gap-2 text-sm text-fg"><Chip tone={row.tone}>{row.value}</Chip></dd>
              {row.note && <p className="text-xs text-fg-dim">{row.note}</p>}
            </div>
          ))}
        </dl>
      )}
      {summary.warnings.length > 0 && (
        <ul className="grid gap-1 text-sm text-warn">{summary.warnings.map((w, i) => <li key={i}>{`• ${w}`}</li>)}</ul>
      )}
    </GlassPanel>
  );
};
