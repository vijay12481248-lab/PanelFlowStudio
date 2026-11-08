import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup as html } from "react-dom/server";
import { Button, Chip, GlassPanel, IconButton, Progress, Skeleton, cx } from "../index";

test("cx joins truthy class parts only", () => {
  assert.equal(cx("a", false, null, undefined, "b"), "a b");
});

test("primary Button is the accent-filled style and secondary is not", () => {
  assert.ok(html(<Button variant="primary">Save changes</Button>).includes("bg-accent"));
  assert.ok(!html(<Button variant="secondary">Cancel</Button>).includes("bg-accent"));
});

test("a loading Button is busy and disabled", () => {
  const markup = html(<Button variant="primary" loading>Render</Button>);
  assert.ok(markup.includes('aria-busy="true"'));
  assert.ok(markup.includes("disabled"));
});

test("Button defaults to type=button so it never submits a form by accident", () => {
  assert.ok(html(<Button variant="ghost">More</Button>).includes('type="button"'));
});

test("IconButton exposes its label as the accessible name", () => {
  assert.ok(html(<IconButton label="Retry">x</IconButton>).includes('aria-label="Retry"'));
});

test("Chip renders its tone and text", () => {
  const markup = html(<Chip tone="ok">Ready</Chip>);
  assert.ok(markup.includes("Ready"));
  assert.ok(markup.includes("text-ok"));
});

test("Progress clamps its value to 0-100", () => {
  assert.ok(html(<Progress value={140} label="Render" />).includes('aria-valuenow="100"'));
  assert.ok(html(<Progress value={-5} label="Render" />).includes('aria-valuenow="0"'));
  assert.ok(html(<Progress value={40} label="Render" />).includes('aria-label="Render"'));
});

test("GlassPanel blurs by default and the flat variant does not", () => {
  assert.ok(html(<GlassPanel>x</GlassPanel>).includes("backdrop-blur"));
  assert.ok(!html(<GlassPanel blur={false}>x</GlassPanel>).includes("backdrop-blur"));
});

test("Skeleton is hidden from assistive technology", () => {
  assert.ok(html(<Skeleton className="h-4" />).includes('aria-hidden="true"'));
});
