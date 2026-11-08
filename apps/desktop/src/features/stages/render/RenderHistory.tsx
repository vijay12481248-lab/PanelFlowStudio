import React from "react";
import type { RenderJob } from "@panelflow/shared-types";
import { Button, Chip, EmptyState, GlassPanel } from "@panelflow/ui-v2";
import { outputName, renderStatus } from "./renderModel";

export interface RenderHistoryProps {
  renders: RenderJob[];
  /** Show a finished render's result. */
  onView?: (render: RenderJob) => void;
  onOpenFile: (path: string) => void;
}

const when = (iso?: string) => (iso ? new Date(iso).toLocaleString() : "");

/** Every render of the project, newest first. An out-of-date render is history only. */
export const RenderHistory: React.FC<RenderHistoryProps> = ({ renders, onView, onOpenFile }) => {
  const rows = [...renders].sort((a, b) => Date.parse(b.created_at ?? "") - Date.parse(a.created_at ?? ""));
  if (rows.length === 0) return <GlassPanel blur={false}><EmptyState title="No renders yet" description="Start a render to make the video. Each one is listed here." /></GlassPanel>;
  return (
    <ul className="grid grid-cols-1 gap-2" aria-label="Render history">
      {rows.map((r) => {
        const status = renderStatus(r.status);
        return (
          <li key={r.render_id} data-render-id={r.render_id}>
            <GlassPanel blur={false} className="flex flex-wrap items-center gap-3 p-3">
              <Chip tone={status.tone}>{status.word}</Chip>
              <span className="text-sm text-fg">{r.output_profile}</span>
              <span className="text-xs text-fg-dim">{when(r.created_at)}</span>
              {r.status === "COMPLETE" && <span className="min-w-0 truncate font-data text-xs text-fg-faint" title={r.output_path}>{outputName(r.output_path)}</span>}
              {r.status === "STALE" && <span className="text-xs text-fg-dim">Out of date: the project changed after this render.</span>}
              {r.status === "FAILED" && r.error_message && <span className="text-xs text-bad">{r.error_message}</span>}
              {r.status === "COMPLETE" && (
                <span className="ml-auto flex gap-2">
                  {onView && <Button size="sm" variant="ghost" onClick={() => onView(r)}>View</Button>}
                  <Button size="sm" variant="secondary" onClick={() => onOpenFile(r.output_path)}>Open file</Button>
                </span>
              )}
            </GlassPanel>
          </li>
        );
      })}
    </ul>
  );
};
