import test from "node:test";
import assert from "node:assert/strict";
import { PanelFlowApiClient } from "./index";

async function call<T>(reply: unknown, run: (c: PanelFlowApiClient) => Promise<T>) {
  const original = globalThis.fetch;
  const calls: { url: string; method?: string; body: any }[] = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), method: options?.method, body: options?.body ? JSON.parse(String(options.body)) : null });
    return new Response(JSON.stringify(reply));
  };
  try {
    return { result: await run(new PanelFlowApiClient("http://127.0.0.1:8765", "t")), calls };
  } finally { globalThis.fetch = original; }
}

test("review queue and run list are plain GETs", async () => {
  const item = { project_id: "p", project_title: "T", run_id: "20260101T000000-abcdef", reasons: ["r"], line_ids: ["L1"], created: "now" };
  const q = await call([item], (c) => c.listNarrationReview());
  assert.match(q.calls[0].url, /\/api\/narration\/review$/);
  assert.equal(q.calls[0].method ?? "GET", "GET");
  assert.deepEqual(q.result, [item]);
  const run = { run_id: "r", gate: "review", created: "now", steps: [{ step: "write", status: "ok", seconds: 1, model_calls: 2 }] };
  const l = await call([run], (c) => c.listNarrationRuns("p 1"));
  assert.match(l.calls[0].url, /\/api\/narration\/runs\/p%201$/);
  assert.equal(l.result[0].steps[0].model_calls, 2);
});

test("run inspector parses the typed payload", async () => {
  const payload = {
    run: { run_id: "r" },
    lines: [{ line_id: "L1", panel_id: "x", text: "t", status: "passed", kind: "beat", facts: "P1 | chars: -",
      speaker_id: "narrator", speaker_name: "Narrator", outdated: false,
      checks: [{ rule: "order", passed: true, severity: "block", reason: "" }],
      take: { wer: 0.1, flagged: false, stt_text: "t", voice_profile_id: "narrator",
              script_revision: 3, direction_revision: 3, provider: "kokoro-82m" } }],
    beat_sheet: { hook: "h", chapter_summary: "s", scenes: [{ scene_id: "S1", goal: "g", first_panel_id: "a", last_panel_id: "b" }] },
    casting: null,
    review: null,
  };
  const { result, calls } = await call(payload, (c) => c.getNarrationRun("p", "20260101T000000-abcdef"));
  assert.match(calls[0].url, /\/api\/narration\/runs\/p\/20260101T000000-abcdef$/);
  assert.equal(result.lines[0].take?.wer, 0.1);
  assert.equal(result.beat_sheet?.scenes[0].scene_id, "S1");
});

test("line actions and approve POST the right bodies", async () => {
  const edit = await call({ line_id: "L1", panel_id: "x", text: "new", status: "passed", kind: "beat", checks: [], facts: "P1 | chars: -", take: null, speaker_id: "narrator", speaker_name: "Narrator", outdated: false }, (c) => c.narrationLineAction("p", "r1", "L1", { action: "edit", text: "new" }));
  assert.deepEqual(Object.keys(edit.result as object).sort(), ["checks", "facts", "kind", "line_id", "outdated", "panel_id", "speaker_id", "speaker_name", "status", "take", "text"]);
  assert.match(edit.calls[0].url, /\/api\/narration\/runs\/p\/r1\/lines\/L1$/);
  assert.equal(edit.calls[0].method, "POST");
  assert.deepEqual(edit.calls[0].body, { action: "edit", text: "new" });
  const regen = await call({ job_id: "j" }, (c) => c.narrationLineAction("p", "r1", "L1", { action: "regenerate", hint: "shorter" }));
  assert.deepEqual(regen.calls[0].body, { action: "regenerate", hint: "shorter" });
  assert.deepEqual(regen.result, { job_id: "j" });
  const ap = await call({ bible_version: 3, job_id: null }, (c) => c.approveNarrationRun("p", "r1"));
  assert.match(ap.calls[0].url, /\/api\/narration\/runs\/p\/r1\/approve$/);
  assert.equal(ap.calls[0].method, "POST");
  assert.deepEqual(ap.result, { bible_version: 3, job_id: null });
});

test("the cast is read, cast and accepted through the project endpoints", async () => {
  const cast = {
    series_key: "s",
    catalog: [{ id: "narrator", name: "The Narrator", voice: "am_michael", gender: "male", engine: "" }],
    assigned: { c1: "aria" },
    cast: [{ character_id: "narrator", profile_id: "narrator", source: "narrator" }],
    recommendations: [{ character_id: "c2", profile_id: "aria", source: "recommended" }],
    uncast: ["c3"],
  };
  const got = await call(cast, (c) => c.getNarrationCast("p 1"));
  assert.match(got.calls[0].url, /\/api\/narration\/projects\/p%201\/cast$/);
  assert.equal(got.calls[0].method ?? "GET", "GET");
  assert.equal(got.result.assigned.c1, "aria");
  assert.deepEqual(got.result.uncast, ["c3"]);

  const set = await call({ series_key: "s", assigned: { c1: "aria" } },
    (c) => c.setNarrationCast("p", "c1", "aria"));
  assert.equal(set.calls[0].method, "POST");
  assert.deepEqual(set.calls[0].body, { character_id: "c1", profile_id: "aria" });

  const accept = await call({ series_key: "s", assigned: { c1: "aria", c2: "aria" } },
    (c) => c.acceptNarrationCast("p"));
  assert.match(accept.calls[0].url, /\/api\/narration\/projects\/p\/cast\/accept$/);
  assert.equal(accept.calls[0].method, "POST");
  assert.equal(accept.result.assigned.c2, "aria");
});
