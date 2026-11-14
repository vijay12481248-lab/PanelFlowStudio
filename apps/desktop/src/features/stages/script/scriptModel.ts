import type { CharacterEntity, PipelineStage, ScriptSegment, ScriptValidationReport, StoryboardPanelRef, VideoScript } from "@panelflow/shared-types";
import { characterName } from "../story/storyModel";

export type ReportIssue = ScriptValidationReport["issues"][number];

export const EMOTIONS = ["NEUTRAL", "DETERMINED", "TENSE", "CALM", "JOYFUL", "SAD", "ANGRY", "FEARFUL", "SURPRISED"] as const;

export const PROFILES = [
  { value: "FAITHFUL", label: "Faithful (direct source)" },
  { value: "CONDENSED", label: "Condensed (paced recap)" },
  { value: "DRAMATIC_NARRATION", label: "Dramatic narration" },
  { value: "ACCESSIBLE_RECAP", label: "Accessible recap" },
] as const;

export const CAMERA_MOTIONS = [
  { value: "SLOW_PUSH", label: "Slow push (pan and zoom)" },
  { value: "CHARACTER_FOCUS", label: "Character focus" },
  { value: "REACTION_CLOSEUP", label: "Reaction close-up" },
  { value: "IMPACT", label: "Impact (combat shake)" },
  { value: "PAN", label: "Pan (horizontal or vertical)" },
  { value: "STATIC", label: "Static" },
] as const;

export interface SegmentAction { id: string; label: string; /** A question to ask first, for actions that discard or join text. */ confirm: string | null; danger?: boolean }

export const SEGMENT_ACTIONS: SegmentAction[] = [
  { id: "regenerate", label: "Regenerate", confirm: null },
  { id: "shorten", label: "Shorten", confirm: null },
  { id: "expand", label: "Expand", confirm: null },
  { id: "more_drama", label: "More drama", confirm: null },
  { id: "less_drama", label: "Less drama", confirm: null },
  { id: "split", label: "Split", confirm: null },
  { id: "merge_next", label: "Merge with next", confirm: "Join this line with the next one?" },
  { id: "move_up", label: "Move up", confirm: null },
  { id: "move_down", label: "Move down", confirm: null },
  { id: "remove", label: "Remove", confirm: "Remove this line from the script?", danger: true },
];

const flagged = (issue: ReportIssue) => issue.status === "UNSUPPORTED" || Boolean(issue.reasons && issue.reasons.length > 0);

export function issueFor(report: ScriptValidationReport | null, segmentId: string): ReportIssue | null {
  return report?.issues?.find((i) => i.segment_id === segmentId && flagged(i)) ?? null;
}

export const unsupportedIssues = (report: ScriptValidationReport | null): ReportIssue[] => (report?.issues ?? []).filter(flagged);

export const unsupportedSegmentIds = (report: ScriptValidationReport | null): Set<string> =>
  new Set(unsupportedIssues(report).map((i) => i.segment_id).filter((id): id is string => Boolean(id)));

export function reasonsFor(issue: Pick<ReportIssue, "reasons" | "issues">): string[] {
  if (issue.reasons?.length) return issue.reasons;
  if (issue.issues?.length) return issue.issues;
  return ["This line makes claims that the source panels, text or events do not support."];
}

/** Never a made-up number: with no report the coverage has not been checked. */
export const coverageLabel = (report: ScriptValidationReport | null): string => (report ? `${Math.round(report.coverage_score * 100)}%` : "Not checked");

export function speakerName(seg: Pick<ScriptSegment, "type" | "speaker_character_id">, characters: CharacterEntity[]): string {
  if (seg.type === "NARRATOR") return "Narrator";
  const known = characters.find((c) => c.character_id === seg.speaker_character_id);
  return known ? characterName(known) : "Speaker";
}

export function canApproveScript({ script, report, busy }: { script: VideoScript | null; report: ScriptValidationReport | null; busy: boolean }): { ok: boolean; reason: string | null } {
  if (!script) return { ok: false, reason: "Generate a script first." };
  if (busy) return { ok: false, reason: "Wait for the current change to finish." };
  if (report && report.passed === false) {
    const n = report.unsupported_segments;
    return { ok: false, reason: n > 0 ? `${n} unsupported line${n === 1 ? "" : "s"} must be fixed first.` : "Validation did not pass. Fix the flagged lines first." };
  }
  return { ok: true, reason: null };
}

const SCRIPT_APPROVED_ONWARD: ReadonlySet<PipelineStage> = new Set<PipelineStage>([
  "SCRIPT_APPROVED", "VOICE_GENERATED", "AUDIO_APPROVED", "SHOT_PLAN_GENERATED", "MOTION_APPROVED", "RENDERED", "QA_APPROVED", "EXPORTED",
]);

export const isScriptApproved = (stage: PipelineStage, status: VideoScript["status"] | undefined) => SCRIPT_APPROVED_ONWARD.has(stage) || status === "APPROVED";

/** A new panel list with one panel's camera motion type changed; its other camera fields are kept. */
export function withCameraMotion(panels: StoryboardPanelRef[], index: number, type: string): StoryboardPanelRef[] {
  return panels.map((p, i) => (i === index ? { ...p, camera_motion: { ...p.camera_motion, type } as StoryboardPanelRef["camera_motion"] } : p));
}
