import React from "react";
import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { api } from "@panelflow/api-client";
import type { Page, Panel } from "@panelflow/shared-types";
import { SourcePageBrowser } from "../SourcePageBrowser";

const pages = Array.from({ length: 11 }, (_, i) => ({
  id: `real-page-${i}`, project_id: "reference-project", sequence: i + 1,
  width: 800, height: 1200,
} as Page));
const panel = { id: "real-panel", page_id: pages[0].id, page_sequence: 1,
  x: 40, y: 80, width: 200, height: 300 } as Panel;
const props = {
  projectId: "reference-project", pages, panels: [panel],
  selectedPageId: pages[0].id, selectedPanelId: panel.id,
  onSelectPage: () => {}, onSelectPanel: () => {}, onAddPanelToScene: () => {},
};

test("compact source browser shows real scrollable four-column thumbnails, selection and reference controls, not the full canvas", () => {
  const html = renderToStaticMarkup(<SourcePageBrowser {...props} compact />);
  assert.match(html, /aria-label="Source page thumbnails"/);
  assert.match(html, /grid-cols-4/);
  assert.match(html, /overflow-y-auto/);
  assert.match(html, /aria-pressed="true"/);
  assert.match(html, /1 \/ 11/);
  for (const page of pages) assert.ok(html.includes(api.getPageImageUrl(props.projectId, page.id)));
  for (const label of ["Source Pages", "Pages", "Panels", "Select", "Rectangle", "Polygon", "Pen"]) assert.ok(html.includes(label));
  assert.match(html, /aria-label="Source zoom"/);
  assert.match(html, /aria-label="Expand source workspace"/);
  assert.doesNotMatch(html, /Manga Page|viewBox="0 0 800 1200"/);
});

// Small hook driver: exercises the component's real callbacks without adding a DOM dependency.
// SSR above verifies emitted markup; this driver does not claim browser focus/layout coverage.
function mount(overrides: Partial<React.ComponentProps<typeof SourcePageBrowser>> = {}) {
  const internals = (React as any).__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
  const slots: any[] = [];
  let cursor = 0;
  let tree: React.ReactNode;
  function render() {
    const previous = internals.ReactCurrentDispatcher.current;
    cursor = 0;
    internals.ReactCurrentDispatcher.current = {
      useState(initial: any) {
        const index = cursor++;
        if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
        return [slots[index], (next: any) => { slots[index] = typeof next === "function" ? next(slots[index]) : next; }];
      },
      useRef(initial: any) { const index = cursor++; return slots[index] ??= { current: initial }; },
      useEffect() { cursor++; },
      useCallback(callback: any) { cursor++; return callback; },
    };
    try { tree = SourcePageBrowser({ ...props, compact: true, ...overrides }); }
    finally { internals.ReactCurrentDispatcher.current = previous; }
    return tree;
  }
  function elements(node: React.ReactNode): React.ReactElement<any>[] {
    if (!React.isValidElement(node)) return [];
    const element = node as React.ReactElement<any>;
    return [element, ...React.Children.toArray(element.props.children).flatMap(elements)];
  }
  render();
  return {
    render,
    all: () => elements(tree),
    find: (predicate: (node: React.ReactElement<any>) => boolean) => {
      const result = elements(tree).find(predicate);
      assert.ok(result, "Expected control exists");
      return result;
    },
  };
}

test("drawing tool expands the same crop workspace; close and Escape preserve its crop draft", () => {
  const browser = mount();
  browser.find(e => e.type === "button" && React.Children.toArray(e.props.children).includes("Rectangle")).props.onClick();
  browser.render();
  const dialog = browser.find(e => e.type === "dialog");
  assert.equal(dialog.props["aria-label"], "Source page workspace");
  const canvas = browser.find(e => e.type === "svg" && e.props.onMouseDown);
  assert.ok(canvas.props.className.includes("cursor-crosshair"));
  const oldSvg = (globalThis as any).SVGSVGElement;
  class FakeSvg { getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 1200 }; } }
  (globalThis as any).SVGSVGElement = FakeSvg;
  try {
    const target = new FakeSvg();
    canvas.props.onMouseDown({ currentTarget: target, clientX: 10, clientY: 20 });
    browser.render();
    browser.find(e => e.type === "svg" && e.props.onMouseMove).props.onMouseMove({ currentTarget: target, clientX: 210, clientY: 320 });
    browser.render();
    browser.find(e => e.type === "svg" && e.props.onMouseUp).props.onMouseUp();
    browser.render();
    browser.find(e => e.props["aria-label"] === "Close source workspace").props.onClick();
    browser.render();
    assert.equal(browser.all().some(e => e.type === "dialog"), false);
    browser.find(e => e.props["aria-label"] === "Expand source workspace").props.onClick();
    browser.render();
    assert.ok(browser.all().some(e => e.type === "rect" && e.props.x === 10 && e.props.y === 20 && e.props.width === 200 && e.props.height === 300));
    browser.find(e => e.type === "dialog").props.onCancel({ preventDefault() {} });
    browser.render();
    assert.equal(browser.all().some(e => e.type === "dialog"), false);
  } finally { (globalThis as any).SVGSVGElement = oldSvg; }
});

test("compact panel gallery preserves the exact drag payload and full-workspace add callbacks", () => {
  const added: unknown[][] = [];
  const browser = mount({ activeSubTab: "panels", onAddPanelToScene: (...args) => added.push(args) });
  const thumb = browser.find(e => e.props["aria-label"] === "Select panel 1");
  const transferred = new Map<string, string>();
  const dataTransfer = { setData: (type: string, value: string) => transferred.set(type, value), effectAllowed: "" };
  thumb.props.onDragStart({ dataTransfer });
  assert.equal(dataTransfer.effectAllowed, "copy");
  assert.deepEqual(JSON.parse(transferred.get("application/panelflow-panel")!), {
    pageId: pages[0].id, panelId: panel.id, pageSequence: 1,
    crop: { x: 40, y: 80, width: 200, height: 300 },
    imageUrl: api.getPageImageUrl(props.projectId, pages[0].id), name: "Panel #1",
  });
  browser.find(e => e.props["aria-label"] === "Expand source workspace").props.onClick();
  browser.render();
  browser.find(e => e.props.title === "Add as layer to active scene").props.onClick({ stopPropagation() {} });
  browser.find(e => e.props.title === "Add as new scene").props.onClick({ stopPropagation() {} });
  assert.deepEqual(added, [[pages[0], panel, undefined, false], [pages[0], panel, undefined, true]]);
});

test("empty compact gallery reports zero pages and does not invent source assets", () => {
  const html = renderToStaticMarkup(<SourcePageBrowser {...props} pages={[]} panels={[]} selectedPageId={null} compact />);
  assert.match(html, /0 \/ 0/);
  assert.match(html, /No pages available/);
  assert.doesNotMatch(html, /<img/);
  const browser = mount({ pages: [], panels: [], selectedPageId: null });
  assert.equal(browser.find(e => e.props["aria-label"] === "Expand source workspace").props.disabled, true);
  assert.equal(browser.find(e => e.props.title === "Next Page").props.disabled, true);
});

test("opening a selected page by double-click preserves an unfinished crop", () => {
  const browser = mount();
  browser.find(e => e.type === "button" && React.Children.toArray(e.props.children).includes("Polygon")).props.onClick();
  browser.render();
  const oldSvg = (globalThis as any).SVGSVGElement;
  class FakeSvg { getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 1200 }; } }
  (globalThis as any).SVGSVGElement = FakeSvg;
  try {
    browser.find(e => e.type === "svg" && e.props.onMouseDown).props.onMouseDown({ currentTarget: new FakeSvg(), clientX: 100, clientY: 100 });
    browser.render();
    browser.find(e => e.props["aria-label"] === "Close source workspace").props.onClick();
    browser.render();
    const thumb = browser.find(e => e.props["aria-label"] === "Select page 1");
    thumb.props.onClick();
    thumb.props.onDoubleClick();
    browser.render();
    assert.ok(browser.all().some(e => e.type === "circle" && e.props.cx === 100 && e.props.cy === 100));
  } finally { (globalThis as any).SVGSVGElement = oldSvg; }
});

for (const [label, cropType] of [["Polygon", "polygon"], ["Pen", "pen"]] as const) {
  test(`${label} opens the drawing surface and confirms the original crop payload before adding`, () => {
    const added: unknown[][] = [];
    const browser = mount({ selectedPanelId: null, onAddPanelToScene: (...args) => added.push(args) });
    browser.find(e => e.type === "button" && React.Children.toArray(e.props.children).includes(label)).props.onClick();
    browser.render();
    const oldSvg = (globalThis as any).SVGSVGElement;
    class FakeSvg { getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 1200 }; } }
    (globalThis as any).SVGSVGElement = FakeSvg;
    try {
      const points = [[100, 100], [300, 100], [300, 400]];
      for (const [index, [x, y]] of points.entries()) {
        const svg = browser.find(e => e.type === "svg" && e.props.onMouseDown);
        const event = { currentTarget: new FakeSvg(), clientX: x, clientY: y };
        if (cropType === "polygon" || index === 0) svg.props.onMouseDown(event);
        else svg.props.onMouseMove(event);
        browser.render();
      }
      browser.find(e => e.type === "svg" && e.props.onMouseUp).props.onMouseUp();
      browser.render();
      browser.find(e => e.props.title === "Add cropped region to timeline").props.onClick();
      browser.render();
      assert.deepEqual(added, [], "Drawing and prompting must never silently mutate the timeline");
      assert.ok(browser.all().some(e => e.type === "h3" && e.props.children === "Add Crop to Timeline?"));
      browser.find(e => e.type === "dialog").props.onCancel({ preventDefault() {} });
      browser.render();
      assert.ok(browser.all().some(e => e.type === "dialog"), "Escape dismisses confirmation before workspace");
      browser.find(e => e.props.title === "Add cropped region to timeline").props.onClick();
      browser.render();
      browser.find(e => React.Children.toArray(e.props.children).some(child => React.isValidElement(child) && (child.props as any).children === "+ Add as Scene & Play")).props.onClick();
      assert.equal(added.length, 1);
      assert.deepEqual(added[0], [pages[0], panel, {
        crop_type: cropType, x: 100, y: 100, width: 200, height: 300,
        polygon_points: [{ x: 100, y: 100 }, { x: 300, y: 100 }, { x: 300, y: 400 }],
        clip_path: "polygon(0% 0%, 100% 0%, 100% 100%)",
      }, true, true]);
    } finally { (globalThis as any).SVGSVGElement = oldSvg; }
  });
}

test("default source browser preserves the existing full viewer and add actions", () => {
  const html = renderToStaticMarkup(<SourcePageBrowser {...props} />);
  assert.match(html, /Manga Page 1/);
  assert.match(html, /viewBox="0 0 800 1200"/);
  assert.match(html, /Auto-Add: OFF/);
  assert.match(html, /\+ Layer/);
  assert.match(html, /\+ Scene/);
  assert.doesNotMatch(html, /Expand source workspace/);
});
