import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { NarrationLine, NarrationReviewItem, NarrationRunDetail, NarrationRunSummary } from "@panelflow/shared-types";
import { NarrationReviewQueue } from "../NarrationReviewQueue";
import { NarrationRunInspector } from "../NarrationRunInspector";

const noop = () => {};
const line = (over: Partial<NarrationLine> = {}): NarrationLine => ({
  line_id: "L1", panel_id: "P1", text: "He draws his sword.", status: "needs_review", kind: "narration",
  checks: [{ rule: "banned_phrase", passed: false, severity: "block", reason: "uses banned phrase 'suddenly'" }],
  facts: "action: draws sword; characters: Lin", take: null, ...over,
});
const detail = (lines: NarrationLine[]): NarrationRunDetail => ({ run: {}, lines, beat_sheet: null, review: null });
const items: NarrationReviewItem[] = [
  { project_id: "p1", project_title: "Manga One", run_id: "20261031T101010-abc123", reasons: ["2 lines failed critique"], line_ids: ["L1"], created: "2026-10-31" },
];
const queue = (run: NarrationRunDetail | null, extra: Record<string, unknown> = {}) =>
  renderToStaticMarkup(
    <NarrationReviewQueue
      items={items} selected={run ? { projectId: "p1", runId: items[0].run_id } : null} run={run}
      imageUrl={(p, q) => `/img/${p}/${q}`}
      audioUrl={(p, r, l) => `/audio/${p}/${r}/${l}`}
      onSelectRun={noop} onLineAction={noop} onApprove={noop} errors={{}} busy={{}} {...extra}
    />,
  );

test("review queue lists reasons and failing checks", () => {
  const html = queue(detail([line()]));
  assert.match(html, /Manga One/);
  assert.match(html, /2 lines failed critique/);
  assert.match(html, /banned phrase/);
  assert.match(html, /block/);
  assert.match(html, /draws sword/);
  assert.match(html, /\/img\/p1\/P1/);
});

test("approve disabled while a line is blocked", () => {
  const btn = (h: string) => h.match(/<button[^>]*aria-label="Approve chapter"[^>]*>/)![0];
  assert.match(btn(queue(detail([line()]))), /disabled=""/);
  assert.doesNotMatch(btn(queue(detail([line({ status: "passed", checks: [] })]))), /disabled=""/);
});

test("edit error shows server reasons", () => {
  const html = queue(detail([line()]), { errors: { L1: ["contains banned phrase 'suddenly'"] } });
  assert.match(html, /role="alert"/);
  assert.match(html, /contains banned phrase &#x27;suddenly&#x27;/);
  assert.match(html, /aria-label="Edit text for L1"[^>]*>He draws his sword\./);
});

test("inspector renders steps and lines", () => {
  const runs: NarrationRunSummary[] = [
    { run_id: "R1", gate: "review", created: "2026-10-31", steps: [{ step: "draft", status: "ok", seconds: 3.5, model_calls: 4 }] },
  ];
  const html = renderToStaticMarkup(
    <NarrationRunInspector
      projects={[{ id: "p1", title: "Manga One" }]} projectId="p1" runs={runs} runId="R1"
      run={detail([line({ take: { wer: 0.25, flagged: true, stt_text: "he draws his sord" } })])}
      onSelectProject={noop} onSelectRun={noop}
    />,
  );
  assert.match(html, /draft/);
  assert.match(html, /3\.5/);
  assert.match(html, /He draws his sword\./);
  assert.match(html, /needs_review/);
});

test("approve error is shown under the button and line errors survive", () => {
  const html = queue(detail([line()]), { errors: { approve: ["lines still need review: L1"], L1: ["still bad"] } });
  assert.match(html, /aria-label="Approve errors"[^>]*>.*lines still need review: L1/);
  assert.match(html, /still bad/);
});

test("load error is rendered in the tab", () => {
  assert.match(queue(null, { loadError: "Could not load the review queue: boom" }), /Could not load the review queue: boom/);
});

test("a flagged passed line is listed with its audio and approve stays enabled", () => {
  const flagged = line({ status: "passed", checks: [], take: { wer: 0.5, flagged: true, stt_text: "heard it wrong" } });
  const html = queue(detail([flagged, line({ line_id: "L2", status: "passed", checks: [] })]));
  assert.match(html, /<audio controls[^>]*src="\/audio\/p1\/20261031T101010-abc123\/L1"/);
  assert.doesNotMatch(html, /Edit text for L2/);
  assert.match(html, /heard it wrong/);
  assert.doesNotMatch(html.match(/<button[^>]*aria-label="Approve chapter"[^>]*>/)![0], /disabled=""/);
  const listed = queue({ ...detail([line({ status: "passed", checks: [] })]), review: { run_id: "r", project_id: "p1", series_key: "s", run_dir: "x", reasons: [], line_ids: ["L1"], status: "pending" } });
  assert.match(listed, /Edit text for L1/);
});

test("new line text replaces a stale draft", async () => {
  const { JSDOM } = await import("jsdom");
  const { createRoot } = await import("react-dom/client");
  const { act } = React as any;
  const dom = new JSDOM("<div id=root></div>");
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true, window: dom.window, document: dom.window.document });
  const root = createRoot(dom.window.document.getElementById("root")!);
  const el = (text: string) => (
    <NarrationReviewQueue
      items={items} selected={{ projectId: "p1", runId: items[0].run_id }} run={detail([line({ text })])}
      imageUrl={() => "/i"} audioUrl={() => "/a"} onSelectRun={noop} onLineAction={noop} onApprove={noop} errors={{}} busy={{}}
    />
  );
  await act(async () => { root.render(el("first text")); });
  const area = () => dom.window.document.querySelector("textarea")!.value;
  assert.equal(area(), "first text");
  await act(async () => { root.render(el("regenerated text")); });
  assert.equal(area(), "regenerated text");
  await act(async () => { root.unmount(); });
  delete (globalThis as any).window;
  delete (globalThis as any).document;
});