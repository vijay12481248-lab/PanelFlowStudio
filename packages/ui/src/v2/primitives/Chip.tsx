import React from "react";
import { cx } from "../cx";

export type Tone = "neutral" | "accent" | "ok" | "warn" | "bad";

const TONE: Record<Tone, string> = {
  neutral: "text-fg-dim bg-glass border-edge",
  accent: "text-info bg-accent-soft border-accent/40",
  ok: "text-ok bg-ok/10 border-ok/30",
  warn: "text-warn bg-warn/10 border-warn/30",
  bad: "text-bad bg-bad/10 border-bad/30",
};

export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  icon?: React.ReactNode;
}

export const Chip: React.FC<ChipProps> = ({ tone = "neutral", icon, className, children, ...rest }) => (
  <span
    {...rest}
    className={cx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-data text-xs", TONE[tone], className)}
  >
    {icon}
    {children}
  </span>
);
