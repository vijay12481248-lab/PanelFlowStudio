import React from "react";
import { cx } from "../cx";

export interface GlassPanelProps extends React.HTMLAttributes<HTMLElement> {
  as?: React.ElementType;
  /** Blur only on hub surfaces: false gives the flat workbench surface. */
  blur?: boolean;
}

export const GlassPanel: React.FC<GlassPanelProps> = ({ as: Tag = "div", blur = true, className, children, ...rest }) => (
  <Tag
    {...rest}
    className={cx(
      "rounded-card border border-edge",
      blur ? "bg-glass backdrop-blur-md" : "bg-flat",
      className,
    )}
  >
    {children}
  </Tag>
);
