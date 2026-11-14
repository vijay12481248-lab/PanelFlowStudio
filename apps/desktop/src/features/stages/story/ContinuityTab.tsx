import React from "react";
import type { ContinuityWarningEntity } from "@panelflow/shared-types";
import { Chip, EmptyState, GlassPanel } from "@panelflow/ui-v2";

const WORD = { ERROR: "Error", WARNING: "Warning", INFO: "Note" } as const;

export const ContinuityTab: React.FC<{ warnings: ContinuityWarningEntity[] }> = ({ warnings }) => {
  if (warnings.length === 0) return <GlassPanel blur={false}><EmptyState title="No continuity warnings" description="No continuity warnings. The story is consistent." /></GlassPanel>;
  return (
    <ul className="grid grid-cols-1 gap-3" aria-label="Continuity warnings">
      {warnings.map((w) => (
        <li key={w.warning_id}>
          <GlassPanel blur={false} className="grid gap-1.5 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Chip tone={w.severity === "ERROR" ? "bad" : w.severity === "WARNING" ? "warn" : "neutral"}>{WORD[w.severity] ?? w.severity}</Chip>
              <span className="text-sm font-medium text-fg">{w.warning_type}</span>
              {w.resolved && <Chip tone="ok">Resolved</Chip>}
              <span className="ml-auto font-data text-xs text-fg-faint">{`Entity ${w.entity_id}`}</span>
            </div>
            <p className="text-sm text-fg-dim">{w.message}</p>
          </GlassPanel>
        </li>
      ))}
    </ul>
  );
};
