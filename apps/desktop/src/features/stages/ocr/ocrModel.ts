import type { CharacterEntity, Panel, TextRegion } from "@panelflow/shared-types";
import type { Tone } from "@panelflow/ui-v2";
import { characterName } from "../story/storyModel";

export { engineProblem, pickEngine } from "../kit/ocrEngine";

const words = (value: string) => {
  const spaced = value.toLowerCase().replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
};

// The engine also sends BLURRED (text that was blurred out) and IGNORED, besides the statuses in the shared type.
const STATUS: Record<string, { word: string; tone: Tone }> = {
  NEEDS_REVIEW: { word: "Needs review", tone: "warn" },
  CONFIRMED: { word: "Confirmed", tone: "ok" },
  DETECTED: { word: "Detected", tone: "accent" },
  BLURRED: { word: "Blurred", tone: "accent" },
  IGNORED: { word: "Ignored", tone: "neutral" },
  REJECTED: { word: "Ignored", tone: "neutral" },
};
export function regionStatus(status: string): { word: string; tone: Tone } {
  return STATUS[status] ?? { word: words(status), tone: "neutral" };
}
export const regionTone = (region: Pick<TextRegion, "status">): Tone => regionStatus(region.status).tone;

const TYPES: Record<string, string> = { SPEECH: "Speech", NARRATION: "Narration", THOUGHT: "Thought", SFX: "Sound effect", CAPTION: "Caption", UNKNOWN: "Unknown", REDACTED: "Redacted" };
export const regionTypeWord = (type: string) => TYPES[type] ?? words(type);

/** The text a region has: the person's correction, else what the engine read. */
const textOf = (r: Pick<TextRegion, "corrected_text" | "raw_text">) => ((r.corrected_text ?? "").trim() ? (r.corrected_text as string) : (r.raw_text ?? ""));
const hasText = (r: Pick<TextRegion, "corrected_text" | "raw_text">) => textOf(r).trim() !== "";

export const needsReview = (regions: TextRegion[]) => regions.filter((r) => r.status === "NEEDS_REVIEW");

export function canConfirmOCR({ regions, running }: { regions: TextRegion[]; running: boolean }): { ok: boolean; reason: string | null } {
  if (running) return { ok: false, reason: "Text is still being read." };
  if (regions.length === 0) return { ok: false, reason: "Run text detection first." };
  const open = needsReview(regions).length;
  if (open > 0) return { ok: false, reason: `${open} ${open === 1 ? "region still needs" : "regions still need"} review.` };
  return { ok: true, reason: null };
}

/** What confirming a region writes. A region with no text is never confirmed with a placeholder: it must be typed or ignored. */
export function confirmPatch(region: TextRegion): { status: "CONFIRMED"; corrected_text: string } | null {
  return hasText(region) ? { status: "CONFIRMED", corrected_text: textOf(region) } : null;
}

const byReading = (a: TextRegion, b: TextRegion) => a.sequence_in_panel - b.sequence_in_panel;
export function regionsByPanel(regions: TextRegion[]): Record<string, TextRegion[]> {
  const grouped: Record<string, TextRegion[]> = {};
  for (const r of regions) (grouped[r.panel_id] ??= []).push(r);
  for (const list of Object.values(grouped)) list.sort(byReading);
  return grouped;
}

export type PanelFilter = "all" | "needs_review" | "no_text" | "has_text";
export function panelFilter(panels: Panel[], regions: TextRegion[], filter: PanelFilter): Panel[] {
  if (filter === "all") return panels;
  const grouped = regionsByPanel(regions);
  const keep = (p: Panel) => {
    const own = grouped[p.id] ?? [];
    if (filter === "needs_review") return own.some((r) => r.status === "NEEDS_REVIEW");
    return filter === "has_text" ? own.some(hasText) : !own.some(hasText);
  };
  return panels.filter(keep);
}
export function filterCounts(panels: Panel[], regions: TextRegion[]): Record<PanelFilter, number> {
  return { all: panels.length, needs_review: panelFilter(panels, regions, "needs_review").length, has_text: panelFilter(panels, regions, "has_text").length, no_text: panelFilter(panels, regions, "no_text").length };
}

/** The next region that needs review in reading order (panel order, then place in the panel), wrapping at the end. */
export function jumpToNextFlagged(regions: TextRegion[], panels: Panel[], currentRegionId: string | null): TextRegion | null {
  const order = new Map(panels.map((p, i) => [p.id, i]));
  const ordered = [...regions].sort((a, b) => (order.get(a.panel_id) ?? Infinity) - (order.get(b.panel_id) ?? Infinity) || byReading(a, b));
  const flagged = ordered.filter((r) => r.status === "NEEDS_REVIEW");
  if (flagged.length === 0) return null;
  const at = currentRegionId ? ordered.findIndex((r) => r.id === currentRegionId) : -1;
  return ordered.slice(at + 1).find((r) => r.status === "NEEDS_REVIEW") ?? flagged[0];
}

export interface EditForm { corrected_text: string; region_type: string; status: string; speaker_character_id: string }
export function editForm(region: TextRegion): EditForm {
  return { corrected_text: textOf(region), region_type: region.region_type, status: region.status, speaker_character_id: region.speaker_character_id || "UNKNOWN" };
}

export type RegionPatch = Partial<{
  corrected_text: string; corrected_by: string; correction_status: string; region_type: string; status: string; speaker_character_id: string; speaker_assignment_method: string;
}>;

/** Only the fields the person changed. A changed speaker is a manual choice. */
export function regionPatch(region: TextRegion, form: EditForm): RegionPatch {
  const before = editForm(region);
  const patch: RegionPatch = {};
  if (form.corrected_text !== before.corrected_text) Object.assign(patch, { corrected_text: form.corrected_text, corrected_by: "HUMAN", correction_status: "EDITED" });
  if (form.region_type !== before.region_type) patch.region_type = form.region_type;
  if (form.status !== before.status) patch.status = form.status;
  if (form.speaker_character_id !== before.speaker_character_id) Object.assign(patch, { speaker_character_id: form.speaker_character_id, speaker_assignment_method: "MANUAL" });
  return patch;
}

/** Approve: the text is always written (so the canonical text is the person's), blank text is refused. Unchanged machine text counts as verified. */
export function approvePatch(region: TextRegion, form: EditForm): RegionPatch | null {
  const text = form.corrected_text;
  if (text.trim() === "") return null;
  const edited = text !== (region.raw_text ?? "");
  return { ...regionPatch(region, form), status: "CONFIRMED", corrected_text: text, corrected_by: "HUMAN", correction_status: edited ? "EDITED" : "VERIFIED" };
}

const SPECIAL = [{ id: "UNKNOWN", label: "Unknown" }, { id: "NARRATOR", label: "Narrator" }, { id: "SFX", label: "Sound effect" }];
export interface SpeakerOption { id: string; label: string }
/** Unknown, Narrator, Sound effect, then characters by name. A current id that matches nobody stays selectable so a save never overwrites it. */
export function speakerOptions(characters: CharacterEntity[], current?: string | null): SpeakerOption[] {
  const named = [...characters].map((c) => ({ id: c.character_id, label: characterName(c) })).sort((a, b) => a.label.localeCompare(b.label));
  const options = [...SPECIAL, ...named];
  if (current && !options.some((o) => o.id === current)) options.push({ id: current, label: "Unknown (not in the character list)" });
  return options;
}
export function speakerWord(id: string | null | undefined, characters: CharacterEntity[]): string {
  const known = id ? speakerOptions(characters).find((o) => o.id === id) : null;
  return known?.label ?? "Unknown";
}
