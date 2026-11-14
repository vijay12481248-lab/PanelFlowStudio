import React, { useState } from "react";
import { Check, Copy, Download } from "lucide-react";

export type ExportFormat = "png" | "jpg" | "webp";

const FORMATS: { id: ExportFormat; label: string; mime: string }[] = [
  { id: "png", label: "PNG", mime: "image/png" },
  { id: "jpg", label: "JPG", mime: "image/jpeg" },
  { id: "webp", label: "WebP", mime: "image/webp" },
];

/** Fetch the picture and write it out in the chosen format. PNG that is already PNG is saved byte for byte. */
async function exportPicture(url: string, filename: string, format: ExportFormat): Promise<void> {
  const blob = await (await fetch(url)).blob();
  const target = FORMATS.find((f) => f.id === format)!;
  let out = blob;
  if (blob.type !== target.mime) {
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("This browser cannot re-encode the picture.");
    if (format === "jpg") {
      ctx.fillStyle = "white"; // JPG has no transparency
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    ctx.drawImage(bitmap, 0, 0);
    out = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not encode the picture."))), target.mime, 0.92),
    );
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(out);
  link.download = filename.replace(/\.[^.]+$/, "") + "." + format;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

const FIELDS: [string, string][] = [
  ["workflow_id", "Workflow"],
  ["mode", "Mode"],
  ["prompt", "Prompt"],
  ["caption", "Caption"],
  ["seed", "Seed"],
  ["pose_asset_id", "Pose picture"],
  ["base_asset_id", "Edited from"],
];

export const DeliverInspector: React.FC<{
  imageUrl: string;
  filename: string;
  dimensions: string;
  sha256?: string;
  provenance?: Record<string, any>;
  onToast: (message: string) => void;
}> = ({ imageUrl, filename, dimensions, sha256, provenance, onToast }) => {
  const [format, setFormat] = useState<ExportFormat>("png");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const rows = FIELDS.filter(([key]) => provenance && provenance[key] != null && provenance[key] !== "");

  const run = async () => {
    setBusy(true);
    try {
      await exportPicture(imageUrl, filename, format);
      onToast(`Exported as ${format.toUpperCase()}`);
    } catch (err: any) {
      onToast(err?.message || "Export failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <section className="flex flex-col gap-3">
        <span className="text-[11px] font-medium text-fg-dim">Export file</span>
        <div role="tablist" aria-label="Export format" className="flex gap-1 rounded-lg bg-flat p-1">
          {FORMATS.map((f) => (
            <button
              key={f.id}
              type="button"
              role="tab"
              aria-selected={format === f.id}
              onClick={() => setFormat(f.id)}
              className={`flex-1 rounded-md py-1.5 text-[11px] font-medium transition-colors ${format === f.id ? "bg-accent text-white" : "text-fg-dim hover:text-fg"}`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-fg-faint">Same size as the picture on screen ({dimensions}). JPG and WebP are saved at 92% quality.</p>
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-2.5 text-xs font-semibold text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Download className="h-4 w-4" />
          <span>{busy ? "Exporting…" : "Export picture"}</span>
        </button>
        <p className="text-[11px] text-fg-faint">Every AI result is already saved in your project as its own asset.</p>
      </section>

      <section className="flex flex-col gap-2 border-t border-edge/70 pt-3">
        <span className="text-[11px] font-medium text-fg-dim">Provenance</span>
        {rows.length === 0 ? (
          <p className="text-[11px] text-fg-faint">No generation record: this is an original picture.</p>
        ) : (
          <dl className="flex flex-col gap-2">
            {rows.map(([key, label]) => (
              <div key={key}>
                <dt className="text-[10px] uppercase tracking-wide text-fg-faint">{label}</dt>
                <dd className="break-words font-mono text-[11px] text-fg-dim">{String(provenance![key])}</dd>
              </div>
            ))}
          </dl>
        )}
        {sha256 && (
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(sha256);
              setCopied(true);
              onToast("SHA-256 copied");
              setTimeout(() => setCopied(false), 2000);
            }}
            className="flex items-center gap-2 self-start rounded-lg border border-edge bg-flat px-2.5 py-1.5 text-[11px] text-fg-dim transition-colors hover:text-fg"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-ok" /> : <Copy className="h-3.5 w-3.5" />}
            <span>Copy SHA-256</span>
          </button>
        )}
      </section>
    </div>
  );
};
