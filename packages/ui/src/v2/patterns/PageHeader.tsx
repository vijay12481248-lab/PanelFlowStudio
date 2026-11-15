import React from "react";

export const PageHeader: React.FC<{ title: string; meta?: React.ReactNode; actions?: React.ReactNode }> = ({ title, meta, actions }) => (
  <header className="flex flex-wrap items-center gap-3">
    <div className="min-w-0 flex-1">
      <h1 className="truncate font-display text-[30px] font-bold leading-tight tracking-tight text-fg">{title}</h1>
      {meta && <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-fg-dim">{meta}</div>}
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </header>
);
