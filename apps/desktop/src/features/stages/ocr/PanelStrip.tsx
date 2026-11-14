import React from "react";
import { api } from "@panelflow/api-client";
import type { Panel, TextRegion } from "@panelflow/shared-types";
import { Button, Chip, cx } from "@panelflow/ui-v2";
import { type PanelFilter, regionsByPanel } from "./ocrModel";

const WINDOW = 60;
const FILTERS: Array<{ id: PanelFilter; label: string }> = [
  { id: "all", label: "All" }, { id: "needs_review", label: "Needs review" }, { id: "has_text", label: "Has text" }, { id: "no_text", label: "No text" },
];

export interface PanelStripProps {
  projectId: string;
  /** The panels the filter keeps, in reading order. */
  panels: Panel[];
  regions: TextRegion[];
  counts: Record<PanelFilter, number>;
  filter: PanelFilter;
  onFilter: (filter: PanelFilter) => void;
  activeId: string | null;
  cropBuster: number;
  onSelect: (panelId: string) => void;
  onDelete: (panel: Panel) => void;
  /** Select the panel with this number. Returns false when there is none. */
  onJump: (sequence: number) => boolean;
}

/** The panels as a row of thumbnails, filterable. Only a window of them is drawn: real projects have up to 625 panels. */
export const PanelStrip: React.FC<PanelStripProps> = ({ projectId, panels, regions, counts, filter, onFilter, activeId, cropBuster, onSelect, onDelete, onJump }) => {
  const [limit, setLimit] = React.useState(WINDOW);
  const [jump, setJump] = React.useState("");
  const [missing, setMissing] = React.useState<number | null>(null);
  const grouped = React.useMemo(() => regionsByPanel(regions), [regions]);
  const shown = panels.slice(0, limit);
  const active = activeId ? panels.find((p) => p.id === activeId) : undefined;
  if (active && !shown.includes(active)) shown.push(active); // the selected panel is always drawn

  const go = () => {
    const n = Number(jump);
    if (!Number.isInteger(n) || n < 1) return;
    if (onJump(n)) { setJump(""); setMissing(null); } else setMissing(n);
  };

  return (
    <div data-panel-strip className="grid min-w-0 gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <Button key={f.id} size="sm" variant={filter === f.id ? "primary" : "secondary"} aria-pressed={filter === f.id} onClick={() => onFilter(f.id)}>
            <span>{f.label}</span><span className="ml-1.5 font-data text-xs opacity-80">{counts[f.id]}</span>
          </Button>
        ))}
        <span className="ml-auto flex items-center gap-2">
          <input aria-label="Jump to panel" inputMode="numeric" placeholder="Panel number" value={jump} onChange={(e) => { setJump(e.target.value); setMissing(null); }} onKeyDown={(e) => { if (e.key === "Enter") go(); }} className="h-9 w-32 rounded-ctl border border-edge bg-glass px-3 text-sm text-fg" />
          <Button size="sm" variant="secondary" onClick={go}>Go</Button>
        </span>
      </div>
      {missing !== null && <p role="alert" className="text-sm text-bad">{`There is no panel ${missing}.`}</p>}
      {panels.length === 0 && <p className="text-sm text-fg-dim">No panels match this filter.</p>}
      <ul className="flex gap-3 overflow-x-auto pb-2">
        {shown.map((p) => {
          const own = grouped[p.id] ?? [];
          const flagged = own.some((r) => r.status === "NEEDS_REVIEW");
          const isActive = p.id === activeId;
          return (
            <li key={p.id} data-strip-panel={p.id} aria-current={isActive ? "true" : undefined} className={cx("relative grid w-28 shrink-0 gap-1 rounded-ctl border p-1.5", isActive ? "border-accent bg-accent/10" : "border-edge")}>
              <button type="button" aria-label={`Select panel ${p.sequence}`} onClick={() => onSelect(p.id)} className="grid gap-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-accent">
                <img src={`${api.getPanelImageUrl(projectId, p.id)}?t=${cropBuster}`} alt="" loading="lazy" className="h-20 w-full rounded-ctl bg-ink object-cover object-top" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
                <span className="text-xs font-medium text-fg">{`Panel ${p.sequence}`}</span>
                <span className="text-[11px] text-fg-dim">{`${own.length} ${own.length === 1 ? "region" : "regions"}`}</span>
              </button>
              {flagged && <Chip tone="warn">Needs review</Chip>}
              <button type="button" aria-label={`Delete panel ${p.sequence}`} onClick={() => onDelete(p)} className="absolute right-1 top-1 grid size-6 place-items-center rounded-full bg-ink/80 text-xs text-fg-dim hover:text-bad focus-visible:ring-2 focus-visible:ring-accent">×</button>
            </li>
          );
        })}
      </ul>
      {limit < panels.length && <div><Button size="sm" variant="secondary" onClick={() => setLimit((n) => n + WINDOW)}>Show more panels</Button></div>}
    </div>
  );
};
