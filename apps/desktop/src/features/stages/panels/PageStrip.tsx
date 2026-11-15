import React from "react";
import type { Page } from "@panelflow/shared-types";
import { cx, FOCUS_RING } from "@panelflow/ui-v2";
import { pageWindow } from "./panelsModel";

export interface PageStripProps {
  pages: Page[];
  perPage: Record<string, number>;
  selectedIndex: number;
  onSelect: (index: number) => void;
}

const WINDOW = 40;

/** The pages of the chapter. A very long chapter shows a window of pages around the one being edited. */
export const PageStrip: React.FC<PageStripProps> = ({ pages, perPage, selectedIndex, onSelect }) => {
  const { start, end } = pageWindow(pages.length, selectedIndex, WINDOW);
  return (
    <nav aria-label="Pages" className="grid gap-1.5">
      <div className="flex items-center justify-between text-xs text-fg-dim">
        <span>{`Page ${selectedIndex + 1} of ${pages.length}`}</span>
        {pages.length > WINDOW && <span>{`Showing pages ${start + 1} to ${end}. Use the arrow keys to move on.`}</span>}
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {pages.slice(start, end).map((p, i) => {
          const index = start + i;
          const count = perPage[p.id] ?? 0;
          const current = index === selectedIndex;
          return (
            <button
              key={p.id}
              type="button"
              data-page-id={p.id}
              aria-current={current ? "page" : undefined}
              onClick={() => onSelect(index)}
              className={cx("flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium", FOCUS_RING, current ? "border-accent bg-accent text-white" : "border-edge bg-glass text-fg-dim hover:text-fg")}
            >
              <span>{`Page ${p.sequence}`}</span>
              <span className="opacity-80">{`${count} ${count === 1 ? "panel" : "panels"}`}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
