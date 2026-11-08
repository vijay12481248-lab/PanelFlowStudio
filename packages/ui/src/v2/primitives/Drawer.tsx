import React from "react";
import { OverlayContent, type OverlayProps } from "./Dialog";

export const Drawer: React.FC<OverlayProps & { side?: "right" | "left" }> = ({ side = "right", ...props }) => (
  <OverlayContent
    {...props}
    className={side === "right" ? "right-0 top-0 h-full w-[min(92vw,440px)] border-y-0 border-r-0" : "left-0 top-0 h-full w-[min(92vw,440px)] border-y-0 border-l-0"}
  />
);
