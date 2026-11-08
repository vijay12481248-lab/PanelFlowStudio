import React from "react";
import { api } from "@panelflow/api-client";
import type { RenderJob } from "@panelflow/shared-types";
import { Button, GlassPanel, Tabs } from "@panelflow/ui-v2";
import { ValidationReport } from "./ValidationReport";
import { outputName, parseReport } from "./renderModel";

export interface RenderResultProps {
  projectId: string;
  render: RenderJob;
  onPublish: () => void;
  /** Saves text as a file. Replaced in tests. */
  download?: (filename: string, content: string) => void;
}

function browserDownload(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** An image that says so when it cannot load. */
const Picture: React.FC<{ src: string; alt: string; unavailable: string; className?: string }> = ({ src, alt, unavailable, className }) => {
  const [failed, setFailed] = React.useState(false);
  return failed
    ? <p role="status" className="grid min-h-24 place-items-center rounded-ctl border border-edge bg-glass p-3 text-sm text-fg-dim">{unavailable}</p>
    : <img src={src} alt={alt} className={className} loading="lazy" onError={() => setFailed(true)} />;
};

/** A finished render: the video with its check markers, the contact sheet and sample frames, the checks, and the next step. */
export const RenderResult: React.FC<RenderResultProps> = ({ projectId, render, onPublish, download = browserDownload }) => {
  const [tab, setTab] = React.useState("video");
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const opening = React.useRef(false);
  const [error, setError] = React.useState<string | null>(null);
  const report = parseReport(render.validation_report);
  const samples: Array<{ timestamp_sec: number; frame_index?: number; mean_luminance?: number }> = Array.isArray(report?.frame_samples) ? report!.frame_samples : [];

  if (render.status === "FAILED") {
    return (
      <GlassPanel blur={false} className="grid gap-2 border-bad/40 p-4" role="alert">
        <h3 className="font-display text-sm font-semibold text-bad">This render failed</h3>
        <p className="text-sm text-fg-dim">{render.error_message || render.error_code || "The video could not be made. Check the engine log in Diagnostics."}</p>
      </GlassPanel>
    );
  }

  const open = async (selectFile: boolean) => {
    if (opening.current) return;
    opening.current = true;
    setError(null);
    try { await api.openPath(render.output_path, selectFile); }
    catch { setError("Couldn't open that. The file may have been moved."); }
    finally { opening.current = false; }
  };
  const seek = (seconds: number) => { if (videoRef.current) videoRef.current.currentTime = seconds; };

  return (
    <div className="grid grid-cols-1 gap-4">
      <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-display text-sm font-semibold text-fg">The rendered video</h3>
          <span className="font-data text-xs text-fg-dim" title={render.output_path}>{outputName(render.output_path)}</span>
        </div>
        <Tabs value={tab} onValueChange={setTab} tabs={[{ value: "video", label: "Video" }, { value: "sheet", label: "Contact sheet" }, { value: "samples", label: "Audit samples" }]}>
          {tab === "video" && (
            <div className="grid grid-cols-1 gap-3">
              <video ref={videoRef} src={api.getRenderVideoUrl(projectId, render.render_id)} controls className="max-h-[60vh] w-full rounded-ctl border border-edge bg-ink" />
              {samples.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-fg-faint">Check frames: jump to one</span>
                  {samples.map((s, i) => (
                    <Button key={i} size="sm" variant="ghost" aria-label={`Seek to ${s.timestamp_sec} seconds`} title={`Frame ${s.frame_index ?? "?"}${s.mean_luminance != null ? ` · luminance ${s.mean_luminance.toFixed(1)} of 255` : ""}`} onClick={() => seek(s.timestamp_sec)}>{`${s.timestamp_sec.toFixed(1)}s`}</Button>
                  ))}
                </div>
              )}
            </div>
          )}
          {tab === "sheet" && <Picture src={api.getRenderContactSheetUrl(projectId, render.render_id)} alt="Contact sheet of the rendered video" unavailable="Contact sheet unavailable" className="w-full rounded-ctl border border-edge" />}
          {tab === "samples" && (
            samples.length === 0
              ? <p className="text-sm text-fg-dim">This render has no sample frames.</p>
              : <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                  {samples.map((s, i) => (
                    <figure key={i} className="grid gap-1">
                      <Picture src={api.getRenderAuditSampleUrl(projectId, render.render_id, i)} alt={`Sample frame ${i + 1}`} unavailable={`Sample ${i + 1} unavailable`} className="w-full rounded-ctl border border-edge" />
                      <figcaption className="text-xs text-fg-dim">{`${s.timestamp_sec.toFixed(2)}s${s.mean_luminance != null ? ` · luminance ${s.mean_luminance.toFixed(1)}` : ""}`}</figcaption>
                    </figure>
                  ))}
                </div>
          )}
        </Tabs>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => void open(true)}>Open file</Button>
          <Button variant="secondary" size="sm" onClick={() => void open(false)}>Open folder</Button>
          <Button variant="ghost" size="sm" onClick={() => download(`qa_audit_${render.render_id}.json`, JSON.stringify(report ?? render.validation_report ?? {}, null, 2))}>Export QA audit</Button>
        </div>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </GlassPanel>

      <ValidationReport report={render.validation_report} />

      <GlassPanel blur={false} className="flex flex-wrap items-center justify-between gap-3 p-4">
        <p className="text-sm text-fg-dim">Next: check the render and copy the packaging in Publish.</p>
        <Button variant="primary" size="sm" onClick={onPublish}>Continue to publish</Button>
      </GlassPanel>
    </div>
  );
};
