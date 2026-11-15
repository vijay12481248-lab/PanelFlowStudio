import React, { useState } from "react";
import { Check, Copy, Download, Save } from "lucide-react";
import { renderEditedBlob, type EditedPicture } from "./cut/render";

export type ExportFormat = "png" | "jpg" | "webp";

const FORMATS: { id: ExportFormat; label: string; mime: string }[] = [
  { id: "png", label: "PNG", mime: "image/png" },
  { id: "jpg", label: "JPG", mime: "image/jpeg" },
  { id: "webp", label: "WebP", mime: "image/webp" },
];

/** What is baked into an export: the picture's pixels with the colour grade (if any) applied first, then the cut (if any). */
export type BakedEdit = EditedPicture;

/** Fetch the picture and write it out in the chosen format. A plain PNG is saved byte for byte; a grade and a cut are baked in. */
async function exportPicture(url: string, filename: string, format: ExportFormat, baked: BakedEdit | null): Promise<void> {
  const target = FORMATS.find((f) => f.id === format)!;
  let out: Blob;
  if (baked) {
    out = await renderEditedBlob(baked, target.mime);
  } else {
    out = await (await fetch(url)).blob();
    if (out.type !== target.mime) {
      const bitmap = await createImageBitmap(out);
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
  ["source_asset_id", "Edited from"],
];

export const DeliverInspector: React.FC<{
  imageUrl: string;
  filename: string;
  dimensions: string;
  sha256?: string;
  provenance?: Record<string, any>;
  /** Set while the picture carries a colour grade that is switched on, or a cut. */
  baked: BakedEdit | null;
  /** The size the export will have (after the cut), as text. */
  outputSize: string;
  /** Project pictures can keep the edited result as a new asset. */
  onSaveEdited?: () => Promise<void>;
  onToast: (message: string) => void;
}> = ({ imageUrl, filename, dimensions, sha256, provenance, baked, outputSize, onSaveEdited, onToast }) => {
  const [format, setFormat] = useState<ExportFormat>("png");
  const [bake, setBake] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const rows = FIELDS.filter(([key]) => provenance && provenance[key] != null && provenance[key] !== "");

  const run = async () => {
    setBusy(true);
    try {
      await exportPicture(imageUrl, filename, format, baked && bake ? baked : null);
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
        <p className="text-[11px] text-fg-faint">{baked && bake ? `Exported at ${outputSize}.` : `Same size as the picture on screen (${dimensions}).`} JPG and WebP are saved at 92% quality.</p>
        {baked && (
          <label className="flex items-center gap-2 text-[11px] text-fg-dim">
            <input type="checkbox" checked={bake} onChange={(e) => setBake(e.target.checked)} className="accent-accent" />
            <span>Bake the colour grade, the cut and the effects into the export</span>
          </label>
        )}
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-2.5 text-xs font-semibold text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Download className="h-4 w-4" />
          <span>{busy ? "Exporting…" : "Export picture"}</span>
        </button>
        {baked && onSaveEdited && (
          <button
            type="button"
            disabled={saving}
            onClick={async () => {
              setSaving(true);
              try {
                await onSaveEdited();
              } finally {
                setSaving(false);
              }
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-edge bg-flat py-2.5 text-xs font-semibold text-fg transition-colors hover:bg-glass-hi disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Save className="h-4 w-4" />
            <span>{saving ? "Saving…" : "Save edited picture as a new asset"}</span>
          </button>
        )}
        <p className="text-[11px] text-fg-faint">Every AI result is already saved in your project as its own asset. A graded, cut or effect-laden picture is only saved when you ask.</p>
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
