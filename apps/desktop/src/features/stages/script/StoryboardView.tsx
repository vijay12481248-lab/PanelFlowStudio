import React from "react";
import type { ScriptValidationReport, StoryboardSegment } from "@panelflow/shared-types";
import { Chip, GlassPanel } from "@panelflow/ui-v2";
import { issueFor, reasonsFor } from "./scriptModel";

export interface StoryboardViewProps {
  segments: StoryboardSegment[];
  report: ScriptValidationReport | null;
  unsupportedOnly: boolean;
}

/** The storyboard: each beat with its narration. */
export const StoryboardView: React.FC<StoryboardViewProps> = ({ segments, report, unsupportedOnly }) => {
  const rows = unsupportedOnly ? segments.filter((s) => issueFor(report, s.segment_id)) : segments;
  return (
    <ol className="grid grid-cols-1 gap-4" aria-label="Storyboard">
      {rows.map((seg) => {
        const issue = issueFor(report, seg.segment_id);
        return (
          <li key={seg.segment_id} data-segment-id={seg.segment_id} id={`seg-${seg.segment_id}`}>
            <GlassPanel blur={false} className={`grid gap-2 p-4 ${issue ? "border-bad/50" : ""}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-info">{`Beat ${seg.sequence}`}</span>
                <Chip>{`${seg.emotion} (${Math.round(seg.intensity * 100)}%)`}</Chip>
                {issue && <Chip tone="bad">Unsupported</Chip>}
              </div>
              <p className="text-sm text-fg">{`"${seg.text}"`}</p>
              {issue && <ul className="grid gap-0.5 text-xs text-bad">{reasonsFor(issue).map((r, i) => <li key={i}>{`• ${r}`}</li>)}</ul>}
            </GlassPanel>
          </li>
        );
      })}
    </ol>
  );
};
