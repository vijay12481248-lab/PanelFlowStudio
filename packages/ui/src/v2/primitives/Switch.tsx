import React from "react";
import * as RS from "@radix-ui/react-switch";
import { FOCUS_RING } from "./Button";
import { cx } from "../cx";

export interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
}

export const Switch: React.FC<SwitchProps> = ({ checked, onCheckedChange, label }) => {
  const id = React.useId();
  return (
    <div className="flex items-center gap-3">
      <RS.Root
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        className={cx("relative h-6 w-11 rounded-full border border-edge bg-glass transition-colors data-[state=checked]:bg-accent", FOCUS_RING)}
      >
        <RS.Thumb className="block size-4.5 translate-x-0.5 rounded-full bg-white transition-transform duration-(--duration-fast) data-[state=checked]:translate-x-5.5" />
      </RS.Root>
      <label htmlFor={id} className="text-sm text-fg">{label}</label>
    </div>
  );
};
