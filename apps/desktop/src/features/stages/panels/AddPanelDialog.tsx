import React from "react";
import { Button, Dialog, Field, Input } from "@panelflow/ui-v2";
import type { Box, Size } from "../kit/canvas/geometry";
import { BOX_ERROR, boxIsValid, parseBox } from "./boxValidation";

export interface AddPanelDialogProps {
  open: boolean;
  image: Size;
  onClose: () => void;
  /** Resolves true when the panel was added (the dialog then closes). */
  onAdd: (box: Box) => Promise<boolean>;
}

/** Add a panel by typing its position and size, for when drawing is not practical. */
export const AddPanelDialog: React.FC<AddPanelDialogProps> = ({ open, image, onClose, onAdd }) => {
  const [v, setV] = React.useState({ x: "50", y: "50", w: "400", h: "300" });
  const [saving, setSaving] = React.useState(false);
  const busy = React.useRef(false);
  React.useEffect(() => { if (open) setV({ x: "50", y: "50", w: "400", h: "300" }); }, [open]);
  const box = parseBox(v.x, v.y, v.w, v.h);
  const valid = boxIsValid(box, image);
  const add = async () => {
    if (!valid || busy.current) return;
    busy.current = true;
    setSaving(true);
    try { if (await onAdd(box)) onClose(); } finally { busy.current = false; setSaving(false); }
  };
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) => setV((s) => ({ ...s, [k]: e.target.value }));
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="Add a panel by numbers"
      description="Positions are in pixels from the top left of the page."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={saving} disabled={!valid} onClick={() => void add()}>Add panel</Button></>}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="X"><Input type="number" value={v.x} onChange={set("x")} /></Field>
        <Field label="Y"><Input type="number" value={v.y} onChange={set("y")} /></Field>
        <Field label="Width"><Input type="number" value={v.w} onChange={set("w")} /></Field>
        <Field label="Height"><Input type="number" value={v.h} onChange={set("h")} /></Field>
        {!valid && <p role="alert" className="col-span-2 text-sm text-bad">{BOX_ERROR}</p>}
      </div>
    </Dialog>
  );
};
