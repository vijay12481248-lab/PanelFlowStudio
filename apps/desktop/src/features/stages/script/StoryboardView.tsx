import React from "react";
import { RefreshCw } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { ScriptValidationReport, StoryboardPanelRef, StoryboardSegment } from "@panelflow/shared-types";
import { Button, Chip, GlassPanel, Select } from "@panelflow/ui-v2";
import { PanelPreview } from "./PanelPreview";
import { SegmentEditor, type LineValues } from "./SegmentEditor";
import { CAMERA_MOTIONS, issueFor, reasonsFor, withCameraMotion } from "./scriptModel";

export interface StoryboardViewProps {
  projectId: string;
  segments: StoryboardSegment[];
  totalSeconds: number;
  report: ScriptValidationReport | null;
  unsupportedOnly: boolean;
  editingId: string | null;
  onEdit: (segmentId: string | null) => void;
  busy: boolean;
  realigning: boolean;
  onSaveBeat: (segmentId: string, values: LineValues) => Promise<boolean>;
  onMotion: (segmentId: string, panels: StoryboardPanelRef[]) => void;
  onRealign: () => void;
}

/** The storyboard: each beat with its panels, camera motion, narration, voice state and cues. */
export const StoryboardView: React.FC<StoryboardViewProps> = ({ projectId, segments, totalSeconds, report, unsupportedOnly, editingId, onEdit, busy, realigning, onSaveBeat, onMotion, onRealign }) => {
  const rows = unsupportedOnly ? segments.filter((s) => issueFor(report, s.segment_id)) : segments;
  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-data text-xs text-fg-dim">{`Duration: ${totalSeconds}s`}</span>
        <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} loading={realigning} disabled={busy} title="Recalculates frame alignment and keeps your manual edits" onClick={onRealign}>Realign frames</Button>
      </div>
      <ol className="grid grid-cols-1 gap-4" aria-label="Storyboard">
        {rows.map((seg) => {
          const issue = issueFor(report, seg.segment_id);
          const editing = editingId === seg.segment_id;
          return (
            <li key={seg.segment_id} data-segment-id={seg.segment_id} id={`seg-${seg.segment_id}`}>
              <GlassPanel blur={false} className={`grid grid-cols-1 gap-4 p-4 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] ${issue ? "border-bad/50" : editing ? "border-accent" : ""}`}>
                <div className="grid content-start gap-3 md:border-r md:border-edge md:pr-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-info">{`Beat ${seg.sequence}`}</span>
                    <Chip tone="accent">{`${seg.supporting_panels.length} ${seg.supporting_panels.length === 1 ? "frame" : "frames"}`}</Chip>
                  </div>
                  {seg.supporting_panels.map((p, index) => (
                    <div key={`${p.panel_id}-${index}`} className="grid gap-1.5">
                      <PanelPreview src={api.getPanelImageUrl(projectId, p.panel_id)} label={`Source panel ${p.reading_order}`} className="aspect-video w-full" />
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-fg-dim">
                        <span>{`#${p.reading_order} · ${p.role} · ${p.sub_duration_sec}s`}</span>
                        <Select
                          aria-label={`Camera motion for panel ${p.reading_order} of beat ${seg.sequence}`}
                          className="h-8 w-44 text-xs"
                          value={p.camera_motion?.type || "SLOW_PUSH"}
                          disabled={busy}
                          onChange={(e) => onMotion(seg.segment_id, withCameraMotion(seg.supporting_panels, index, e.target.value))}
                        >
                          {CAMERA_MOTIONS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                        </Select>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="grid content-start gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Chip>Narrator</Chip>
                    <Chip tone={seg.emotion === "TENSE" || seg.emotion === "ANGRY" ? "bad" : "neutral"}>{`${seg.emotion} (${Math.round(seg.intensity * 100)}%)`}</Chip>
                    {issue && <Chip tone="bad">Unsupported</Chip>}
                    {seg.manual_override && <Chip tone="warn">Locked override</Chip>}
                    <span className="ml-auto font-data text-xs text-fg">{`${seg.measured_duration_sec}s`}</span>
                    <Chip tone={seg.audio_clip_path ? "ok" : "neutral"}>{seg.audio_clip_path ? "Voice locked" : "Estimated"}</Chip>
                  </div>
                  {editing ? (
                    <SegmentEditor
                      initial={{ text: seg.text, emotion: seg.emotion, intensity: seg.intensity }}
                      showDuration={false}
                      saveLabel="Save beat"
                      busy={busy}
                      onSave={async (values) => { const ok = await onSaveBeat(seg.segment_id, values); if (ok) onEdit(null); return ok; }}
                      onCancel={() => onEdit(null)}
                    />
                  ) : (
                    <p className="rounded-ctl border border-edge bg-glass p-3 text-sm text-fg">{`"${seg.text}"`}</p>
                  )}
                  {issue && (
                    <div className="grid gap-0.5 rounded-ctl border border-bad/40 bg-bad/10 p-2.5 text-xs text-bad">
                      <span className="font-semibold">Why this line is blocked</span>
                      {reasonsFor(issue).map((r, i) => <span key={i}>{`• ${r}`}</span>)}
                    </div>
                  )}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-edge pt-2 text-xs text-fg-dim">
                    <span>{`Music ${seg.music_cue?.intent || "CALM"} · Ducking ${seg.music_cue?.ducking_gain_db ?? -14} dB · SFX ${seg.sfx_cue?.type || "NONE"}`}</span>
                    {!editing && <Button size="sm" variant="ghost" aria-label={`Edit beat ${seg.sequence}`} onClick={() => onEdit(seg.segment_id)}>Edit beat</Button>}
                  </div>
                </div>
              </GlassPanel>
            </li>
          );
        })}
      </ol>
    </div>
  );
};
