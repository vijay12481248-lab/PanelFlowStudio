import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { button, panel, region, show, stub, text, until } from "./ocrFixtures";

const PANELS = [panel("pa", 1), panel("pb", 2)];
const REGIONS = () => [
  region("r1", "pa", 1, { raw_text: "Helo", raw_confidence: 0.95, ocr_engine: "windows_media" }),
  region("r2", "pa", 2),
  region("r3", "pb", 1, { raw_text: "Later" }),
];
const CHARACTERS = [{ id: "c1", display_name: "Anna", canonical_name: null, aliases: [] }];

const area = (d: Document) => d.querySelector('textarea[aria-label="Corrected text"]') as HTMLTextAreaElement;
const select = (d: Document, label: string) => d.querySelector(`select[aria-label="${label}"]`) as HTMLSelectElement;
const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const typeInto = (el: HTMLTextAreaElement, value: string) => act(async () => {
  Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new window.Event("input", { bubbles: true }));
});
const choose = (el: HTMLSelectElement, value: string) => act(async () => {
  Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new window.Event("change", { bubbles: true }));
});
const current = (d: Document) => d.querySelector("[data-list-region][aria-current=\"true\"]")?.getAttribute("data-list-region") ?? null;

async function open(regionNumber: number, opts: Parameters<typeof stub>[0] = {}) {
  const { over, ...rest } = opts;
  const calls = stub({ panels: PANELS, regions: REGIONS(), ...rest, over: { listCharacters: async () => CHARACTERS, ...(over ?? {}) } });
  const view = await show();
  await until(() => Boolean(button(view.document, `Select region ${regionNumber}`)));
  await view.click(button(view.document, `Select region ${regionNumber}`)!);
  await until(() => Boolean(area(view.document)));
  return { calls, view };
}

test("the editor shows the three layers: the machine reading, the correction and the speaker", async () => {
  const { view } = await open(1);
  const t = text(view.document);
  assert.ok(t.includes("Machine reading") && t.includes("Correction") && t.includes("Speaker"));
  assert.ok(view.document.querySelector("[data-machine-text]")!.textContent!.includes("Helo"));
  assert.ok(t.includes("windows_media") && t.includes("95%"));
  assert.equal(area(view.document).value, "Helo", "starts from the machine text when there is no correction");
  assert.ok(!/Milestone|Layer 1|Layer 2|Layer 3/.test(t));
  await view.cleanup();
});

test("Save is disabled until something changed, then sends only the changed fields, once on a double click", async () => {
  const { calls, view } = await open(1);
  assert.equal(button(view.document, "Save")!.disabled, true);
  await choose(select(view.document, "Region type"), "THOUGHT");
  assert.equal(button(view.document, "Save")!.disabled, false);
  await view.clickTwice(button(view.document, "Save")!);
  await until(() => calls.update.length > 0);
  assert.deepEqual(calls.update, [["p1", "r1", { region_type: "THOUGHT" }]]);
  await view.cleanup();
});

test("a corrected text is saved as the person's correction", async () => {
  const { calls, view } = await open(1);
  await typeInto(area(view.document), "Hello");
  await view.click(button(view.document, "Save")!);
  await until(() => calls.update.length > 0);
  assert.deepEqual(calls.update[0][2], { corrected_text: "Hello", corrected_by: "HUMAN", correction_status: "EDITED" });
  await view.cleanup();
});

test("Approve of blank text is refused with the sentence and sends nothing", async () => {
  const { calls, view } = await open(2);
  assert.equal(area(view.document).value, "");
  await view.click(button(view.document, "Approve")!);
  assert.ok(text(view.document).includes("Type the text, or ignore this region."));
  assert.equal(calls.update.length, 0);
  await view.cleanup();
});

test("Approve sends CONFIRMED with the text once, and Ignore sends REJECTED, the status the export and audio steps leave out", async () => {
  const { calls, view } = await open(1);
  await view.clickTwice(button(view.document, "Approve")!);
  await until(() => calls.update.length > 0);
  assert.deepEqual(calls.update, [["p1", "r1", { status: "CONFIRMED", corrected_text: "Helo", corrected_by: "HUMAN", correction_status: "VERIFIED" }]]);
  await view.cleanup();
  const second = await open(1);
  await second.view.clickTwice(button(second.view.document, "Ignore this region")!);
  await until(() => second.calls.update.length > 0);
  assert.deepEqual(second.calls.update, [["p1", "r1", { status: "REJECTED" }]]);
  await second.view.cleanup();
});

test("Save and next saves, then selects the next region of the panel; on the last one it goes to the next flagged region", async () => {
  const { calls, view } = await open(1);
  await typeInto(area(view.document), "Hello");
  await view.click(button(view.document, "Save and next")!);
  await until(() => current(view.document) === "r2");
  assert.equal(calls.update.length, 1);
  assert.equal(current(view.document), "r2");
  await typeInto(area(view.document), "More");
  await view.click(button(view.document, "Save and next")!);
  await until(() => current(view.document) === "r3");
  assert.equal(current(view.document), "r3", "the panel is done, so the next flagged region in the next panel");
  await view.cleanup();
});

test("Save and next with nothing changed just moves on, and sends nothing", async () => {
  const { calls, view } = await open(1);
  await view.click(button(view.document, "Save and next")!);
  await until(() => current(view.document) === "r2");
  assert.equal(calls.update.length, 0);
  await view.cleanup();
});

test("Delete region asks first, Cancel sends nothing, and confirming deletes once and clears the selection", async () => {
  const deleted: any[][] = [];
  const { view } = await open(1, { over: { deleteTextRegion: async (...a: any[]) => { deleted.push(a); } } });
  await view.click(button(view.document, "Delete region")!);
  await until(() => Boolean(dialogButton(view.document, "Cancel")));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(deleted.length, 0);
  await view.click(button(view.document, "Delete region")!);
  await until(() => Boolean(dialogButton(view.document, "Delete region")));
  await view.clickTwice(dialogButton(view.document, "Delete region")!);
  await until(() => deleted.length > 0);
  assert.deepEqual(deleted, [["p1", "r1"]]);
  await until(() => current(view.document) === null);
  assert.equal(area(view.document), null, "the editor closes");
  await view.cleanup();
});

test("Read again sends the chosen engine once and shows the new machine text", async () => {
  const reads: any[][] = [];
  const regions = REGIONS();
  const { view } = await open(1, { regions, over: { ocrSingleRegion: async (...a: any[]) => { reads.push(a); regions[0] = { ...regions[0], raw_text: "Hello again" } as any; return regions[0]; } } });
  await view.clickTwice(button(view.document, "Read again")!);
  await until(() => reads.length > 0);
  assert.deepEqual(reads, [["p1", "r1", "windows_media", "en"]]);
  await until(() => view.document.querySelector("[data-machine-text]")!.textContent!.includes("Hello again"));
  assert.ok(view.document.querySelector("[data-machine-text]")!.textContent!.includes("Hello again"));
  await view.cleanup();
});

test("a failed save keeps what was typed and says why", async () => {
  const { view } = await open(1, { over: { updateTextRegion: async () => { throw new Error("Region was changed elsewhere."); } } });
  await typeInto(area(view.document), "Typed text");
  await view.click(button(view.document, "Save")!);
  await until(() => text(view.document).includes("Couldn't save the region."));
  assert.ok(text(view.document).includes("Couldn't save the region. Region was changed elsewhere."));
  assert.equal(area(view.document).value, "Typed text");
  await view.cleanup();
});

test("a second action while one is running is not sent", async () => {
  const sent: any[][] = [];
  const { view } = await open(1, { over: { updateTextRegion: async (...a: any[]) => { sent.push(a); await new Promise((r) => setTimeout(r, 80)); return { id: a[1] }; } } });
  await typeInto(area(view.document), "Hello");
  await act(async () => {
    button(view.document, "Save")!.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    button(view.document, "Approve")!.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 200));
  assert.equal(sent.length, 1, "the Approve pressed while Save was running was not sent");
  await view.cleanup();
});

test("the speaker choice shows names, keeps an id that matches nobody as Unknown, and a change is a manual choice", async () => {
  const regions = [region("r1", "pa", 1, { raw_text: "Hi", speaker_character_id: "deadbeef", speaker_assignment_method: "BALLOON_GEOMETRY" })];
  const { calls, view } = await open(1, { regions });
  const speaker = select(view.document, "Speaker");
  const labels = [...speaker.querySelectorAll("option")].map((o) => o.textContent);
  assert.deepEqual(labels, ["Unknown", "Narrator", "Sound effect", "Anna", "Unknown (not in the character list)"]);
  assert.equal(speaker.value, "deadbeef");
  assert.ok(text(view.document).includes("Balloon shape"), "how it was assigned is shown in words");
  await choose(speaker, "c1");
  await view.click(button(view.document, "Save")!);
  await until(() => calls.update.length > 0);
  assert.deepEqual(calls.update[0][2], { speaker_character_id: "c1", speaker_assignment_method: "MANUAL" });
  await view.cleanup();
});

test("the quick text tools change the correction without saving it", async () => {
  const regions = [region("r1", "pa", 1, { raw_text: "  hello   world. fine  " })];
  const { calls, view } = await open(1, { regions });
  await view.click(button(view.document, "Trim spaces")!);
  assert.equal(area(view.document).value, "hello world. fine");
  await view.click(button(view.document, "Sentence case")!);
  assert.equal(area(view.document).value, "Hello world. Fine");
  await view.click(button(view.document, "Clear text")!);
  assert.equal(area(view.document).value, "");
  assert.equal(calls.update.length, 0);
  await view.cleanup();
});

test("a status the engine set itself, such as Blurred, is shown and kept when other fields are saved", async () => {
  const regions = [region("r1", "pa", 1, { raw_text: "Hi", status: "BLURRED", region_type: "REDACTED" })];
  const { calls, view } = await open(1, { regions });
  assert.equal(select(view.document, "Region status").value, "BLURRED");
  assert.equal(select(view.document, "Region type").value, "REDACTED");
  await typeInto(area(view.document), "Hi there");
  await view.click(button(view.document, "Save")!);
  await until(() => calls.update.length > 0);
  assert.deepEqual(Object.keys(calls.update[0][2]).sort(), ["corrected_by", "corrected_text", "correction_status"], "status and type are not sent");
  await view.cleanup();
});

test("drawing a box on the crop creates a manual text region once", async () => {
  const created: any[][] = [];
  const proto = (window as any).Element.prototype;
  const saved = proto.getBoundingClientRect;
  const { view } = await open(1, { over: { createManualTextRegion: async (...a: any[]) => { created.push(a); return region("new", "pa", 3); } } });
  proto.getBoundingClientRect = () => ({ left: 0, top: 0, width: 768, height: 360, right: 768, bottom: 360, x: 0, y: 0, toJSON() {} });
  await view.click(button(view.document, "Add text region")!);
  const overlay = view.document.querySelector("[data-canvas-overlay]")!;
  const ptr = (type: string, x: number, y: number) => act(async () => { overlay.dispatchEvent(new (window as any).MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 })); });
  await ptr("pointerdown", 100, 100);
  await ptr("pointermove", 300, 200);
  await ptr("pointerup", 300, 200);
  await until(() => created.length > 0);
  proto.getBoundingClientRect = saved;
  assert.equal(created.length, 1);
  assert.equal(created[0][0], "p1");
  assert.equal(created[0][1], "pa");
  assert.ok(created[0][4] > 0 && created[0][5] > 0, "a drawable box");
  await view.cleanup();
});
