import React from "react";
import type { ScriptSegment } from "@panelflow/shared-types";
import type { CharacterEntity } from "@panelflow/shared-types";
import { Button, Chip, GlassPanel } from "@panelflow/ui-v2";
import { reasonsFor, speakerName, type ReportIssue } from "./scriptModel";

export interface UnsupportedBannerProps {
  issues: ReportIssue[];
  segments: ScriptSegment[];
  characters: CharacterEntity[];
  filterOn: boolean;
  onToggleFilter: () => void;
  onEdit: (segmentId: string) => void;
  /** The script is already approved: the statements are reported, but nothing is blocked. */
  approved?: boolean;
}

/** Lines the faithfulness check could not ground in the source. They block approval until fixed. */
export const UnsupportedBanner: React.FC<UnsupportedBannerProps> = ({ issues, segments, characters, filterOn, onToggleFilter, onEdit, approved }) => {
  const n = issues.length;
  return (
    <GlassPanel blur={false} data-unsupported-banner className="grid grid-cols-1 gap-3 border-bad/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className={`font-display text-sm font-semibold ${approved ? "text-warn" : "text-bad"}`}>{approved ? `${n} unsupported statement${n === 1 ? "" : "s"} found` : `${n} unsupported statement${n === 1 ? " blocks" : "s block"} approval`}</h3>
        <Button size="sm" variant={filterOn ? "primary" : "secondary"} aria-pressed={filterOn} onClick={onToggleFilter}>Show unsupported only</Button>
      </div>
      <p className="text-sm text-fg-dim">{approved
        ? "The check found statements without enough support in the source panels, text or characters. This script is already approved, so editing a line here changes the approved script."
        : "The check found statements without enough support in the source panels, text or characters. Fix or remove these lines to unlock approval."}</p>
      <ul className="grid gap-2">
        {issues.map((issue, i) => {
          const segment = segments.find((s) => s.segment_id === issue.segment_id);
          return (
            <li key={issue.segment_id ?? i} className="grid gap-2 rounded-ctl border border-edge bg-glass p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-fg">{`Statement ${segment?.sequence ?? issue.sequence ?? i + 1}`}</span>
                <Chip>{segment?.type ?? "LINE"}</Chip>
                {segment && <span className="text-fg-dim">{speakerName(segment, characters)}</span>}
                {issue.segment_id && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => onEdit(issue.segment_id as string)}>Edit this line</Button>}
              </div>
              <p className="font-data text-fg">{`"${issue.text ?? segment?.text ?? ""}"`}</p>
              <ul className="grid gap-0.5 text-xs text-fg-dim">{reasonsFor(issue).map((reason, r) => <li key={r}>{`• ${reason}`}</li>)}</ul>
            </li>
          );
        })}
      </ul>
    </GlassPanel>
  );
};
