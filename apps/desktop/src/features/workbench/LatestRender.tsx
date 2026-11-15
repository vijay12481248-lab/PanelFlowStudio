import React from "react";
import { Link } from "react-router";
import { api } from "@panelflow/api-client";
import type { RenderJob, RenderValidationReport } from "@panelflow/shared-types";
import { Button, EmptyState, GlassPanel } from "@panelflow/ui-v2";
import { paths } from "../../app/routes";
import { durationLabel } from "./publishModel";

export interface LatestRenderProps {
  projectId: string;
  render: RenderJob | undefined;
  report: RenderValidationReport | undefined;
}

const verdict = (ok: boolean, what: string) => (ok ? `${what} valid` : `${what} has problems`);

export const LatestRender: React.FC<LatestRenderProps> = ({ projectId, render, report }) => {
  const opening = React.useRef(false); // synchronous guard against a fast double click
  const openFolder = async () => {
    if (opening.current) return;
    opening.current = true;
    try { await api.openProjectFolder(projectId); } catch { /* the folder may have moved; nothing else to do here */ } finally { opening.current = false; }
  };

  if (!render) {
    return (
      <GlassPanel blur={false}>
        <EmptyState
          title="No finished render yet"
          description="Render the video first. When it finishes it appears here with its checks."
          action={<Link to={paths.stage(projectId, "render")} className="text-sm text-info underline underline-offset-2">Open the render stage</Link>}
        />
      </GlassPanel>
    );
  }
  return (
    <GlassPanel blur={false} className="grid grid-cols-1 gap-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-sm font-semibold text-fg">Latest render</h2>
          <p className="text-xs text-fg-dim">{`${render.output_profile}${report ? `, ${durationLabel(report.duration_sec)}` : ""}`}</p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => void openFolder()}>Open project folder</Button>
      </div>
      <video controls preload="metadata" src={api.getRenderVideoUrl(projectId, render.render_id)} className="aspect-video w-full rounded-ctl border border-edge bg-ink" />
      {report && (
        <div className="grid grid-cols-1 gap-2 text-sm">
          <ul className="flex flex-wrap gap-x-5 gap-y-1 text-fg">
            <li>{verdict(report.video_valid, "Video")}</li>
            <li>{verdict(report.audio_valid, "Audio")}</li>
            <li>{verdict(report.sync_valid, "Sync")}</li>
          </ul>
          <p className="text-xs text-fg-dim">{`Black frames: ${report.black_frames_count}. Timeline gaps: ${report.timeline_gaps_count}. Clipping samples: ${report.clipping_samples_count}.`}</p>
          {report.warnings.length > 0 && (
            <ul className="grid grid-cols-1 gap-1 text-xs text-warn">
              {report.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          )}
        </div>
      )}
    </GlassPanel>
  );
};
