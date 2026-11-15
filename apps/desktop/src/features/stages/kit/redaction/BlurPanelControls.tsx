import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import { Button } from "@panelflow/ui-v2";
import { ConfirmDialog } from "../ConfirmDialog";
import type { Redaction } from "./useRedaction";

export interface BlurPanelControlsProps {
  projectId: string;
  panelId: string;
  /** Changes after any edit, so the state is read again. */
  buster: number;
  redaction: Redaction;
}

/** Whether a panel is blurred (in words), and the two actions for one panel. */
export const BlurPanelControls: React.FC<BlurPanelControlsProps> = ({ projectId, panelId, buster, redaction }) => {
  const [confirming, setConfirming] = React.useState(false);
  const status = useQuery({
    queryKey: ["stages", "redaction", "status", projectId, panelId, buster],
    queryFn: () => api.getPanelBlurStatus(projectId, panelId).catch(() => null),
    retry: false,
  });
  const s = status.data;
  const blurred = Boolean(s?.is_blurred);
  return (
    <div className="grid gap-2 border-t border-edge pt-3">
      <p className="text-xs text-fg-dim">{s ? (blurred ? `Blurred, ${s.blurred_regions_count} ${s.blurred_regions_count === 1 ? "region" : "regions"}` : "Not blurred") : "Blur state unknown"}{s?.has_backup ? ". Original saved." : ""}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" disabled={redaction.busy} onClick={() => void redaction.blurPanel(panelId)}>Blur panel</Button>
        <Button size="sm" variant="secondary" disabled={redaction.busy || !blurred} onClick={() => setConfirming(true)}>Restore original</Button>
      </div>
      <ConfirmDialog
        open={confirming}
        title="Restore the original image?"
        description="The blur on this panel is removed and its original image comes back."
        confirmLabel="Restore original"
        onConfirm={() => { setConfirming(false); void redaction.reset(panelId); }}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
};
