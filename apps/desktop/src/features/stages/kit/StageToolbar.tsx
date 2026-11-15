import React from "react";

export interface StageToolbarProps {
  title: string;
  description?: string;
  /** Status chips or text beside the title. */
  status?: React.ReactNode;
  actions?: React.ReactNode;
}

/** The title row of a stage. The workbench frame owns the page's h1, so this is an h2. */
export const StageToolbar: React.FC<StageToolbarProps> = ({ title, description, status, actions }) => (
  <div className="flex flex-wrap items-start justify-between gap-3">
    <div className="grid min-w-0 gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-display text-lg font-semibold text-fg">{title}</h2>
        {status}
      </div>
      {description && <p className="max-w-[70ch] text-sm text-fg-dim">{description}</p>}
    </div>
    {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
  </div>
);
