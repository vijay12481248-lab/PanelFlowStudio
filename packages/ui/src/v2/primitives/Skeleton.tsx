import React from "react";
import { cx } from "../cx";

export const Skeleton: React.FC<{ className?: string }> = ({ className }) => (
  <div aria-hidden="true" className={cx("rounded-ctl bg-fg/10 motion-safe:animate-pulse", className)} />
);
