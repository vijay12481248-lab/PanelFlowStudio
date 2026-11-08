import test from "node:test";
import assert from "node:assert/strict";
import type { Panel, TextRegion } from "@panelflow/shared-types";
import {
  approvePatch, canConfirmOCR, confirmPatch, editForm, filterCounts, jumpToNextFlagged, needsReview, panelFilter, regionPatch, regionStatus, regionTone, regionTypeWord,
  regionsByPanel, speakerOptions, speakerWord,
} from "../ocrModel";

// Real shapes: the engine sends statuses BLURRED and IGNORED as well as NEEDS_REVIEW, types such as REDACTED, and speaker id "UNKNOWN".
const region = (id: string, panel: string, seq: number, over: Record<string, unknown> = {}) => ({
  id, panel_id: panel, sequence_in_panel: seq, status: "NEEDS_REVIEW", region_type: "SPEECH", raw_text: "", corrected_text: "", speaker_character_id: null, speaker_assignment_method: null, x: 0, y: 0, width: 10, height: 10, ...over,
}) as unknown as TextRegion;
const panel = (id: string, n: number) => ({ id, sequence: n, page_sequence: n }) as unknown as Panel;

test("a region's status and type are said in words, including the ones the engine really sends", () => {
  assert.deepEqual(regionStatus("NEEDS_REVIEW"), { word: "Needs review", tone: "warn" });
  assert.deepEqual(regionStatus("CONFIRMED"), { word: "Confirmed", tone: "ok" });
  assert.equal(regionStatus("IGNORED").word, "Ignored");
  assert.equal(regionStatus("REJECTED").word, "Ignored");
  assert.equal(regionStatus("BLURRED").word, "Blurred");
  assert.equal(regionStatus("SOME_NEW_STATE").word, "Some new state");
  assert.equal(regionTypeWord("SFX"), "Sound effect");
  assert.equal(regionTypeWord("REDACTED"), "Redacted");
  assert.equal(regionTypeWord("odd_type"), "Odd type");
  assert.equal(regionTone(region("a", "p", 1, { status: "CONFIRMED" })), "ok");
});

test("only NEEDS_REVIEW regions need review, and the approval gate says why it is closed", () => {
  const regions = [region("a", "p1", 1), region("b", "p1", 2, { status: "CONFIRMED" }), region("c", "p2", 1, { status: "IGNORED" }), region("d", "p2", 2)];
  assert.deepEqual(needsReview(regions).map((r) => r.id), ["a", "d"]);
  assert.deepEqual(canConfirmOCR({ regions: [], running: false }), { ok: false, reason: "Run text detection first." });
  assert.deepEqual(canConfirmOCR({ regions, running: true }), { ok: false, reason: "Text is still being read." });
  assert.deepEqual(canConfirmOCR({ regions, running: false }), { ok: false, reason: "2 regions still need review." });
  assert.equal(canConfirmOCR({ regions: [region("a", "p1", 1), region("b", "p1", 2)], running: false }).reason, "2 regions still need review.");
  assert.equal(canConfirmOCR({ regions: [region("a", "p1", 1)], running: false }).reason, "1 region still needs review.");
  assert.deepEqual(canConfirmOCR({ regions: [region("b", "p1", 2, { status: "CONFIRMED" }), region("i", "p1", 3, { status: "BLURRED" })], running: false }), { ok: true, reason: null });
});

test("confirming a region with no text writes nothing: it must be typed or ignored, and never becomes a placeholder", () => {
  assert.equal(confirmPatch(region("a", "p", 1)), null);
  assert.equal(confirmPatch(region("a", "p", 1, { raw_text: "   \n ", corrected_text: "  " })), null);
  assert.deepEqual(confirmPatch(region("a", "p", 1, { raw_text: "Hello" })), { status: "CONFIRMED", corrected_text: "Hello" });
  assert.deepEqual(confirmPatch(region("a", "p", 1, { raw_text: "Helo", corrected_text: "Hello" })), { status: "CONFIRMED", corrected_text: "Hello" });
  assert.notEqual(JSON.stringify(confirmPatch(region("a", "p", 1, { raw_text: "x" }))), "...");
});

test("regions are grouped by panel in reading order", () => {
  const grouped = regionsByPanel([region("b", "p1", 2), region("a", "p1", 1), region("c", "p2", 1)]);
  assert.deepEqual(grouped["p1"].map((r) => r.id), ["a", "b"]);
  assert.deepEqual(grouped["p2"].map((r) => r.id), ["c"]);
});

test("the panel filters and their counts: a panel with only blank regions has no text", () => {
  const panels = [panel("p1", 1), panel("p2", 2), panel("p3", 3), panel("p4", 4)];
  const regions = [
    region("a", "p1", 1, { raw_text: "Hi", status: "CONFIRMED" }),
    region("b", "p2", 1, { raw_text: "", status: "NEEDS_REVIEW" }),
    region("c", "p3", 1, { corrected_text: "Typed", status: "NEEDS_REVIEW" }),
  ];
  assert.deepEqual(panelFilter(panels, regions, "all").map((p) => p.id), ["p1", "p2", "p3", "p4"]);
  assert.deepEqual(panelFilter(panels, regions, "needs_review").map((p) => p.id), ["p2", "p3"]);
  assert.deepEqual(panelFilter(panels, regions, "has_text").map((p) => p.id), ["p1", "p3"]);
  assert.deepEqual(panelFilter(panels, regions, "no_text").map((p) => p.id), ["p2", "p4"]);
  assert.deepEqual(filterCounts(panels, regions), { all: 4, needs_review: 2, has_text: 2, no_text: 2 });
});

test("Jump to next flagged goes in reading order across panels, wraps, and says nothing when nothing is flagged", () => {
  const panels = [panel("p1", 1), panel("p2", 2), panel("p3", 3)];
  const regions = [region("a", "p1", 1, { status: "CONFIRMED" }), region("b", "p2", 2), region("c", "p2", 1), region("d", "p3", 1)];
  assert.equal(jumpToNextFlagged(regions, panels, null)?.id, "c", "from nothing, the first flagged region");
  assert.equal(jumpToNextFlagged(regions, panels, "c")?.id, "b", "within the panel by place");
  assert.equal(jumpToNextFlagged(regions, panels, "b")?.id, "d", "into the next panel");
  assert.equal(jumpToNextFlagged(regions, panels, "d")?.id, "c", "wraps to the start");
  assert.equal(jumpToNextFlagged(regions, panels, "a")?.id, "c", "from a region that is not flagged");
  assert.equal(jumpToNextFlagged([region("a", "p1", 1, { status: "CONFIRMED" })], panels, null), null);
});

test("the edit form starts from the correction, else the machine text, and a save sends only what changed", () => {
  const r = region("a", "p", 1, { raw_text: "Helo", corrected_text: "", speaker_character_id: "UNKNOWN", speaker_assignment_method: "BALLOON_GEOMETRY" });
  const form = editForm(r);
  assert.deepEqual(form, { corrected_text: "Helo", region_type: "SPEECH", status: "NEEDS_REVIEW", speaker_character_id: "UNKNOWN" });
  assert.deepEqual(regionPatch(r, form), {}, "nothing changed, nothing sent");
  assert.deepEqual(regionPatch(r, { ...form, region_type: "THOUGHT" }), { region_type: "THOUGHT" });
  assert.deepEqual(regionPatch(r, { ...form, corrected_text: "Hello" }), { corrected_text: "Hello", corrected_by: "HUMAN", correction_status: "EDITED" });
  assert.deepEqual(regionPatch(r, { ...form, speaker_character_id: "NARRATOR" }), { speaker_character_id: "NARRATOR", speaker_assignment_method: "MANUAL" });
  assert.deepEqual(editForm(region("b", "p", 1, { raw_text: "Helo", corrected_text: "Hello" })).corrected_text, "Hello");
  assert.equal(editForm(region("c", "p", 1)).speaker_character_id, "UNKNOWN", "no speaker is Unknown");
  assert.equal(Object.keys(regionPatch(r, { ...form, status: "CONFIRMED" })).join(), "status");
});

test("Approve refuses blank text, and approving unchanged machine text is verified, not edited", () => {
  const r = region("a", "p", 1, { raw_text: "Hello" });
  assert.equal(approvePatch(r, { ...editForm(r), corrected_text: "  " }), null);
  assert.deepEqual(approvePatch(r, editForm(r)), { status: "CONFIRMED", corrected_text: "Hello", corrected_by: "HUMAN", correction_status: "VERIFIED" });
  assert.deepEqual(approvePatch(r, { ...editForm(r), corrected_text: "Hello!" }), { status: "CONFIRMED", corrected_text: "Hello!", corrected_by: "HUMAN", correction_status: "EDITED" });
});

test("speaker choices are Unknown, Narrator, Sound effect, then characters by name; an id that matches nobody is kept and called unknown", () => {
  const characters = [{ character_id: "c2", canonical_name: null, display_name: "Zed" }, { character_id: "c1", canonical_name: "Anna", display_name: "Anna R." }] as any;
  assert.deepEqual(speakerOptions(characters).map((o) => [o.id, o.label]), [["UNKNOWN", "Unknown"], ["NARRATOR", "Narrator"], ["SFX", "Sound effect"], ["c1", "Anna"], ["c2", "Zed"]]);
  const gone = speakerOptions(characters, "deadbeef");
  assert.equal(gone[gone.length - 1].id, "deadbeef");
  assert.equal(gone[gone.length - 1].label, "Unknown (not in the character list)");
  assert.equal(speakerOptions(characters, "c1").length, 5, "a known id adds nothing");
  assert.equal(speakerWord("c1", characters), "Anna");
  assert.equal(speakerWord("UNKNOWN", characters), "Unknown");
  assert.equal(speakerWord(null, characters), "Unknown");
  assert.equal(speakerWord("deadbeef", characters), "Unknown");
});
