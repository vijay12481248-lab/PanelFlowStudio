import React from "react";
import * as RM from "@radix-ui/react-dropdown-menu";
import { cx } from "../cx";

export interface MenuItem {
  label: string;
  onSelect: () => void;
  danger?: boolean;
}

export const Menu: React.FC<{ trigger: React.ReactNode; items: MenuItem[] }> = ({ trigger, items }) => (
  <RM.Root>
    <RM.Trigger asChild>{trigger}</RM.Trigger>
    <RM.Portal>
      <RM.Content align="end" sideOffset={6} className="z-50 min-w-44 rounded-ctl border border-edge bg-navy p-1 text-sm shadow-xl">
        {items.map((item) => (
          <RM.Item
            key={item.label}
            onSelect={item.onSelect}
            className={cx("cursor-pointer rounded-lg px-3 py-2 outline-none data-[highlighted]:bg-accent-soft", item.danger ? "text-bad" : "text-fg")}
          >
            {item.label}
          </RM.Item>
        ))}
      </RM.Content>
    </RM.Portal>
  </RM.Root>
);
