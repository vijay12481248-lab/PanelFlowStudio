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
