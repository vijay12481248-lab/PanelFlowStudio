import React from "react";
import { cx } from "../cx";
import { FOCUS_RING } from "../primitives/Button";

export type StepStatus = "done" | "active" | "stale" | "blocked" | "upcoming";

export interface Step {
  id: string;
  label: string;
  status: StepStatus;
  href?: string;
  /** The step whose screen is open right now (it can differ from the one in progress). */
  viewed?: boolean;
}

export interface StepperProps {
  steps: Step[];
  /** The shell passes router links here so navigation stays client-side. */
  renderLink?: (step: Step, children: React.ReactNode) => React.ReactElement;
}

const WORD: Record<StepStatus, string> = { done: "Done", active: "In progress", stale: "Stale", blocked: "Blocked", upcoming: "Not started" };
const STYLE: Record<StepStatus, string> = {
  done: "text-ok border-ok/30",
  active: "text-white bg-accent border-transparent shadow-lg shadow-accent/30",
  stale: "text-warn border-warn/40",
  blocked: "text-bad border-bad/40",
  upcoming: "text-fg-faint border-edge",
};

export const Stepper: React.FC<StepperProps> = ({ steps, renderLink }) => {
  // aria-current marks the screen being viewed; when none is marked it falls back to the step in progress.
  const currentId = steps.find((s) => s.viewed)?.id ?? steps.find((s) => s.status === "active")?.id;
  return (
    <ol aria-label="Pipeline stages" className="flex flex-wrap items-center gap-1.5">
      {steps.map((step) => {
        const body = (
          <>
            <span>{step.label}</span>
            <span className="sr-only">{`: ${WORD[step.status]}${step.viewed ? ", viewing" : ""}`}</span>
            {(step.status === "stale" || step.status === "blocked") && <span aria-hidden="true" className="text-[11px]">{WORD[step.status]}</span>}
          </>
        );
        const className = cx(
          "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[13px] font-medium",
          STYLE[step.status],
          step.viewed && "ring-2 ring-info ring-offset-2 ring-offset-ink",
          step.href && FOCUS_RING,
        );
        let content: React.ReactNode;
        if (!step.href) content = <span className={className}>{body}</span>;
        else if (renderLink) content = React.cloneElement(renderLink(step, body), { className });
        else content = <a href={step.href} className={className}>{body}</a>;
        return <li key={step.id} aria-current={step.id === currentId ? "step" : undefined}>{content}</li>;
      })}
    </ol>
  );
};
