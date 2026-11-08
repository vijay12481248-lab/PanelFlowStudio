import React from "react";
import type { CharacterEntity, ScriptSegment, ScriptValidationReport } from "@panelflow/shared-types";
import { Chip, GlassPanel } from "@panelflow/ui-v2";
import { issueFor, reasonsFor, speakerName } from "./scriptModel";

export interface SpokenListProps {
  segments: ScriptSegment[];
  characters: CharacterEntity[];
  report: ScriptValidationReport | null;
  unsupportedOnly: boolean;
}

const STATUS = { SUPPORTED: "Supported", WEAKLY_SUPPORTED: "Weakly supported", UNSUPPORTED: "Unsupported" } as const;

/** The script as spoken lines. */
export const SpokenList: React.FC<SpokenListProps> = ({ segments, characters, report, unsupportedOnly }) => {
  const rows = unsupportedOnly ? segments.filter((s) => issueFor(report, s.segment_id) || s.faithfulness_status === "UNSUPPORTED") : segments;
  return (
    <ol className="grid grid-cols-1 gap-3" aria-label="Spoken script">
      {rows.map((seg) => {
        const issue = issueFor(report, seg.segment_id);
        const unsupported = Boolean(issue) || seg.faithfulness_status === "UNSUPPORTED";
        return (
          <li key={seg.segment_id} data-segment-id={seg.segment_id} id={`seg-${seg.segment_id}`}>
            <GlassPanel blur={false} className={`grid gap-2 p-4 ${unsupported ? "border-bad/50" : ""}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-info">{`#${seg.sequence}`}</span>
                <Chip tone={seg.type === "NARRATOR" ? "neutral" : "accent"}>{seg.type}</Chip>
                <span className="text-sm font-medium text-fg">{speakerName(seg, characters)}</span>
                <Chip tone={unsupported ? "bad" : seg.faithfulness_status === "WEAKLY_SUPPORTED" ? "warn" : "ok"}>{unsupported ? "Unsupported" : STATUS[seg.faithfulness_status] ?? seg.faithfulness_status}</Chip>
              </div>
              <p className="text-sm text-fg">{`"${seg.text}"`}</p>
              {unsupported && (
                <ul className="grid gap-0.5 text-xs text-bad">
                  {reasonsFor(issue ?? {}).map((reason, i) => <li key={i}>{`• ${reason}`}</li>)}
                </ul>
              )}
            </GlassPanel>
          </li>
        );
      })}
    </ol>
  );
};
