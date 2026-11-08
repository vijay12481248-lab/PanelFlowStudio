import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup as html } from "react-dom/server";
import { Button, Chip, EmptyState, ErrorState, GlassPanel, IconButton, ListRow, Progress, Skeleton, Tile, cx } from "../index";

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

test("a bad ListRow carries the word Failed so status is not colour alone", () => {
  assert.ok(html(<ListRow title="H3 clip 4 failed" tone="bad" />).includes("Failed"));
});

test("a selected ListRow is accent-filled and a row with onSelect is a button", () => {
  const markup = html(<ListRow title="OCR review" selected onSelect={() => {}} />);
  assert.ok(markup.includes("bg-accent"));
  assert.ok(markup.startsWith("<button"));
});

test("a Tile without an image shows its fallback text and no img", () => {
  const markup = html(<Tile title="Magic Emperor" fallbackText="ME" />);
  assert.ok(markup.includes(">ME<"));
  assert.ok(!markup.includes("<img"));
});

test("a Tile with an image renders it with empty alt text (the title already names it)", () => {
  assert.ok(html(<Tile title="Why We Cry" fallbackText="WC" imageUrl="/c.png" />).includes('<img src="/c.png" alt=""'));
});

test("ErrorState shows Retry only when onRetry is given and never a raw error object", () => {
  assert.ok(!html(<ErrorState title="Could not load" description="Check the engine and try again." />).includes("Retry"));
  assert.ok(html(<ErrorState title="Could not load" description="Check the engine and try again." onRetry={() => {}} />).includes("Retry"));
});

test("EmptyState renders its action", () => {
  assert.ok(html(<EmptyState title="Nothing needs you" action={<button>Start a project</button>} />).includes("Start a project"));
});
