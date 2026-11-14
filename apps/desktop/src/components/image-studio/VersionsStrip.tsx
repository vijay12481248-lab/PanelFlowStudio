import React from "react";
import type { StudioVersion } from "./types";

/** The original and every result of this session. Click one to look at it (and edit from it). */
export const VersionsStrip: React.FC<{
  versions: StudioVersion[];
  activeKey: string | null;
  onSelect?: (key: string) => void;
  busy: boolean;
}> = ({ versions, activeKey, onSelect, busy }) => (
  <div className="flex items-center gap-2 border-t border-edge/70 bg-navy/60 px-3 py-2" aria-label="Versions">
    <span className="text-[11px] font-medium text-fg-faint">Versions</span>
    <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
      {versions.map((v) => (
        <button
          key={v.key}
          type="button"
          disabled={!onSelect || busy}
          onClick={() => onSelect?.(v.key)}
          title={v.label}
          className={`group relative h-12 w-20 shrink-0 overflow-hidden rounded-md border transition-colors ${
            activeKey === v.key ? "border-accent" : "border-edge hover:border-info/60"
          } ${!onSelect ? "cursor-default" : ""}`}
        >
          <img src={v.src} alt={v.label} className="h-full w-full object-cover" draggable={false} />
          <span className="absolute inset-x-0 bottom-0 truncate bg-ink/80 px-1 text-[10px] text-fg-dim">{v.label}</span>
        </button>
      ))}
      {busy && (
        <div className="flex h-12 w-20 shrink-0 items-center justify-center rounded-md border border-dashed border-info/50 text-[10px] text-info">
          Working…
        </div>
      )}
    </div>
  </div>
);
