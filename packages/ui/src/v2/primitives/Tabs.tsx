import React from "react";
import * as RT from "@radix-ui/react-tabs";
import { FOCUS_RING } from "./Button";
import { cx } from "../cx";

export interface TabsProps {
  value: string;
  onValueChange: (value: string) => void;
  tabs: Array<{ value: string; label: string }>;
  /** The panel for the active tab. */
  children?: React.ReactNode;
}

export const Tabs: React.FC<TabsProps> = ({ value, onValueChange, tabs, children }) => (
  <RT.Root value={value} onValueChange={onValueChange}>
    <RT.List className="flex gap-1 border-b border-edge">
      {tabs.map((tab) => (
        <RT.Trigger
          key={tab.value}
          value={tab.value}
          className={cx("px-3 py-2 text-sm text-fg-dim transition-colors data-[state=active]:border-b-2 data-[state=active]:border-accent data-[state=active]:text-fg", FOCUS_RING)}
        >
          {tab.label}
        </RT.Trigger>
      ))}
    </RT.List>
    <RT.Content value={value} className="pt-4 focus:outline-none">{children}</RT.Content>
  </RT.Root>
);
