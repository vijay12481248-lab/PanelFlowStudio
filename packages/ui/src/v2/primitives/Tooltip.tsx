import React from "react";
import * as RTT from "@radix-ui/react-tooltip";

export const Tooltip: React.FC<{ content: string; children: React.ReactElement }> = ({ content, children }) => (
  <RTT.Provider delayDuration={300}>
    <RTT.Root>
      <RTT.Trigger asChild>{children}</RTT.Trigger>
      <RTT.Portal>
        <RTT.Content sideOffset={6} className="z-50 rounded-lg border border-edge bg-navy px-2.5 py-1.5 text-xs text-fg shadow-lg">
          {content}
        </RTT.Content>
      </RTT.Portal>
    </RTT.Root>
  </RTT.Provider>
);
