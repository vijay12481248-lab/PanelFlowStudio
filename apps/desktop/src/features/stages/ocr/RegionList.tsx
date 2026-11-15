import React from "react";
import type { TextRegion } from "@panelflow/shared-types";
import { Button, Chip, cx } from "@panelflow/ui-v2";
import { regionStatus, regionTypeWord } from "./ocrModel";

const textOf = (r: TextRegion) => ((r.corrected_text ?? "").trim() ? r.corrected_text! : (r.raw_text ?? "")).trim();

/** The active panel's regions, each with its status and a one-line preview. */
export const RegionList: React.FC<{ regions: TextRegion[]; selectedId: string | null; onSelect: (id: string) => void }> = ({ regions, selectedId, onSelect }) => (
  <ul className="grid gap-2" aria-label="Regions in this panel">
    {regions.length === 0 && <li className="text-sm text-fg-dim">No text regions in this panel.</li>}
    {regions.map((r) => {
      const status = regionStatus(r.status);
      const preview = textOf(r);
      return (
        <li key={r.id} data-list-region={r.id} aria-current={r.id === selectedId ? "true" : undefined} className={cx("grid gap-1 rounded-ctl border p-2", r.id === selectedId ? "border-accent bg-accent/10" : "border-edge")}>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" aria-label={`Select region ${r.sequence_in_panel}`} onClick={() => onSelect(r.id)}>{`Region ${r.sequence_in_panel}`}</Button>
            <Chip tone={status.tone}>{status.word}</Chip>
            <span className="text-xs text-fg-faint">{regionTypeWord(r.region_type)}</span>
          </div>
          <p className="line-clamp-1 text-sm text-fg-dim">{preview || "No text yet"}</p>
        </li>
      );
    })}
  </ul>
);
