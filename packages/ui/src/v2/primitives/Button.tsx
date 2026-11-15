import React from "react";
import { cx } from "../cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: React.ReactNode;
}

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white shadow-lg shadow-accent/30 hover:brightness-110",
  secondary: "bg-glass-hi text-fg border border-edge hover:bg-glass",
  ghost: "text-fg-dim hover:text-fg hover:bg-accent-soft",
  danger: "bg-bad text-ink hover:brightness-110",
};

const SIZE = { sm: "h-8 px-3 text-[13px]", md: "h-10 px-4 text-sm" } as const;

export const FOCUS_RING = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-info";

// forwardRef: Radix triggers (asChild) attach a ref to the button to anchor menus and tooltips.
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}, ref) {
  return (
  <button
    ref={ref}
    type={type}
    {...rest}
    disabled={disabled || loading}
    aria-busy={loading || undefined}
    className={cx(
      "inline-flex items-center justify-center gap-2 rounded-full font-semibold whitespace-nowrap transition-colors duration-(--duration-fast) disabled:opacity-50 disabled:cursor-not-allowed",
      FOCUS_RING,
      VARIANT[variant],
      SIZE[size],
      className,
    )}
  >
    {loading ? <span aria-hidden="true" className="size-3.5 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin" /> : icon}
    {children}
  </button>
  );
});
