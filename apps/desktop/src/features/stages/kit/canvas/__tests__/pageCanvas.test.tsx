import { mount } from "../../../../../../../../packages/ui/src/v2/__tests__/dom"; // first: installs jsdom
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { PageCanvas, type CanvasBox } from "../PageCanvas";
import type { Box } from "../geometry";

const IMAGE = { src: "/page.png", width: 1000, height: 2000, alt: "Page 1" };

/** The overlay is drawn at (0, 0), image size times zoom. Every element reports that rectangle. */
function stubRect(zoom: number) {
  const proto = (window as any).Element.prototype;
  const saved = proto.getBoundingClientRect;
  proto.getBoundingClientRect = () => ({ left: 0, top: 0, width: (IMAGE.width * zoom) / 100, height: (IMAGE.height * zoom) / 100, right: 0, bottom: 0, x: 0, y: 0, toJSON() {} });
  return () => { proto.getBoundingClientRect = saved; };
}

const ptr = (el: Element, type: string, x: number, y: number, extra: Record<string, unknown> = {}) =>
  act(async () => { el.dispatchEvent(new (window as any).MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, ...extra })); });
const key = (el: Element, k: string, extra: Record<string, unknown> = {}) =>
  act(async () => { el.dispatchEvent(new (window as any).KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra })); });

interface Log { select: Array<[string | null, boolean]>; change: Array<[string, Box]>; commit: Array<[string, Box, Box]>; draw: Box[] }

function Harness({ initial, log, zoom = 100, editable = true, drawMode = false }: { initial: CanvasBox[]; log: Log; zoom?: number; editable?: boolean; drawMode?: boolean }) {
  const [boxes, setBoxes] = React.useState(initial);
  const [selected, setSelected] = React.useState<string | null>(null);
  return (
    <PageCanvas
      image={IMAGE}
      boxes={boxes}
      selectedId={selected}
      zoom={zoom}
      editable={editable}
      drawMode={drawMode}
      onSelect={(id, additive) => { log.select.push([id, additive]); setSelected(id); }}
      onChange={(id, box) => { log.change.push([id, box]); setBoxes((bs) => bs.map((b) => (b.id === id ? { ...b, box } : b))); }}
      onCommit={(id, box, previous) => { log.commit.push([id, box, previous]); }}
      onDraw={(box) => { log.draw.push(box); }}
    />
  );
}
const newLog = (): Log => ({ select: [], change: [], commit: [], draw: [] });
const BOXES: CanvasBox[] = [
  { id: "a", box: { x: 100, y: 100, w: 300, h: 200 }, label: "Panel 1", tone: "accent" },
  { id: "b", box: { x: 500, y: 600, w: 300, h: 200 }, label: "Panel 2", tone: "neutral", locked: true },
];
const boxEl = (d: Document, id: string) => d.querySelector(`[data-box-id="${id}"]`) as Element;
const overlay = (d: Document) => d.querySelector("[data-canvas-overlay]") as Element;
const handle = (d: Document, h: string) => d.querySelector(`[data-handle="${h}"]`) as Element;

test("pressing a box selects it, and Shift or Ctrl makes the selection additive", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} />);
  await ptr(boxEl(view.document, "a"), "pointerdown", 200, 150);
  await ptr(boxEl(view.document, "a"), "pointerup", 200, 150);
  await ptr(boxEl(view.document, "a"), "pointerdown", 200, 150, { shiftKey: true });
  await ptr(boxEl(view.document, "a"), "pointerup", 200, 150);
  assert.deepEqual(log.select, [["a", false], ["a", true]]);
  await view.cleanup(); restore();
});

test("dragging a box reports each move and commits once at the end with the box it started from", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} />);
  await ptr(boxEl(view.document, "a"), "pointerdown", 200, 150);
  await ptr(overlay(view.document), "pointermove", 230, 170);
  await ptr(overlay(view.document), "pointermove", 260, 200);
  await ptr(overlay(view.document), "pointerup", 260, 200);
  assert.deepEqual(log.change.at(-1), ["a", { x: 160, y: 150, w: 300, h: 200 }]);
  assert.equal(log.commit.length, 1);
  assert.deepEqual(log.commit[0], ["a", { x: 160, y: 150, w: 300, h: 200 }, { x: 100, y: 100, w: 300, h: 200 }]);
  await view.cleanup(); restore();
});

test("a press and release without moving commits nothing", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} />);
  await ptr(boxEl(view.document, "a"), "pointerdown", 200, 150);
  await ptr(overlay(view.document), "pointerup", 200, 150);
  assert.equal(log.commit.length, 0);
  assert.equal(log.change.length, 0);
  await view.cleanup(); restore();
});

test("Escape during a drag puts the box back and commits nothing", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} />);
  await ptr(boxEl(view.document, "a"), "pointerdown", 200, 150);
  await ptr(overlay(view.document), "pointermove", 300, 250);
  await key(view.document.body, "Escape");
  assert.deepEqual(log.change.at(-1), ["a", { x: 100, y: 100, w: 300, h: 200 }]);
  await ptr(overlay(view.document), "pointerup", 300, 250);
  assert.equal(log.commit.length, 0);
  await view.cleanup(); restore();
});

test("dragging a handle resizes the box the way resizeBox does", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} />);
  await ptr(boxEl(view.document, "a"), "pointerdown", 200, 150);
  await ptr(overlay(view.document), "pointerup", 200, 150);
  await ptr(handle(view.document, "se"), "pointerdown", 400, 300);
  await ptr(overlay(view.document), "pointermove", 450, 340);
  await ptr(overlay(view.document), "pointerup", 450, 340);
  assert.deepEqual(log.commit.at(-1), ["a", { x: 100, y: 100, w: 350, h: 240 }, { x: 100, y: 100, w: 300, h: 200 }]);
  await view.cleanup(); restore();
});

test("at 50 percent zoom the same pointer distance moves the box twice as far in the image", async () => {
  const restore = stubRect(50);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} zoom={50} />);
  await ptr(boxEl(view.document, "a"), "pointerdown", 100, 75);
  await ptr(overlay(view.document), "pointermove", 150, 75);
  await ptr(overlay(view.document), "pointerup", 150, 75);
  assert.equal(log.commit[0][1].x, 200, "50 screen pixels is 100 image pixels");
  await view.cleanup(); restore();
});

test("in draw mode a drag draws a box, but only a big enough one is reported", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={[]} log={log} drawMode />);
  await ptr(overlay(view.document), "pointerdown", 300, 400);
  await ptr(overlay(view.document), "pointermove", 500, 650);
  await ptr(overlay(view.document), "pointerup", 500, 650);
  assert.deepEqual(log.draw, [{ x: 300, y: 400, w: 200, h: 250 }]);
  await ptr(overlay(view.document), "pointerdown", 100, 100);
  await ptr(overlay(view.document), "pointermove", 110, 110);
  await ptr(overlay(view.document), "pointerup", 110, 110);
  assert.equal(log.draw.length, 1, "a ten pixel box is not drawn");
  await view.cleanup(); restore();
});

test("pressing the empty page clears the selection", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} />);
  await ptr(overlay(view.document), "pointerdown", 900, 1500);
  await ptr(overlay(view.document), "pointerup", 900, 1500);
  assert.deepEqual(log.select, [[null, false]]);
  await view.cleanup(); restore();
});

test("arrow keys move the focused box by 10 pixels (1 with Alt) and Shift resizes it, each press committing once", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} />);
  const a = () => boxEl(view.document, "a");
  await key(a(), "ArrowRight");
  await key(a(), "ArrowDown", { altKey: true });
  await key(a(), "ArrowRight", { shiftKey: true });
  assert.equal(log.commit.length, 3);
  assert.deepEqual(log.commit[0], ["a", { x: 110, y: 100, w: 300, h: 200 }, { x: 100, y: 100, w: 300, h: 200 }]);
  assert.deepEqual(log.commit[1][1], { x: 110, y: 101, w: 300, h: 200 });
  assert.deepEqual(log.commit[2][1], { x: 110, y: 101, w: 310, h: 200 });
  await view.cleanup(); restore();
});

test("when the canvas is not editable, pointers only select and keys do nothing", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} editable={false} />);
  await ptr(boxEl(view.document, "a"), "pointerdown", 200, 150);
  await ptr(overlay(view.document), "pointermove", 300, 250);
  await ptr(overlay(view.document), "pointerup", 300, 250);
  await key(boxEl(view.document, "a"), "ArrowRight");
  assert.equal(log.change.length, 0);
  assert.equal(log.commit.length, 0);
  assert.equal(handle(view.document, "se"), null, "no handles");
  assert.deepEqual(log.select, [["a", false]]);
  await view.cleanup(); restore();
});

test("a locked box can be selected but not moved, resized or nudged", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const view = await mount(<Harness initial={BOXES} log={log} />);
  await ptr(boxEl(view.document, "b"), "pointerdown", 600, 650);
  await ptr(overlay(view.document), "pointermove", 700, 750);
  await ptr(overlay(view.document), "pointerup", 700, 750);
  await key(boxEl(view.document, "b"), "ArrowRight");
  assert.deepEqual(log.select, [["b", false]]);
  assert.equal(log.change.length + log.commit.length, 0);
  await view.cleanup(); restore();
});

test("each box is exposed to assistive technology with its label, position and size", async () => {
  const restore = stubRect(100);
  const view = await mount(<Harness initial={BOXES} log={newLog()} />);
  const a = boxEl(view.document, "a");
  assert.equal(a.getAttribute("role"), "button");
  assert.equal(a.getAttribute("tabindex"), "0");
  assert.equal(a.getAttribute("aria-label"), "Panel 1, at 100, 100, 300 by 200");
  assert.ok(boxEl(view.document, "b").getAttribute("aria-label")!.includes("locked"));
  await view.cleanup(); restore();
});

test("a page image that cannot load says so and offers Retry with a cache-buster", async () => {
  const restore = stubRect(100);
  const view = await mount(<Harness initial={BOXES} log={newLog()} />);
  const img = view.document.querySelector("img")!;
  await act(async () => { img.dispatchEvent(new (window as any).Event("error")); });
  assert.ok((view.document.body.textContent ?? "").includes("Page image unavailable"));
  assert.equal(view.document.querySelector("img"), null);
  const retry = [...view.document.querySelectorAll("button")].find((b) => b.textContent === "Retry")!;
  await act(async () => { retry.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true })); });
  assert.ok(view.document.querySelector("img")!.getAttribute("src")!.includes("retry=1"));
  await view.cleanup(); restore();
});

test("boxes can be hidden", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const Hidden = () => <PageCanvas image={IMAGE} boxes={BOXES} selectedId={null} zoom={100} showBoxes={false} onSelect={() => {}} />;
  const view = await mount(<Hidden />);
  assert.equal(boxEl(view.document, "a"), null);
  await view.cleanup(); restore();
  void log;
});

test("the canvas reports the image's natural size once it loads", async () => {
  const restore = stubRect(100);
  const sizes: Array<[number, number]> = [];
  const Sized = () => <PageCanvas image={IMAGE} boxes={[]} selectedId={null} zoom={100} onSelect={() => {}} onImageSize={(w, h) => { sizes.push([w, h]); }} />;
  const view = await mount(<Sized />);
  const img = view.document.querySelector("img")!;
  Object.defineProperty(img, "naturalWidth", { configurable: true, value: 1920 });
  Object.defineProperty(img, "naturalHeight", { configurable: true, value: 22528 });
  await act(async () => { img.dispatchEvent(new (window as any).Event("load")); });
  assert.deepEqual(sizes, [[1920, 22528]]);
  await view.cleanup(); restore();
});

test("a fixed box can be selected and a new box drawn, but the fixed box is never moved, resized or nudged, and is not called locked", async () => {
  const restore = stubRect(100);
  const log = newLog();
  const fixed: CanvasBox[] = [{ id: "r", box: { x: 100, y: 100, w: 300, h: 200 }, label: "Region 1", tone: "accent", fixed: true }];
  const view = await mount(<Harness initial={fixed} log={log} />);
  await key(boxEl(view.document, "r"), "Enter");
  assert.deepEqual(log.select, [["r", false]]);
  assert.equal(view.document.querySelectorAll("[data-handle]").length, 0, "no resize handles");
  await key(boxEl(view.document, "r"), "ArrowRight");
  await ptr(boxEl(view.document, "r"), "pointerdown", 200, 150);
  await ptr(overlay(view.document), "pointermove", 260, 190);
  await ptr(overlay(view.document), "pointerup", 260, 190);
  assert.deepEqual(log.commit, [], "dragging a fixed box commits nothing");
  assert.deepEqual(log.change, []);
  assert.ok(!boxEl(view.document, "r").getAttribute("aria-label")!.includes("locked"));
  await view.cleanup();
  restore();
});
