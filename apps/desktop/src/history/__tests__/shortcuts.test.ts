import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { historyShortcut } from "../shortcuts";
const { JSDOM } = createRequire(import.meta.url)("jsdom");

test("undo/redo routing preserves native text edits and respects handled/composing events", () => {
  const dom = new JSDOM('<input><textarea></textarea><div contenteditable="true"><span id="text"></span></div><button></button>');
  try {
    const event = { key: "z", ctrlKey: true, metaKey: false, shiftKey: false, altKey: false, target: dom.window.document.querySelector("button") };
    assert.equal(historyShortcut(event), "undo");
    assert.equal(historyShortcut({ ...event, shiftKey: true }), "redo");
    assert.equal(historyShortcut({ ...event, key: "y" }), "redo");
    assert.equal(historyShortcut({ ...event, ctrlKey: false, metaKey: true }), "undo");
    for (const selector of ["input", "textarea", "#text"]) assert.equal(historyShortcut({ ...event, target: dom.window.document.querySelector(selector) }), null);
    for (const overrides of [{ defaultPrevented: true }, { isComposing: true }, { altKey: true }, { ctrlKey: false }]) assert.equal(historyShortcut({ ...event, ...overrides }), null);
    assert.equal(historyShortcut({ ...event, composedPath: () => [dom.window.document.querySelector("input"), event.target] }), null);
  } finally { dom.window.close(); }
});
