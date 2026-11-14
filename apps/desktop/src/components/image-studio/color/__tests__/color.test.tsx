import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ColorInspector } from "../ColorInspector";
import { G, cloneGrade, gradeSignature, isNeutral } from "../grade";
import { COALESCE_MS, pushGrade, redoGrade, startHistory, undoGrade } from "../history";
import { LOOKS } from "../looks";
import { lutId } from "../lutLibrary";
import { autoBalanceCdl } from "../stats";

const px = (r: number, g: number, b: number, n = 1) => {
  const data = new Uint8ClampedArray(n * 4);
  for (let i = 0; i < n; i++) data.set([r, g, b, 255], i * 4);
  return data;
};

test("ChronoFlow's grade maths is loaded unchanged and a new grade changes nothing", () => {
  const g = G.newGrade();
  assert.equal(G.LUT_SIZE, 33);
  assert.equal(isNeutral(g), true);
  assert.equal(G.activeNodes(g).length, 0);
});

test("warming a node pushes mid grey towards red, and the baked table does it to pixels", () => {
  const g = G.newGrade();
  g.nodes[0].temp = 60;
  assert.equal(isNeutral(g), false);
  const table = G.bake(g, G.LUT_SIZE);
  const out = G.applyToPixels(px(128, 128, 128), table, G.LUT_SIZE);
  assert.ok(out[0] > out[2] + 20, `red ${out[0]} should be well above blue ${out[2]}`);
});

test("a look adds a tunable node and the signature tells two grades apart", () => {
  const g = G.newGrade();
  const before = gradeSignature(g);
  const n = G.newNode("Noir");
  LOOKS.Noir(n);
  g.nodes.push(n);
  assert.notEqual(gradeSignature(g), before);
  const out = G.applyToPixels(px(200, 60, 60), G.bake(g, G.LUT_SIZE), G.LUT_SIZE);
  assert.ok(Math.abs(out[0] - out[1]) < 8 && Math.abs(out[1] - out[2]) < 8, "Noir removes the colour");
});

test("undo steps back one edit, and a drag of the same slider is one step", () => {
  let h = startHistory(G.newGrade());
  const withContrast = (v: number) => { const g = cloneGrade(h.present); g.nodes[0].contrast = v; return g; };
  h = pushGrade(h, withContrast(1.1), "s:contrast", 1000);
  h = pushGrade(h, withContrast(1.2), "s:contrast", 1000 + COALESCE_MS - 1); // same drag
  h = pushGrade(h, withContrast(1.5), "s:contrast", 1000 + COALESCE_MS * 3); // a new gesture
  assert.equal(h.past.length, 2);
  h = undoGrade(h);
  assert.equal(h.present.nodes[0].contrast, 1.2);
  h = undoGrade(h);
  assert.equal(h.present.nodes[0].contrast, 1);
  assert.equal(undoGrade(h), h, "nothing left to undo");
  h = redoGrade(h);
  assert.equal(h.present.nodes[0].contrast, 1.2);
  h = pushGrade(h, withContrast(0.5), "", 9e9);
  assert.equal(h.future.length, 0, "a new edit clears redo");
});

test("auto balance pulls a blue cast back: red gains more than blue", () => {
  const n = 400;
  const data = new Uint8ClampedArray(n * 4);
  for (let i = 0; i < n; i++) { const v = 40 + (i % 200); data.set([v * 0.7, v * 0.9, Math.min(255, v * 1.2), 255], i * 4); }
  const { cdl } = autoBalanceCdl({ data, width: 20, height: 20 });
  assert.ok(cdl.slope[0] > cdl.slope[2], `red ${cdl.slope[0]} vs blue ${cdl.slope[2]}`);
});

test("importing the same LUT twice gives it one id", () => {
  const t = new Float32Array(27 * 3).map((_, i) => (i % 9) / 9);
  assert.equal(lutId(t), lutId(new Float32Array(t)));
  assert.notEqual(lutId(t), lutId(t.map((x) => 1 - x)));
});

test("parseCube reads a 2-point 3D LUT and refuses a file that is not a .cube", () => {
  const cube = ["LUT_3D_SIZE 2", "0 0 0", "1 0 0", "0 1 0", "1 1 0", "0 0 1", "1 0 1", "0 1 1", "1 1 1"].join("\n");
  const lut = G.parseCube(cube);
  assert.equal(lut.size, 2);
  assert.equal(lut.table.length, 24);
  assert.throws(() => G.parseCube("hello"), /Not a \.cube file/);
});

test("the colour inspector shows the node strip, the tools and the primaries", () => {
  const html = renderToStaticMarkup(
    <ColorInspector
      grade={G.newGrade()} nodeIndex={0} onNodeIndex={() => {}} onChange={() => {}} canUndo={false} canRedo={false}
      onUndo={() => {}} onRedo={() => {}} lib={{}} onLib={() => {}} bypass={false} onBypass={() => {}}
      probe={null} sourceError={null} table={null} onToast={() => {}}
    />,
  );
  for (const label of ["Primaries", "Curves", "Hue / Sat", "LUT &amp; Looks", "Scopes", "Auto balance", "Lift", "Gamma", "Gain", "Offset", "Contrast", "Saturation", "Highlights"]) {
    assert.ok(html.includes(label), label);
  }
  assert.ok(html.includes('aria-label="Delete this node"') && /<button[^>]*disabled=""[^>]*aria-label="Delete this node"|aria-label="Delete this node"[^>]*disabled=""/.test(html), "the only node cannot be deleted");
});
