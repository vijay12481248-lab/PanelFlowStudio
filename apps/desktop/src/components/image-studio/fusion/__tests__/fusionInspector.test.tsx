import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { newEffect, newFusion, type FusionState } from "../effects";
import { FusionInspector } from "../FusionInspector";

const noop = () => {};
const render = (fusion: FusionState, selectedId: string | null) =>
  renderToStaticMarkup(
    <FusionInspector fusion={fusion} selectedId={selectedId} onSelect={noop} onChange={noop} canUndo={false} canRedo={false} onUndo={noop} onRedo={noop} />,
  );

test("an empty stack offers every effect and says what happens next", () => {
  const html = render(newFusion(), null);
  for (const label of ["Glow", "Vignette", "Film grain", "Blur", "Text"]) assert.ok(html.includes(`>${label}<`), label);
  assert.ok(html.includes("No effects yet"));
  assert.ok(html.includes("Select an effect to change it"));
  assert.match(html, /<button[^>]*disabled=""[^>]*aria-label="Undo effect change"|aria-label="Undo effect change"[^>]*disabled=""/);
});

test("the stack lists effects in order with switches, move and delete, and the open one shows its controls", () => {
  const glow = newEffect("glow"), text = newEffect("text");
  const html = render({ effects: [glow, text] }, text.id);
  assert.ok(html.includes("Text · TITLE") && html.includes(">Glow<"));
  for (const t of ["Delete Glow", "Move Glow down", "Move Text · TITLE up", "Switch off Glow"]) assert.ok(html.includes(`aria-label="${t}"`), t);
  assert.match(html, /aria-label="Move Glow up"[^>]*disabled=""|disabled=""[^>]*aria-label="Move Glow up"/, "the first effect cannot move up");
  for (const c of ["Size", "Colour", "Outline", "Glow colour"]) assert.ok(html.includes(c), c);
  assert.ok(html.includes("Click or drag on the picture to place the text"));
});

test("each effect shows only its own controls", () => {
  const vig = newEffect("vignette");
  const html = render({ effects: [vig] }, vig.id);
  for (const c of ["Radius", "Softness", "Opacity", "Colour"]) assert.ok(html.includes(c), c);
  assert.ok(!html.includes("Outline"));
  const grain = newEffect("grain");
  const g = render({ effects: [grain] }, grain.id);
  assert.ok(g.includes("New grain pattern") && g.includes("Amount"));
});

test("an effect that would change nothing says so", () => {
  const blur = { ...newEffect("blur"), params: { radius: 0 } };
  assert.ok(render({ effects: [blur] }, blur.id).includes("(no effect)"));
});
