import React from "react";
import { cx } from "../cx";
import { FOCUS_RING } from "../primitives/Button";

export type StepStatus = "done" | "active" | "stale" | "blocked" | "upcoming";

export interface Step {
  id: string;
  label: string;
  status: StepStatus;
  href?: string;
}

const WORD: Record<StepStatus, string> = { done: "Done", active: "In progress", stale: "Stale", blocked: "Blocked", upcoming: "Not started" };
const STYLE: Record<StepStatus, string> = {
  done: "text-ok border-ok/30",
  active: "text-white bg-accent border-transparent shadow-lg shadow-accent/30",
  stale: "text-warn border-warn/40",
  blocked: "text-bad border-bad/40",
  upcoming: "text-fg-faint border-edge",
};

export const Stepper: React.FC<{ steps: Step[] }> = ({ steps }) => (
  <ol aria-label="Pipeline stages" className="flex flex-wrap items-center gap-1.5">
    {steps.map((step) => {
      const body = (
        <>
          <span>{step.label}</span>
          <span className="sr-only">{`: ${WORD[step.status]}`}</span>
          {(step.status === "stale" || step.status === "blocked") && <span aria-hidden="true" className="text-[11px]">{WORD[step.status]}</span>}
        </>
      );
      const className = cx("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[13px] font-medium", STYLE[step.status], step.href && FOCUS_RING);
      return (
        <li key={step.id} aria-current={step.status === "active" ? "step" : undefined}>
          {step.href ? <a href={step.href} className={className}>{body}</a> : <span className={className}>{body}</span>}
        </li>
      );
    })}
  </ol>
);
