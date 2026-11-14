import React from "react";
import { cx } from "../cx";
import { FOCUS_RING } from "./Button";

export type RowTone = "neutral" | "ok" | "warn" | "bad" | "info";

const DOT: Record<RowTone, string> = {
  neutral: "bg-fg-faint",
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  info: "bg-info",
};

// Status is read aloud (and shown on hover) as a word, so it is never colour alone.
const WORD: Record<RowTone, string | null> = {
  neutral: null,
  ok: "Ready",
  warn: "Needs attention",
  bad: "Failed",
  info: "In progress",
};

export interface ListRowProps {
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
  selected?: boolean;
  tone?: RowTone;
  action?: React.ReactNode;
  onSelect?: () => void;
  className?: string;
}

export const ListRow: React.FC<ListRowProps> = ({ icon, title, subtitle, selected, tone = "neutral", action, onSelect, className }) => {
  const word = WORD[tone];
  const body = (
    <>
      <span className="grid size-9 shrink-0 place-items-center rounded-full border border-edge bg-glass-hi">
        {icon ?? <span aria-hidden="true" className={cx("size-2.5 rounded-full", selected ? "bg-white" : DOT[tone])} />}
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block truncate text-sm font-medium">{title}</span>
        {(subtitle || word) && (
          <span className={cx("block truncate text-xs", selected ? "text-white/80" : "text-fg-faint")}>
            {word && <span className="sr-only">{word}. </span>}
            {subtitle}
          </span>
        )}
      </span>
    </>
  );
  const classes = cx(
    "flex w-full items-center gap-3 rounded-ctl border p-2 transition-colors duration-(--duration-fast)",
    selected ? "border-transparent bg-accent text-white shadow-lg shadow-accent/30" : "border-transparent text-fg hover:bg-glass",
    FOCUS_RING,
    className,
  );
  if (onSelect && !action) {
    return <button type="button" onClick={onSelect} aria-current={selected || undefined} className={cx(classes, "cursor-pointer text-left")}>{body}</button>;
  }
  return (
    <div onClick={onSelect} className={cx(classes, onSelect && "cursor-pointer select-none")}>
      {onSelect ? (
        <button type="button" onClick={(e) => { e.stopPropagation(); onSelect(); }} className="flex min-w-0 flex-1 items-center gap-3 text-left cursor-pointer focus:outline-none">
          {body}
        </button>
      ) : (
        body
      )}
      <div onClick={(e) => e.stopPropagation()} className="shrink-0">{action}</div>
    </div>
  );
};
