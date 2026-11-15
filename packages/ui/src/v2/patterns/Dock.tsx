import React from "react";
import { cx } from "../cx";
import { FOCUS_RING } from "../primitives/Button";

export interface DockItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  href: string;
}

export interface DockProps {
  items: DockItem[];
  activeId: string;
  /** The shell passes router links here so navigation stays client-side. */
  renderLink?: (item: DockItem, children: React.ReactNode) => React.ReactElement;
}

export const Dock: React.FC<DockProps> = ({ items, activeId, renderLink }) => (
  <nav aria-label="Main" className="mx-auto flex w-fit gap-1.5 rounded-card border border-edge bg-glass p-2 backdrop-blur-md">
    {items.map((item) => {
      const active = item.id === activeId;
      const inner = (
        <>
          <span aria-hidden="true" className="grid size-5 place-items-center">{item.icon}</span>
          <span className="text-[11px] font-medium">{item.label}</span>
        </>
      );
      const className = cx(
        "flex min-w-[68px] flex-col items-center gap-0.5 rounded-ctl px-3 py-2 transition-colors duration-(--duration-fast)",
        active ? "bg-accent-soft text-fg shadow-[0_0_24px_var(--color-accent-soft)] ring-1 ring-accent/60" : "text-fg-faint hover:text-fg",
        FOCUS_RING,
      );
      const props = { "aria-current": active ? ("page" as const) : undefined, className };
      return renderLink ? (
        React.cloneElement(renderLink(item, inner), { key: item.id, ...props })
      ) : (
        <a key={item.id} href={item.href} {...props}>{inner}</a>
      );
    })}
  </nav>
);
