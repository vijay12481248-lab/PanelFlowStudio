import React from "react";
import { api } from "@panelflow/api-client";
import type { CharacterEntity, ScriptSegment, ScriptValidationReport } from "@panelflow/shared-types";
import { Button, Chip, GlassPanel, Menu } from "@panelflow/ui-v2";
import { panelLabel } from "../story/storyModel";
import { PanelPreview } from "./PanelPreview";
import { SegmentEditor, type LineValues } from "./SegmentEditor";
import { SEGMENT_ACTIONS, issueFor, reasonsFor, speakerName, type SegmentAction } from "./scriptModel";

export interface SpokenListProps {
  projectId: string;
  segments: ScriptSegment[];
  characters: CharacterEntity[];
  report: ScriptValidationReport | null;
  unsupportedOnly: boolean;
  editingId: string | null;
  onEdit: (segmentId: string | null) => void;
  /** A change is running somewhere on the screen. */
  busy: boolean;
  onAction: (segmentId: string, action: SegmentAction) => void;
  onSave: (segmentId: string, values: LineValues) => Promise<boolean>;
}

const STATUS = { SUPPORTED: "Supported", WEAKLY_SUPPORTED: "Weakly supported", UNSUPPORTED: "Unsupported" } as const;

/** The script as spoken lines: evidence, status, editing and the line actions menu. */
export const SpokenList: React.FC<SpokenListProps> = ({ projectId, segments, characters, report, unsupportedOnly, editingId, onEdit, busy, onAction, onSave }) => {
  const rows = unsupportedOnly ? segments.filter((s) => issueFor(report, s.segment_id) || s.faithfulness_status === "UNSUPPORTED") : segments;
  return (
    <ol className="grid grid-cols-1 gap-3" aria-label="Spoken script">
      {rows.map((seg) => {
        const issue = issueFor(report, seg.segment_id);
        const unsupported = Boolean(issue) || seg.faithfulness_status === "UNSUPPORTED";
        const editing = editingId === seg.segment_id;
        const intents = [seg.motion_intent && `Motion ${seg.motion_intent}`, seg.music_intent && `Music ${seg.music_intent}`, seg.sfx_intent && `SFX ${seg.sfx_intent}`].filter(Boolean);
        return (
          <li key={seg.segment_id} data-segment-id={seg.segment_id} id={`seg-${seg.segment_id}`}>
            <GlassPanel blur={false} className={`grid gap-3 p-4 ${unsupported ? "border-bad/50" : editing ? "border-accent" : ""}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-info">{`#${seg.sequence}`}</span>
                <Chip tone={seg.type === "NARRATOR" ? "neutral" : "accent"}>{seg.type}</Chip>
                <span className="text-sm font-medium text-fg">{speakerName(seg, characters)}</span>
                <span className="font-data text-xs text-fg-dim">{`${seg.estimated_start}s to ${seg.estimated_end}s (${seg.estimated_duration}s)`}</span>
                <Chip tone={unsupported ? "bad" : seg.faithfulness_status === "WEAKLY_SUPPORTED" ? "warn" : "ok"}>{unsupported ? "Unsupported" : STATUS[seg.faithfulness_status] ?? seg.faithfulness_status}</Chip>
                {seg.manual_override && <Chip>Edited</Chip>}
                <div className="ml-auto flex items-center gap-1">
                  {!editing && <Button size="sm" variant="ghost" aria-label={`Edit line ${seg.sequence}`} onClick={() => onEdit(seg.segment_id)}>Edit</Button>}
                  <Menu
                    trigger={<Button size="sm" variant="ghost" aria-label={`Line actions for line ${seg.sequence}`} disabled={busy}>Line actions</Button>}
                    items={SEGMENT_ACTIONS.map((action) => ({ label: action.label, danger: action.danger, onSelect: () => onAction(seg.segment_id, action) }))}
                  />
                </div>
              </div>

              {seg.source_evidence.panel_ids.length > 0 && (
                <div className="flex gap-2 overflow-x-auto py-1" aria-label={`Source panels for line ${seg.sequence}`}>
                  {seg.source_evidence.panel_ids.map((panelId) => <PanelPreview key={panelId} src={api.getPanelImageUrl(projectId, panelId)} label={`Source panel for line ${seg.sequence}`} />)}
                </div>
              )}

              {editing ? (
                <SegmentEditor
                  initial={{ text: seg.text, emotion: seg.emotion, intensity: seg.intensity, duration: seg.estimated_duration }}
                  showDuration
                  saveLabel="Save line"
                  busy={busy}
                  onSave={async (values) => { const ok = await onSave(seg.segment_id, values); if (ok) onEdit(null); return ok; }}
                  onCancel={() => onEdit(null)}
                />
              ) : (
                <p className="text-sm text-fg">{`"${seg.text}"`}</p>
              )}

              {unsupported && (
                <div className="grid gap-0.5 rounded-ctl border border-bad/40 bg-bad/10 p-2.5 text-xs text-bad">
                  <span className="font-semibold">Why this line is blocked</span>
                  {reasonsFor(issue ?? {}).map((reason, i) => <span key={i}>{`• ${reason}`}</span>)}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-dim">
                <span>{`Emotion ${seg.emotion} (${Math.round(seg.intensity * 100)}%)`}</span>
                {intents.length > 0 && <span>{intents.join(" · ")}</span>}
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-fg-faint" aria-label="Evidence">
                <span>Evidence</span>
                {seg.source_evidence.panel_ids.map((id) => <Chip key={id}>{panelLabel(id, [])}</Chip>)}
                {seg.source_evidence.text_region_ids.map((id) => <Chip key={id}>{`Region …${id.slice(-4)}`}</Chip>)}
              </div>
            </GlassPanel>
          </li>
        );
      })}
    </ol>
  );
};
