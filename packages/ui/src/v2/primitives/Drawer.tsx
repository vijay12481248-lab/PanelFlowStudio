import React from "react";
import { OverlayContent, type OverlayProps } from "./Dialog";

/** `wide` is for content that needs room, such as a page viewer. */
export const Drawer: React.FC<OverlayProps & { side?: "right" | "left"; size?: "default" | "wide" }> = ({ side = "right", size = "default", ...props }) => {
  const width = size === "wide" ? "w-[min(96vw,900px)]" : "w-[min(92vw,440px)]";
  return (
    <OverlayContent
      {...props}
      className={side === "right" ? `right-0 top-0 h-full ${width} border-y-0 border-r-0` : `left-0 top-0 h-full ${width} border-y-0 border-l-0`}
    />
  );
};
