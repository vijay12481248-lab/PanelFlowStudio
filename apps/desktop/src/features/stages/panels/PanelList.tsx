import React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { Panel } from "@panelflow/shared-types";
import { Button, Chip, GlassPanel, IconButton } from "@panelflow/ui-v2";
import { boxesOverlap } from "../kit/canvas/geometry";
import { panelStatus } from "./panelsModel";

export interface PanelListProps {
  panels: Panel[];
  selectedId: string | null;
  mergeIds: string[];
  busy: boolean;
  onSelect: (id: string) => void;
  onToggleMerge: (id: string) => void;
  onMove: (index: number, delta: -1 | 1) => void;
  onMerge: () => void;
}

const box = (p: Panel) => ({ x: p.x, y: p.y, w: p.width, h: p.height });

/** The page's panels in reading order: select, choose for merging, and move earlier or later. */
export const PanelList: React.FC<PanelListProps> = ({ panels, selectedId, mergeIds, busy, onSelect, onToggleMerge, onMove, onMerge }) => (
  <GlassPanel blur={false} className="grid grid-cols-1 content-start gap-3 p-4" aria-label="Panels on this page">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="font-display text-sm font-semibold text-fg">{`Panels on this page (${panels.length})`}</h3>
      <Button size="sm" variant="secondary" disabled={mergeIds.length < 2 || busy} onClick={onMerge}>{`Merge selected (${mergeIds.length})`}</Button>
    </div>
    {mergeIds.length < 2 && <p className="text-xs text-fg-faint">Choose at least two panels to merge.</p>}
    <ol className="grid gap-1.5">
      {panels.map((p, index) => {
        const overlaps = panels.filter((o) => o.id !== p.id && p.status !== "IGNORED" && o.status !== "IGNORED" && boxesOverlap(box(p), box(o)) > 0.8);
        const status = panelStatus(p.status);
        return (
          <li key={p.id} data-list-panel={p.id} className={`flex flex-wrap items-center gap-2 rounded-ctl border p-2 ${p.id === selectedId ? "border-accent" : "border-edge"}`}>
            <input type="checkbox" aria-label={`Merge panel ${p.page_sequence}`} checked={mergeIds.includes(p.id)} onChange={() => onToggleMerge(p.id)} />
            <Button size="sm" variant="ghost" aria-label={`Select panel ${p.page_sequence}`} onClick={() => onSelect(p.id)}>{`Panel ${p.page_sequence}`}</Button>
            <Chip tone={status.tone}>{status.word}</Chip>
            <span className="font-data text-xs text-fg-faint">{`${p.width}×${p.height}`}</span>
            {overlaps.length > 0 && <Chip tone="warn">{`Overlaps panel ${overlaps[0].page_sequence}`}</Chip>}
            <span className="ml-auto flex gap-1">
              <IconButton label={`Move panel ${p.page_sequence} earlier`} className="size-7" disabled={index === 0 || busy} onClick={() => onMove(index, -1)}><ChevronUp size={14} /></IconButton>
              <IconButton label={`Move panel ${p.page_sequence} later`} className="size-7" disabled={index === panels.length - 1 || busy} onClick={() => onMove(index, 1)}><ChevronDown size={14} /></IconButton>
            </span>
          </li>
        );
      })}
    </ol>
  </GlassPanel>
);
