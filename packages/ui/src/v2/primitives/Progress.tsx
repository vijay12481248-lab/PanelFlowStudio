import React from "react";
import { cx } from "../cx";

export const Progress: React.FC<{ value: number; label: string; className?: string }> = ({ value, label, className }) => {
  const pct = Math.round(Math.min(100, Math.max(0, value)));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className={cx("h-1.5 overflow-hidden rounded-full bg-fg/10", className)}
    >
      <div className="h-full rounded-full bg-accent transition-[width] duration-(--duration-base)" style={{ width: `${pct}%` }} />
    </div>
  );
};
