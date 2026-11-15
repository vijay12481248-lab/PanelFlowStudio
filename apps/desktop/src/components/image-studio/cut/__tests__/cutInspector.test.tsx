import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CutInspector } from "../CutInspector";
import { newCut } from "../geometry";

const render = (cut = newCut()) =>
  renderToStaticMarkup(
    <CutInspector cut={cut} sourceWidth={1792} sourceHeight={2368} onChange={() => {}} canUndo={false} canRedo={false} onUndo={() => {}} onRedo={() => {}} />,
  );

test("the cut inspector offers the aspects, straighten, turns, flips and the output size", () => {
  const html = render();
  for (const label of ["Free", "Original", "1:1", "4:5", "3:4", "4:3", "16:9", "9:16", "Straighten", "Keep", "2048", "1080"]) assert.ok(html.includes(label), label);
  for (const title of ["Turn left", "Turn right", "Flip horizontally", "Flip vertically", "Undo cut change", "Redo cut change"]) assert.ok(html.includes(`aria-label="${title}"`), title);
  assert.ok(html.includes("1792 × 2368 px"), "an untouched cut keeps the picture's size");
  assert.match(html, /<button[^>]*disabled=""[^>]*>Reset<\/button>/, "Reset is off while nothing is cut");
});

test("the readout shows the size the cut will produce", () => {
  const html = render({ ...newCut(), aspect: "free", crop: { x: 0, y: 0, w: 0.5, h: 0.5 }, longEdge: 512 });
  assert.match(html, /38[78] × 512 px/); // half of 1792 × 2368, scaled so the long edge is 512
  assert.doesNotMatch(html, /<button[^>]*disabled=""[^>]*>Reset<\/button>/, "Reset is on once something is cut");
});
