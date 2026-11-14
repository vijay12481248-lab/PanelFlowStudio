import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AiInspector, type AiInspectorProps } from "../AiInspector";
import { PageRail } from "../PageRail";
import { VersionsStrip } from "../VersionsStrip";

const noop = () => {};
const inspector = (over: Partial<AiInspectorProps>): AiInspectorProps => ({
  mode: "edit", onMode: noop, isProject: true, busy: false, progress: 0, statusText: "", error: null,
  prompt: "", onPrompt: noop, seed: 1, onSeed: noop, onEdit: noop,
  pose: { imageData: null, fileName: "", note: "", onNote: noop, onFile: noop, onSubmit: noop },
  inpaint: {
    tool: "brush", onTool: noop, brushSize: 40, onBrushSize: noop, brushOpacity: 0.85, onBrushOpacity: noop,
    maskColors: [{ id: "a", label: "Rose", hex: "#f2667a" }], maskColorIndex: 0, onMaskColor: noop,
    presets: [{ label: "Clean up", prompt: "clean" }], negativePrompt: "", onNegativePrompt: noop, hasMask: false, onSubmit: noop,
  },
  ...over,
});

test("the page rail shows every page but only AI and Deliver can be opened", () => {
  const html = renderToStaticMarkup(<PageRail page="ai" onPage={noop} />);
  for (const name of ["AI", "Cut", "Fusion", "Color", "Deliver"]) assert.ok(html.includes(`<span>${name}</span>`), name);
  assert.equal((html.match(/disabled=""/g) || []).length, 3, "Cut, Fusion and Color are disabled");
  assert.ok(html.includes('aria-current="page"'));
});

test("story panels can only be inpainted: Edit and Pose are locked", () => {
  const html = renderToStaticMarkup(<AiInspector {...inspector({ isProject: false, mode: "inpaint" })} />);
  assert.equal((html.match(/title="Needs a project picture"/g) || []).length, 2);
  assert.ok(html.includes("qwen_image_21_inpaint"));
});

test("the pose mode needs a picture before it can run, and names the workflow", () => {
  const empty = renderToStaticMarkup(<AiInspector {...inspector({ mode: "pose" })} />);
  assert.ok(empty.includes("Transfer pose &amp; camera") && empty.includes("minimax_h3_image_edit"));
  assert.match(empty, /<button[^>]*disabled=""[^>]*>[^]*Transfer pose/);
  const ready = renderToStaticMarkup(
    <AiInspector {...inspector({ mode: "pose", pose: { imageData: "data:image/png;base64,AA", fileName: "p.png", note: "", onNote: noop, onFile: noop, onSubmit: noop } })} />,
  );
  assert.ok(ready.includes("p.png"));
  assert.doesNotMatch(ready, /<button[^>]*disabled=""[^>]*><svg[^>]*><\/svg><span>Transfer pose/);
});

test("the inpaint button asks for a mask first", () => {
  const html = renderToStaticMarkup(<AiInspector {...inspector({ mode: "inpaint", prompt: "sparks" })} />);
  assert.ok(html.includes("Paint a mask to inpaint"));
});

test("the versions strip marks the open version and shows work in progress", () => {
  const html = renderToStaticMarkup(
    <VersionsStrip versions={[{ key: "a", label: "Original", src: "a.jpg" }, { key: "b", label: "v1 · Pose", src: "b.jpg" }]} activeKey="b" onSelect={noop} busy />,
  );
  assert.ok(html.includes("v1 · Pose") && html.includes("Working…"));
  assert.equal((html.match(/border-accent/g) || []).length, 1, "only the open version is highlighted");
});
