import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("desktop windows allow HTML panel and timeline drag-and-drop on Windows", () => {
  const config = JSON.parse(readFileSync(new URL("../../src-tauri/tauri.conf.json", import.meta.url), "utf8"));
  assert.ok(config.app.windows.length > 0);
  for (const window of config.app.windows) {
    // Tauri's default native drop handler replaces WebView2's HTML5 handler.
    // DOM-only interaction tests cannot catch this desktop-host regression.
    assert.equal(window.dragDropEnabled, false,
      `${window.title}: disable native interception so HTML dragover/drop reach the editor`);
  }
});
