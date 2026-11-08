import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { button, panel, region, show, stub, text, until } from "./ocrFixtures";

const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const stripIds = (d: Document) => [...d.querySelectorAll("[data-strip-panel]")].map((e) => e.getAttribute("data-strip-panel"));
const boxIds = (d: Document) => [...d.querySelectorAll("[data-box-id]")].map((e) => e.getAttribute("data-box-id"));
const key = (el: Element | Window, k: string, extra: Record<string, unknown> = {}) => act(async () => { (el as any).dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra })); });
const input = (d: Document, label: string) => d.querySelector(`input[aria-label="${label}"]`) as HTMLInputElement;
const setText = (el: HTMLInputElement, value: string) => act(async () => {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new window.Event("input", { bubbles: true }));
});

// Panels pa (2 regions, one with text), pb (1 confirmed), pc (none).
const PANELS = [panel("pa", 1), panel("pb", 2), panel("pc", 3)];
const REGIONS = [region("r1", "pa", 1, { raw_text: "Hello" }), region("r2", "pa", 2), region("r3", "pb", 1, { status: "CONFIRMED", raw_text: "Done" })];

test("the strip shows every panel with filter pills and counts, and a filter narrows it", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await until(() => stripIds(view.document).length === 3);
  assert.deepEqual(stripIds(view.document), ["pa", "pb", "pc"]);
  assert.ok(button(view.document, /^All\s*3$/));
  assert.ok(button(view.document, /^Needs review\s*1$/), "pa has a region that needs review (r2); r1 also, so one panel");
  assert.ok(button(view.document, /^Has text\s*2$/));
  assert.ok(button(view.document, /^No text\s*1$/));
  await view.click(button(view.document, /^No text/)!);
  assert.deepEqual(stripIds(view.document), ["pc"]);
  await view.click(button(view.document, /^Needs review/)!);
  assert.deepEqual(stripIds(view.document), ["pa"]);
  await view.cleanup();
});

test("a strip of 625 panels draws at most 60 thumbnails, keeps the selected one, and Show more adds 60", async () => {
  const many = Array.from({ length: 625 }, (_, i) => panel(`p${i + 1}`, i + 1));
  stub({ panels: many, regions: [] });
  const view = await show();
  await until(() => stripIds(view.document).length > 0);
  assert.equal(stripIds(view.document).length, 60);
  await view.click(button(view.document, "Show more panels")!);
  assert.equal(stripIds(view.document).length, 120);
  // Jumping to panel 500 selects it and keeps it in the window even though it is beyond the limit.
  await setText(input(view.document, "Jump to panel"), "500");
  await view.click(button(view.document, "Go")!);
  await view.settle();
  assert.ok(stripIds(view.document).includes("p500"));
  assert.ok(stripIds(view.document).length <= 121);
  assert.equal(input(view.document, "Jump to panel").value, "", "the jump box clears");
  await view.cleanup();
});

test("jumping to a panel number that does not exist says so and changes nothing", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await setText(input(view.document, "Jump to panel"), "99");
  await view.click(button(view.document, "Go")!);
  assert.ok(text(view.document).includes("There is no panel 99."));
  await view.cleanup();
});

test("deleting a panel asks first, Cancel deletes nothing, and confirming deletes once", async () => {
  const calls = stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await until(() => Boolean(button(view.document, "Delete panel 3")));
  await view.click(button(view.document, "Delete panel 3")!);
  await until(() => Boolean(dialogButton(view.document, "Cancel")));
  assert.ok(text(view.document).includes("Delete panel 3?"));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(calls.deletePanel.length, 0);
  await view.click(button(view.document, "Delete panel 3")!);
  await until(() => Boolean(dialogButton(view.document, "Delete panel")));
  await view.clickTwice(dialogButton(view.document, "Delete panel")!);
  await until(() => calls.deletePanel.length > 0);
  assert.deepEqual(calls.deletePanel, [["p1", "pc"]]);
  assert.equal(calls.deletePanel.length, 1);
  await view.cleanup();
});

test("the canvas draws the active panel's regions, and selecting a region from the list or a box highlights it", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await until(() => boxIds(view.document).length === 2);
  assert.deepEqual(boxIds(view.document), ["r1", "r2"], "the first panel's regions");
  const box = view.document.querySelector('[data-box-id="r1"]')!;
  assert.match(box.getAttribute("aria-label")!, /^Region 1.*, at 100, 100, 400 by 80$/);
  await key(box, "Enter");
  await view.settle();
  assert.equal(view.document.querySelector('[data-list-region="r1"]')?.getAttribute("aria-current"), "true");
  await view.click(button(view.document, "Select region 2")!);
  assert.equal(view.document.querySelector('[data-list-region="r2"]')?.getAttribute("aria-current"), "true");
  assert.equal(view.document.querySelector('[data-list-region="r1"]')?.getAttribute("aria-current"), null);
  await view.cleanup();
});

test("the list shows each region's status and a one-line preview of its text, or says it has none", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await until(() => Boolean(view.document.querySelector('[data-list-region="r1"]')));
  const first = view.document.querySelector('[data-list-region="r1"]')!.textContent!;
  assert.ok(first.includes("Needs review") && first.includes("Hello"));
  assert.ok(view.document.querySelector('[data-list-region="r2"]')!.textContent!.includes("No text yet"));
  await view.cleanup();
});

test("zoom buttons and ctrl+wheel stay between 25 and 300 percent, and Fit returns to the fitted size", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  const percent = () => Number(/(\d+)%/.exec(view.document.querySelector("[data-zoom-label]")!.textContent!)![1]);
  for (let i = 0; i < 20; i++) await view.click(button(view.document, "Zoom out")!);
  assert.equal(percent(), 25);
  for (let i = 0; i < 40; i++) await view.click(button(view.document, "Zoom in")!);
  assert.equal(percent(), 300);
  const area = view.document.querySelector("[data-region-canvas]")!;
  for (let i = 0; i < 40; i++) await act(async () => { area.dispatchEvent(new (window as any).WheelEvent("wheel", { deltaY: 100, ctrlKey: true, bubbles: true, cancelable: true })); });
  assert.equal(percent(), 25);
  for (let i = 0; i < 5; i++) await act(async () => { area.dispatchEvent(new (window as any).WheelEvent("wheel", { deltaY: -100, bubbles: true, cancelable: true })); });
  assert.equal(percent(), 25, "a plain wheel scrolls and does not zoom");
  await view.click(button(view.document, "Fit")!);
  assert.ok(percent() >= 25 && percent() <= 300);
  await view.cleanup();
});

test("[ and ] move between the panel's regions and wrap; Escape clears; Tab is left alone", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await until(() => boxIds(view.document).length === 2);
  const current = () => view.document.querySelector('[data-list-region][aria-current="true"]')?.getAttribute("data-list-region") ?? null;
  await key(window, "]");
  assert.equal(current(), "r1");
  await key(window, "]");
  assert.equal(current(), "r2");
  await key(window, "]");
  assert.equal(current(), "r1", "wraps");
  await key(window, "[");
  assert.equal(current(), "r2", "wraps backwards");
  const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
  await act(async () => { window.dispatchEvent(tab); });
  assert.equal(tab.defaultPrevented, false, "Tab is not taken over");
  assert.equal(current(), "r2");
  await key(window, "Escape");
  assert.equal(current(), null);
  await view.cleanup();
});

test("ArrowLeft and ArrowRight move between panels and stop at the ends; the buttons do the same", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await until(() => boxIds(view.document).length === 2);
  const active = () => view.document.querySelector('[data-strip-panel][aria-current="true"]')?.getAttribute("data-strip-panel");
  assert.equal(active(), "pa");
  assert.equal(button(view.document, "Previous panel")!.disabled, true);
  await key(window, "ArrowLeft");
  assert.equal(active(), "pa", "stops at the first");
  await key(window, "ArrowRight");
  assert.equal(active(), "pb");
  await view.click(button(view.document, "Next panel")!);
  assert.equal(active(), "pc");
  assert.equal(button(view.document, "Next panel")!.disabled, true);
  await key(window, "ArrowRight");
  assert.equal(active(), "pc", "stops at the last");
  await view.click(button(view.document, "Previous panel")!);
  assert.equal(active(), "pb");
  await view.cleanup();
});

test("Jump to next flagged selects the next region that needs review, in its panel", async () => {
  stub({ panels: PANELS, regions: [region("a", "pa", 1, { status: "CONFIRMED", raw_text: "x" }), region("b", "pb", 1), region("c", "pc", 1)] });
  const view = await show();
  await until(() => Boolean(button(view.document, "Jump to next flagged")));
  await view.click(button(view.document, "Jump to next flagged")!);
  const active = () => view.document.querySelector('[data-strip-panel][aria-current="true"]')?.getAttribute("data-strip-panel");
  assert.equal(active(), "pb");
  assert.equal(view.document.querySelector('[data-list-region][aria-current="true"]')?.getAttribute("data-list-region"), "b");
  await view.click(button(view.document, "Jump to next flagged")!);
  assert.equal(view.document.querySelector('[data-list-region][aria-current="true"]')?.getAttribute("data-list-region"), "c");
  await view.cleanup();
});

test("a panel crop that cannot load says the panel image is unavailable", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await until(() => Boolean(view.document.querySelector("[data-region-canvas] img")));
  await view.fire(view.document.querySelector("[data-region-canvas] img")!, "error");
  assert.ok(text(view.document).includes("Panel image unavailable"));
  await view.cleanup();
});

test("shortcuts are ignored while typing in a field", async () => {
  stub({ panels: PANELS, regions: REGIONS });
  const view = await show();
  await until(() => boxIds(view.document).length === 2);
  const jump = input(view.document, "Jump to panel");
  await key(jump, "]");
  assert.equal(view.document.querySelector('[data-list-region][aria-current="true"]'), null);
  await key(jump, "ArrowRight");
  assert.equal(view.document.querySelector('[data-strip-panel][aria-current="true"]')?.getAttribute("data-strip-panel"), "pa");
  await view.cleanup();
});
