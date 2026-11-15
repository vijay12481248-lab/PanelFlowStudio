import React from "react";
import { api } from "@panelflow/api-client";
import { Button, ErrorState, GlassPanel, Skeleton } from "@panelflow/ui-v2";
import { diagnosticsFilename, hardwareRows } from "./settingsModels";
import { useHardware } from "./settingsQueries";
import { saveJsonFile } from "./saveJsonFile";

export interface DiagnosticsSectionProps {
  /** Injected in tests; the default saves a file through the browser. */
  download?: (filename: string, json: string) => void;
  copy?: (text: string) => Promise<void>;
}

const EXPORT_FAILED = "Couldn't export diagnostics. Check that the engine is running, then try again.";

export const DiagnosticsSection: React.FC<DiagnosticsSectionProps> = ({ download = saveJsonFile, copy = (text) => navigator.clipboard.writeText(text) }) => {
  const hardware = useHardware();
  const [status, setStatus] = React.useState<string | null>(null);
  const [failed, setFailed] = React.useState(false);
  const busy = React.useRef(false); // synchronous guard against a fast double click

  const run = async (action: (json: string, filename: string) => Promise<void> | void, done: string) => {
    if (busy.current) return;
    busy.current = true;
    setFailed(false);
    setStatus(null);
    try {
      const diagnostics = await api.exportDiagnostics();
      await action(JSON.stringify(diagnostics, null, 2), diagnosticsFilename(diagnostics));
      setStatus(done);
    } catch {
      setFailed(true); // never show the raw exception: it can contain local paths
    } finally {
      busy.current = false;
    }
  };

  return (
    <div className="grid grid-cols-1 gap-5">
      <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4">
        <h2 className="font-display text-sm font-semibold text-fg">Hardware</h2>
        {hardware.isError ? (
          <ErrorState title="Couldn't read the hardware details" description="Check that the engine is running, then try again." onRetry={() => void hardware.refetch()} />
        ) : !hardware.data ? (
          <Skeleton className="h-32" />
        ) : (
          <dl className="grid grid-cols-1 gap-2 text-sm">
            {hardwareRows(hardware.data).map((row) => (
              <div key={row.label} className="flex justify-between gap-4 border-b border-edge pb-2">
                <dt className="text-fg-faint">{row.label}</dt>
                <dd className="text-right text-fg">{row.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </GlassPanel>

      <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4">
        <h2 className="font-display text-sm font-semibold text-fg">Export</h2>
        <p className="text-sm text-fg-dim">This file has paths and secrets removed. Review it before you share it.</p>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={() => void run((json, filename) => download(filename, json), "Diagnostics exported")}>Export diagnostics</Button>
          <Button variant="secondary" onClick={() => void run((json) => copy(json), "Copied")}>Copy diagnostics</Button>
          {status && <p role="status" className="text-sm text-ok">{status}</p>}
          {failed && <p role="alert" className="text-sm text-bad">{EXPORT_FAILED}</p>}
        </div>
      </GlassPanel>
    </div>
  );
};
