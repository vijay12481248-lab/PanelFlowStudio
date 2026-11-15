import React from "react";
import type { AcquisitionManifest } from "@panelflow/shared-types";
import { Button, Dialog } from "@panelflow/ui-v2";

/** The acquisition manifest the engine holds for the project, as read-only JSON. */
export const ManifestDialog: React.FC<{ manifest: AcquisitionManifest | null; onClose: () => void }> = ({ manifest, onClose }) => (
  <Dialog
    open={manifest !== null}
    onOpenChange={(open) => { if (!open) onClose(); }}
    title="Acquisition manifest"
    description="What the engine recorded about the source and each page."
    footer={<Button variant="ghost" onClick={onClose}>Close</Button>}
  >
    <pre tabIndex={0} aria-label="Manifest JSON" className="max-h-[50vh] overflow-auto rounded-ctl border border-edge bg-glass p-3 font-data text-xs text-fg-dim">
      {JSON.stringify(manifest, null, 2)}
    </pre>
  </Dialog>
);
