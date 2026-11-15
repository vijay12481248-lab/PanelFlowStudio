import React from "react";
import { Button, Dialog } from "@panelflow/ui-v2";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** The in-app replacement for window.confirm: Cancel is first, confirming fires once even on a fast double click. */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({ open, title, description, confirmLabel, danger, onConfirm, onCancel }) => {
  const fired = React.useRef(false);
  React.useEffect(() => { if (open) fired.current = false; }, [open]);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => { if (!next) onCancel(); }}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="ghost" autoFocus onClick={onCancel}>Cancel</Button>
          <Button
            variant={danger ? "danger" : "primary"}
            onClick={() => { if (fired.current) return; fired.current = true; onConfirm(); }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
};
