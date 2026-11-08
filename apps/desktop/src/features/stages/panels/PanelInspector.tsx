import React from "react";
import { api } from "@panelflow/api-client";
import type { Panel } from "@panelflow/shared-types";
import { Button, Chip, GlassPanel, Input } from "@panelflow/ui-v2";
import type { Box, Size } from "../kit/canvas/geometry";
import { BOX_ERROR, boxIsValid, parseBox } from "./boxValidation";
import { panelStatus } from "./panelsModel";

export interface PanelInspectorProps {
  projectId: string;
  panel: Panel;
  image: Size;
  busy: boolean;
  cropBuster: number;
  onApplyBox: (box: Box) => void;
  onSplit: (type: "horizontal" | "vertical") => void;
  onFullPage: () => void;
  onDelete: () => void;
  /** Extra actions for this panel (redaction). */
  children?: React.ReactNode;
}

/** The selected panel: its crop, its exact position and the actions that apply to one panel. */
export const PanelInspector: React.FC<PanelInspectorProps> = ({ projectId, panel, image, busy, cropBuster, onApplyBox, onSplit, onFullPage, onDelete, children }) => {
  const [v, setV] = React.useState({ x: "", y: "", w: "", h: "" });
  const [cropFailed, setCropFailed] = React.useState(false);
  React.useEffect(() => { setV({ x: String(panel.x), y: String(panel.y), w: String(panel.width), h: String(panel.height) }); setCropFailed(false); }, [panel.id, panel.x, panel.y, panel.width, panel.height]);
  const box = parseBox(v.x, v.y, v.w, v.h);
  const valid = boxIsValid(box, image);
  const changed = box.x !== panel.x || box.y !== panel.y || box.w !== panel.width || box.h !== panel.height;
  const status = panelStatus(panel.status);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) => setV((s) => ({ ...s, [k]: e.target.value }));

  return (
    <GlassPanel blur={false} className="grid grid-cols-1 content-start gap-4 p-4" aria-label="Selected panel">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display text-sm font-semibold text-fg">{`Panel ${panel.page_sequence}`}</h3>
        <Chip tone={status.tone}>{status.word}</Chip>
      </div>
      {cropFailed
        ? <p role="status" className="rounded-ctl border border-edge bg-glass p-3 text-sm text-fg-dim">Crop preview unavailable</p>
        : <img src={`${api.getPanelImageUrl(projectId, panel.id)}?t=${cropBuster}`} alt={`Crop of panel ${panel.page_sequence}`} className="max-h-56 w-full rounded-ctl border border-edge bg-ink object-contain" onError={() => setCropFailed(true)} />}
      <div className="grid grid-cols-2 gap-2">
        <label className="grid gap-1 text-xs text-fg-dim">X<Input aria-label="X position" type="number" value={v.x} onChange={set("x")} className="h-9" /></label>
        <label className="grid gap-1 text-xs text-fg-dim">Y<Input aria-label="Y position" type="number" value={v.y} onChange={set("y")} className="h-9" /></label>
        <label className="grid gap-1 text-xs text-fg-dim">Width<Input aria-label="Width" type="number" value={v.w} onChange={set("w")} className="h-9" /></label>
        <label className="grid gap-1 text-xs text-fg-dim">Height<Input aria-label="Height" type="number" value={v.h} onChange={set("h")} className="h-9" /></label>
      </div>
      {!valid && <p role="alert" className="text-sm text-bad">{BOX_ERROR}</p>}
      <Button variant="secondary" size="sm" disabled={!valid || !changed || busy} onClick={() => onApplyBox(box)}>Apply position</Button>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => onSplit("horizontal")}>Split horizontally</Button>
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => onSplit("vertical")}>Split vertically</Button>
        <Button variant="secondary" size="sm" disabled={busy} onClick={onFullPage}>Mark full page</Button>
      </div>
      {children}
      <Button variant="danger" size="sm" disabled={busy} onClick={onDelete}>Delete panel</Button>
    </GlassPanel>
  );
};
