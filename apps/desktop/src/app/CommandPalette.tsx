import React from "react";
import { Command as Cmdk } from "cmdk";
import { Dialog } from "@panelflow/ui-v2";
import type { Command, CommandGroup } from "./commands";

const GROUPS: CommandGroup[] = ["Go to", "Projects"];

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  commands: Command[];
  onSelect: (command: Command) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onOpenChange, commands, onSelect }) => (
  <Dialog open={open} onOpenChange={onOpenChange} title="Go anywhere" description="Search screens, projects and settings.">
    <Cmdk label="Go anywhere" className="grid gap-3">
      <Cmdk.Input
        autoFocus
        placeholder="Open jobs"
        className="h-10 w-full rounded-ctl border border-edge bg-glass px-3 text-sm text-fg placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-info"
      />
      <Cmdk.List className="max-h-72 overflow-y-auto">
        <Cmdk.Empty className="px-3 py-6 text-center text-sm text-fg-dim">No match. Try a project name or a screen.</Cmdk.Empty>
        {GROUPS.map((group) => {
          const items = commands.filter((command) => command.group === group);
          return items.length === 0 ? null : (
            <Cmdk.Group key={group} heading={group} className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-fg-faint">
              {items.map((command) => (
                <Cmdk.Item
                  key={command.id}
                  value={`${command.label} ${(command.keywords ?? []).join(" ")}`}
                  onSelect={() => onSelect(command)}
                  className="cursor-pointer rounded-ctl px-3 py-2 text-sm text-fg data-[selected=true]:bg-accent-soft"
                >
                  {command.label}
                </Cmdk.Item>
              ))}
            </Cmdk.Group>
          );
        })}
      </Cmdk.List>
    </Cmdk>
  </Dialog>
);
