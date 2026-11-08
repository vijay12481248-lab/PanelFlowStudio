import React from "react";
import { Button, EmptyState, InboxRow, type InboxKind } from "@panelflow/ui-v2";
import type { InboxItem } from "./inbox";

const GROUP_ORDER: Array<[InboxKind, string]> = [["failed", "Failed"], ["blocked", "Blocked"], ["review", "Review"], ["publish", "Ready to publish"]];
const CAP = 8;

export interface NeedsYouProps {
  items: InboxItem[];
  onAction: (item: InboxItem) => void;
  onCreate: () => void;
  onOpenStories: () => void;
}

export const NeedsYou: React.FC<NeedsYouProps> = ({ items, onAction, onCreate, onOpenStories }) => {
  const [showAll, setShowAll] = React.useState(false);
  if (items.length === 0) {
    return (
      <EmptyState
        title="Nothing needs you"
        description="Everything is approved or running. Start something new, or check your Original Stories."
        action={<span className="flex gap-2"><Button variant="primary" onClick={onCreate}>Create a project</Button><Button onClick={onOpenStories}>Open original stories</Button></span>}
      />
    );
  }
  const shown = showAll ? items : items.slice(0, CAP);
  return (
    <div className="grid gap-4">
      {GROUP_ORDER.map(([kind, label]) => {
        const rows = shown.filter((item) => item.kind === kind);
        return rows.length === 0 ? null : (
          <section key={kind} className="grid gap-1">
            <h3 data-inbox-group className="px-2 text-xs font-medium text-fg-faint">{label}</h3>
            {rows.map((item) => (
              <div key={item.id} data-inbox-row>
                <InboxRow kind={item.kind} title={item.title} subtitle={item.subtitle} actionLabel={item.actionLabel} selected={item === items[0]} onAction={() => onAction(item)} />
              </div>
            ))}
          </section>
        );
      })}
      {items.length > CAP && !showAll && <Button variant="ghost" size="sm" onClick={() => setShowAll(true)}>{`Show all ${items.length}`}</Button>}
    </div>
  );
};
