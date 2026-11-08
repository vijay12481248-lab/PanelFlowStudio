import React from "react";

export const EmptyState: React.FC<{ title: string; description?: string; action?: React.ReactNode }> = ({ title, description, action }) => (
  <div className="grid justify-items-center gap-2 px-6 py-10 text-center">
    <h3 className="font-display text-base font-semibold text-fg">{title}</h3>
    {description && <p className="max-w-[44ch] text-sm text-fg-dim">{description}</p>}
    {action && <div className="mt-2">{action}</div>}
  </div>
);
