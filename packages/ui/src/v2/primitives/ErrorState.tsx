import React from "react";
import { Button } from "./Button";

export interface ErrorStateProps {
  title: string;
  /** A sentence saying what happened and what to do. Never a raw exception. */
  description: string;
  onRetry?: () => void;
  onBack?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ title, description, onRetry, onBack }) => (
  <div role="alert" className="grid justify-items-center gap-2 px-6 py-10 text-center">
    <h3 className="font-display text-base font-semibold text-bad">{title}</h3>
    <p className="max-w-[44ch] text-sm text-fg-dim">{description}</p>
    {(onRetry || onBack) && (
      <div className="mt-2 flex gap-2">
        {onRetry && <Button variant="primary" onClick={onRetry}>Retry</Button>}
        {onBack && <Button variant="secondary" onClick={onBack}>Go back</Button>}
      </div>
    )}
  </div>
);
