import type { SceneCrossCheck, SceneItemStatus, ScenePlanData, SceneRun } from "@panelflow/api-client";

export type Confidence = "high" | "medium" | "low";

export const confidenceLabel = (c: number): Confidence => (c >= 0.8 ? "high" : c >= 0.5 ? "medium" : "low");

export const TAGS = ["emotion", "pose", "camera", "identity", "style", "other"] as const;

/** The action words a plan can use per scene type (mirrors engine/original/playbooks/*.json). */
export const STATES: Record<string, string[]> = {
  fight: ["striking", "blocking", "readying", "struck", "falling", "dodging"],
  emotion: ["grieving", "joyful", "proud", "afraid", "angry", "guilty", "hopeful", "lost", "peaceful", "nostalgic", "ashamed", "determined", "tender", "forgiving"],
  concept_art: ["standing", "walking", "watching", "working", "resting", "travelling"],
};

export const ANGLES: { value: string; label: string }[] = [
  { value: "eye_level", label: "Eye level" }, { value: "low", label: "Low angle" }, { value: "high", label: "High angle" }, { value: "dutch", label: "Tilted" },
];

const STATUS_TEXT: Record<SceneItemStatus, string> = {
  agreed: "Both judges agree",
  resolved: "Settled after a second look",
  disputed: "Judges still disagree: your call",
  single: "One judge only",
  unjudged: "Could not be judged",
};

const CAMERA_WORDS: Record<string, string> = { looks_up: "looking up (low angle)", level: "level", looks_down: "looking down (high angle)", tilted: "tilted" };

export function humanValue(key: string, value: string | null): string {
  if (value === null || value === undefined || value === "") return "unclear";
  return key === "camera" ? (CAMERA_WORDS[value] ?? value) : value;
}

export interface PlanCheck { expected: string | null; match: boolean | null }

export interface ItemRow {
  key: string;
  label: string;
  status: SceneItemStatus;
  statusText: string;
  value: string | null;
  valueText: string;
  confidencePct: number;
  confidence: Confidence;
  perJudge: { judge: string; round1: string | null; round2: string | null; evidence: string }[];
  flipped: string[];
  highlight: boolean; // the owner has to decide this one
  plan: PlanCheck; // what the plan asked for, and whether the judges' answer matches it
}

function labelFor(key: string): string {
  if (key === "camera") return "Camera angle";
  if (key === "people") return "People in the picture";
  const m = /^action:(\d+)$/.exec(key);
  return m ? `Person ${Number(m[1]) + 1} (from the left)` : key;
}

export function itemRows(cc: SceneCrossCheck | null | undefined, plan?: ScenePlanData): ItemRow[] {
  const items = cc?.items ?? [];
  return items.map((it) => ({
    key: it.key,
    label: labelFor(it.key),
    status: it.status,
    statusText: STATUS_TEXT[it.status] ?? it.status,
    value: it.value,
    valueText: humanValue(it.key, it.value),
    confidencePct: Math.round(it.confidence * 100),
    confidence: confidenceLabel(it.confidence),
    perJudge: Object.entries(it.answers ?? {}).map(([judge, a]) => ({ judge, round1: a.round1, round2: a.round2, evidence: a.evidence })),
    flipped: it.suspect_flips ?? [],
    highlight: it.status === "disputed" || it.status === "unjudged",
    plan: planMatch(plan ?? {}, it.key, it.value),
  }));
}

export interface OwnerState { liked: number | null; agrees: boolean; note: string; goodTags: string[]; wrongTags: string[]; choices?: Record<string, string> }

/** The owner has chosen how much they liked it AND given a reason: agreeing with the AI, a comment, or a tag. */
export function ownerCanSubmit(s: OwnerState): boolean {
  return s.liked !== null && (s.agrees || s.note.trim().length > 0 || s.goodTags.length > 0 || s.wrongTags.length > 0 || Object.keys(s.choices ?? {}).length > 0);
}

export const waitingFirst = (runs: SceneRun[]): SceneRun | null => runs.find((r) => r.review_state === "pending") ?? null;

const ANGLE_WORDS: Record<string, string> = { eye_level: "eye-level view", low: "low angle", high: "high angle", dutch: "tilted angle" };
const LIGHT_WORDS: Record<string, string> = { front: "light from the front", back: "light from behind", left: "light from the left", right: "light from the right", top: "light from above", below: "light from below" };
const SIDE_WORDS: Record<string, string> = { left: "on the left", center: "in the centre", right: "on the right" };

/** The plan as one plain sentence (same wording as the engine's `plan_to_words`). */
export function planSummary(plan: ScenePlanData): string {
  if (!plan || !plan.camera) return "";
  const parts = [`${ANGLE_WORDS[plan.camera.angle] ?? plan.camera.angle}, ${plan.camera.distance} shot`];
  for (const a of plan.actors ?? []) parts.push(`${a.id} ${SIDE_WORDS[a.side] ?? a.side} ${a.action_state}`);
  if (plan.light?.direction) parts.push(LIGHT_WORDS[plan.light.direction] ?? plan.light.direction);
  return parts.join(", ");
}


const SEEN: Record<string, string> = { eye_level: "level", low: "looks_up", high: "looks_down", dutch: "tilted" };
const ANGLE_EXPECT: Record<string, string> = { eye_level: "eye level", low: "low angle (looking up)", high: "high angle (looking down)", dutch: "tilted angle" };
const SIDE_ORDER: Record<string, number> = { left: 0, center: 1, right: 2 };
// feelings a 9B vision model cannot tell apart (mirrors state_groups in engine/original/playbooks/emotion.json)
const FAMILIES: string[][] = [
  ["grieving", "lost", "guilty", "ashamed"],
  ["joyful", "proud", "hopeful", "tender", "peaceful", "nostalgic", "forgiving"],
  ["afraid", "angry", "determined"],
];
const sameState = (sceneType: string, a: string, b: string) => a === b || (sceneType === "emotion" && FAMILIES.some((g) => g.includes(a) && g.includes(b)));

/** What the plan asked for on one judged item, and whether the judges' final answer matches it (null = cannot tell). Persons are matched from the left, like the judges read them. */
export function planMatch(plan: ScenePlanData, key: string, value: string | null): PlanCheck {
  if (!plan?.camera) return { expected: null, match: null };
  if (key === "camera") return { expected: ANGLE_EXPECT[plan.camera.angle] ?? plan.camera.angle, match: value === null ? null : value === SEEN[plan.camera.angle] };
  const actors: { side: string; action_state: string }[] = [...(plan.actors ?? [])].sort((a, b) => (SIDE_ORDER[a.side] ?? 1) - (SIDE_ORDER[b.side] ?? 1));
  if (key === "people") return { expected: String(actors.length), match: value === null ? null : value === String(actors.length) };
  const m = /^action:(\d+)$/.exec(key);
  const actor = m ? actors[Number(m[1])] : undefined;
  if (!actor) return { expected: null, match: null };
  return { expected: actor.action_state, match: value === null ? null : sameState(String(plan.scene_type ?? ""), value, actor.action_state) };
}

const OVERDUE_MS = 10 * 60 * 1000;

/** The judges never reported back for a picture that is more than ten minutes old: stop waiting and say so. */
export function analysisOverdue(run: Pick<SceneRun, "created_at" | "analysis">, nowMs: number = Date.now()): boolean {
  if (run.analysis || !run.created_at) return false;
  const stamp = /[zZ]|[+-]\d\d:?\d\d$/.test(run.created_at) ? run.created_at : `${run.created_at}Z`; // the engine stores UTC without a zone
  const created = Date.parse(stamp);
  return Number.isFinite(created) && nowMs - created > OVERDUE_MS;
}

/** The distinct first answers of the judges on a row the owner has to settle. */
export function choiceOptions(row: ItemRow): { value: string; judges: string[] }[] {
  if (!row.highlight) return [];
  const out: { value: string; judges: string[] }[] = [];
  for (const j of row.perJudge) {
    if (j.round1 === null || j.round1 === undefined) continue;
    const found = out.find((o) => o.value === j.round1);
    if (found) found.judges.push(j.judge);
    else out.push({ value: j.round1, judges: [j.judge] });
  }
  return out;
}
