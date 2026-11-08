import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { api } from "@panelflow/api-client";
import type { UtteranceEntity } from "@panelflow/shared-types";
import { CharactersTab } from "../CharactersTab";
import { normalizeCharacters } from "../storyModel";

// The engine's real shape: an id, a null canonical name.
const CHARACTERS = normalizeCharacters([
  { id: "c1", display_name: "Shangguan Yulin", canonical_name: null, aliases: ["Yulin"], description: "A young man", role: "UNKNOWN", status: "LIKELY" },
  { id: "c2", display_name: "Red Demon", canonical_name: null, aliases: [], description: "", role: "ANTAGONIST", status: "CONFIRMED" },
  { id: "c3", display_name: "Master", canonical_name: null, aliases: [], role: "SUPPORTING", status: "LIKELY" },
]);
const utt = (n: number, speaker: string, panel: string) => ({ utterance_id: `u${n}`, text_region_id: `r${n}`, panel_id: panel, speaker_character_id: speaker, source_text: "x", corrected_text: "x", utterance_type: "DIALOGUE", sequence: n }) as unknown as UtteranceEntity;
const UTTERANCES = [utt(3, "c1", "pn3"), utt(1, "c1", "pn1"), utt(2, "c2", "pn2"), utt(4, "c1", "pn1")];
const PANELS = [{ id: "pn1", sequence: 1 }, { id: "pn2", sequence: 2 }, { id: "pn3", sequence: 3 }];

interface Calls { update: any[][]; merge: any[][]; split: any[][]; changed: number }
function stub(over: Record<string, unknown> = {}) {
  const calls: Calls = { update: [], merge: [], split: [], changed: 0 };
  Object.assign(api as any, {
    updateCharacter: async (...a: any[]) => { calls.update.push(a); },
    mergeCharacters: async (...a: any[]) => { calls.merge.push(a); },
    splitCharacter: async (...a: any[]) => { calls.split.push(a); },
    ...over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;
const dialog = (d: Document) => d.querySelector('[role="dialog"]') as HTMLElement | null;
const dialogButton = (d: Document, label: string) => button(dialog(d)!, label);
/** The control a Field label points at. */
function field(d: Document, label: string): HTMLInputElement & HTMLSelectElement {
  const l = [...d.querySelectorAll("label")].find((x) => x.textContent?.trim() === label);
  assert.ok(l, `label ${label}`);
  return d.getElementById((l as HTMLLabelElement).htmlFor) as any;
}

async function show(characters = CHARACTERS, utterances = UTTERANCES, calls = { changed: 0 }) {
  const view = await mountPage(<CharactersTab projectId="p1" characters={characters} utterances={utterances} panels={PANELS} onChanged={async () => { calls.changed++; }} />);
  await view.settle();
  return view;
}

test("cards show display names when the canonical name is null, with the role and status in words", async () => {
  stub();
  const view = await show();
  const body = text(view.document);
  assert.ok(body.includes("Shangguan Yulin") && body.includes("Red Demon") && body.includes("Master"));
  assert.ok(body.includes("Status: LIKELY"));
  await view.cleanup();
});

test("Merge needs two characters and Split needs one", async () => {
  stub();
  const one = await show([CHARACTERS[0]]);
  assert.equal(button(one.document, "Merge identities")!.disabled, true);
  assert.equal(button(one.document, "Split identity")!.disabled, false);
  await one.cleanup();
  const none = await show([]);
  assert.equal(button(none.document, "Split identity")!.disabled, true);
  await none.cleanup();
});

test("editing one field sends only that field, under the normalised character id", async () => {
  const calls = stub();
  const bump = { changed: 0 };
  const view = await show(CHARACTERS, UTTERANCES, bump);
  await view.click(button(view.document, "Edit Red Demon")!);
  assert.ok(dialog(view.document));
  const save = () => dialogButton(view.document, "Save identity")!;
  assert.equal(save().disabled, true, "nothing changed yet");
  await view.setSelect(field(view.document, "Role"), "PROTAGONIST");
  assert.equal(save().disabled, false);
  await view.clickTwice(save());
  await view.settle();
  assert.equal(calls.update.length, 1, "saved once");
  assert.deepEqual(calls.update[0], ["p1", "c2", { role: "PROTAGONIST" }]);
  assert.equal(bump.changed, 1, "the narrative is reloaded");
  assert.equal(dialog(view.document), null, "the dialog closes");
  await view.cleanup();
});

test("a null canonical name is never overwritten with an empty string", async () => {
  const calls = stub();
  const view = await show();
  await view.click(button(view.document, "Edit Master")!);
  await view.setValue(field(view.document, "Display name"), "The Master");
  await view.click(dialogButton(view.document, "Save identity")!);
  await view.settle();
  assert.deepEqual(calls.update[0], ["p1", "c3", { display_name: "The Master" }]);
  assert.ok(!("canonical_name" in calls.update[0][2]));
  await view.cleanup();
});

test("aliases are a comma list, trimmed and de-duplicated", async () => {
  const calls = stub();
  const view = await show();
  await view.click(button(view.document, "Edit Shangguan Yulin")!);
  await view.setValue(field(view.document, "Aliases (comma separated)"), "Yulin, Young Master, Yulin ,");
  await view.click(dialogButton(view.document, "Save identity")!);
  await view.settle();
  assert.deepEqual(calls.update[0][2], { aliases: ["Yulin", "Young Master"] });
  await view.cleanup();
});

test("a blank display name is an inline error and cannot be saved", async () => {
  const calls = stub();
  const view = await show();
  await view.click(button(view.document, "Edit Master")!);
  await view.setValue(field(view.document, "Display name"), "   ");
  assert.ok(text(view.document).includes("Enter a name."));
  assert.equal(dialogButton(view.document, "Save identity")!.disabled, true);
  assert.equal(calls.update.length, 0);
  await view.cleanup();
});

test("a failed save keeps the dialog open and says why in words", async () => {
  stub({ updateCharacter: async () => { throw new Error("Character is locked by another change."); } });
  const view = await show();
  await view.click(button(view.document, "Edit Red Demon")!);
  await view.setSelect(field(view.document, "Role"), "MINOR");
  await view.click(dialogButton(view.document, "Save identity")!);
  await view.settle();
  assert.ok(dialog(view.document));
  assert.ok(text(view.document).includes("Couldn't save the character. Character is locked by another change."));
  await view.click(dialogButton(view.document, "Cancel")!); // leave no modal open: Radix keeps page state while one is
  await view.cleanup();
});

test("Cancel and Escape close the editor without saving, and focus returns to the Edit button", async () => {
  const calls = stub();
  const view = await show();
  const edit = button(view.document, "Edit Red Demon")!;
  edit.focus();
  await view.click(edit);
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(dialog(view.document), null);
  assert.equal(view.document.activeElement, edit);
  await view.click(edit);
  await act(async () => { dialog(view.document)!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  assert.equal(dialog(view.document), null);
  assert.equal(calls.update.length, 0);
  await view.cleanup();
});

test("Merge with the same character on both sides shows an inline error and calls nothing", async () => {
  const calls = stub();
  const view = await show();
  await view.click(button(view.document, "Merge identities")!);
  await view.setSelect(field(view.document, "Merge this identity (it will be removed)"), "c1");
  await view.setSelect(field(view.document, "Into this identity (it is kept)"), "c1");
  await view.click(dialogButton(view.document, "Review merge")!);
  assert.ok(text(view.document).includes("Choose two different characters."));
  assert.equal(calls.merge.length, 0);
  await view.cleanup();
});

test("Merge asks for a second confirmation, then merges once even on a double click", async () => {
  const calls = stub();
  const bump = { changed: 0 };
  const view = await show(CHARACTERS, UTTERANCES, bump);
  await view.click(button(view.document, "Merge identities")!);
  await view.setSelect(field(view.document, "Merge this identity (it will be removed)"), "c3");
  await view.setSelect(field(view.document, "Into this identity (it is kept)"), "c1");
  await view.click(dialogButton(view.document, "Review merge")!);
  assert.equal(calls.merge.length, 0, "nothing is merged by the review step");
  assert.ok(text(view.document).includes("This can't be undone."));
  assert.ok(dialog(view.document)!.textContent!.includes("Master") && dialog(view.document)!.textContent!.includes("Shangguan Yulin"));
  await view.clickTwice(dialogButton(view.document, "Merge identities")!);
  await view.settle();
  assert.deepEqual(calls.merge, [["p1", "c3", "c1"]]);
  assert.equal(bump.changed, 1);
  assert.equal(dialog(view.document), null);
  await view.cleanup();
});

test("a refused merge keeps the dialog open with the reason", async () => {
  stub({ mergeCharacters: async () => { throw new Error("Characters appear in the same panel."); } });
  const view = await show();
  await view.click(button(view.document, "Merge identities")!);
  await view.setSelect(field(view.document, "Merge this identity (it will be removed)"), "c3");
  await view.setSelect(field(view.document, "Into this identity (it is kept)"), "c1");
  await view.click(dialogButton(view.document, "Review merge")!);
  await view.click(dialogButton(view.document, "Merge identities")!);
  await view.settle();
  assert.ok(dialog(view.document));
  assert.ok(text(view.document).includes("Couldn't merge the characters. Characters appear in the same panel."));
  await view.click(dialogButton(view.document, "Back")!);
  await view.click(dialogButton(view.document, "Cancel")!);
  await view.cleanup();
});

test("Split offers only the panels where that character speaks, in order, and needs a name and a panel", async () => {
  const calls = stub();
  const view = await show();
  await view.click(button(view.document, "Split identity")!);
  await view.setSelect(field(view.document, "Character to split"), "c1");
  const boxes = () => [...dialog(view.document)!.querySelectorAll('input[type="checkbox"]')] as HTMLInputElement[];
  assert.deepEqual(boxes().map((b) => b.getAttribute("aria-label")), ["Panel 1", "Panel 3"], "panels 1 and 3, once each, in reading order");
  assert.equal(dialogButton(view.document, "Split identity")!.disabled, true, "no name and no panel yet");
  await view.setValue(field(view.document, "New character name"), "  Mysterious Stranger ");
  assert.equal(dialogButton(view.document, "Split identity")!.disabled, true, "still no panel");
  await view.click(boxes()[1]);
  assert.equal(dialogButton(view.document, "Split identity")!.disabled, false);
  await view.clickTwice(dialogButton(view.document, "Split identity")!);
  await view.settle();
  assert.deepEqual(calls.split, [["p1", "c1", "Mysterious Stranger", ["pn3"]]]);
  await view.cleanup();
});

test("Split explains when a character has no attributed lines", async () => {
  const calls = stub();
  const view = await show();
  await view.click(button(view.document, "Split identity")!);
  await view.setSelect(field(view.document, "Character to split"), "c3");
  assert.ok(text(view.document).includes("No lines are attributed to this character"));
  await view.setValue(field(view.document, "New character name"), "Someone");
  assert.equal(dialogButton(view.document, "Split identity")!.disabled, true);
  assert.equal(calls.split.length, 0);
  await view.cleanup();
});
