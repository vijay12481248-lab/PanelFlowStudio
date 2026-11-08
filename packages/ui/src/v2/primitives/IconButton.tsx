import React from "react";
import { cx } from "../cx";
import { FOCUS_RING } from "./Button";

export interface IconButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  /** Required: becomes the accessible name. */
  label: string;
}

export const IconButton: React.FC<IconButtonProps> = ({ label, className, children, type = "button", ...rest }) => (
  <button
    type={type}
    {...rest}
    aria-label={label}
    className={cx(
      "inline-grid size-9 place-items-center rounded-full border border-edge bg-glass text-fg-dim transition-colors duration-(--duration-fast) hover:text-fg hover:bg-glass-hi disabled:opacity-50",
      FOCUS_RING,
      className,
    )}
  >
    {children}
  </button>
);
