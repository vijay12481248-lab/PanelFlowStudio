import { createRequire } from "node:module";
import type React from "react";
import { act } from "react";

// Radix checks `globalThis.document` when its module loads, so this file must be imported
// BEFORE any component. It installs one jsdom for the whole test file (each file runs in its own process).
const { JSDOM } = createRequire(import.meta.url)("jsdom");
const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/", pretendToBeVisual: true });
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (!(key in globalThis)) Object.defineProperty(globalThis, key, { configurable: true, get: () => (dom.window as any)[key] });
}
// Node ships its own Event classes; elements in jsdom only accept jsdom's.
for (const key of ["window", "document", "navigator", "Event", "CustomEvent", "UIEvent", "MouseEvent", "KeyboardEvent", "FocusEvent", "InputEvent"]) {
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: (dom.window as any)[key] });
}
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

/** Mount a React element into a fresh container in the shared jsdom. */
export async function mount(element: React.ReactElement) {
  const { createRoot } = await import("react-dom/client");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(element));
  return {
    document,
    click: (el: Element) => act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); }),
    /** Two clicks inside one act(): overlapping act() calls (Promise.all of two clicks) corrupt later tests. */
    clickTwice: (el: Element) => act(async () => {
      for (let i = 0; i < 2; i++) el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    }),
    /** A full mouse press (down, up, click): Radix tabs and menus react to mousedown, not click. */
    press: (el: Element) => act(async () => {
      for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) el.dispatchEvent(new dom.window.MouseEvent(type, { bubbles: true, button: 0 }));
    }),
    /** Dispatch a plain event such as "error" (a failed image load). */
    fire: (el: Element, type: string) => act(async () => { el.dispatchEvent(new dom.window.Event(type, { bubbles: false })); }),
    /** Type into a controlled React input. */
    setValue: (input: HTMLInputElement, value: string) => act(async () => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    }),
    async cleanup() {
      await act(async () => root.unmount());
      container.remove();
    },
  };
}
