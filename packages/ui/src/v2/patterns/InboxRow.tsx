import React from "react";
import { ListRow, type RowTone } from "../primitives/ListRow";
import { Button } from "../primitives/Button";

export type InboxKind = "review" | "blocked" | "publish" | "failed";

const TONE: Record<InboxKind, RowTone> = { review: "info", blocked: "warn", publish: "ok", failed: "bad" };

export interface InboxRowProps {
  kind: InboxKind;
  title: string;
  subtitle: string;
  actionLabel: string;
  onAction: () => void;
  onSelect?: () => void;
  selected?: boolean;
}

export const InboxRow: React.FC<InboxRowProps> = ({ kind, title, subtitle, actionLabel, onAction, onSelect, selected }) => (
  <ListRow
    tone={TONE[kind]}
    title={title}
    subtitle={subtitle}
    selected={selected}
    onSelect={onSelect}
    action={<Button variant={selected ? "secondary" : "ghost"} size="sm" onClick={onAction}>{actionLabel}</Button>}
  />
);
