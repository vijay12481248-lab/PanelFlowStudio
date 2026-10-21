import test from "node:test";
import assert from "node:assert/strict";
import { PanelFlowApiClient } from "./index";

const saved = {
  project_id: "project", scenes: [{ id: "scene", duration_sec: 7, layers: [
    { id: "old", source_page_id: "page-old", image_url: "http://127.0.0.1:8765/api/projects/project/pages/page-old/file;pf-token=previous-session", transform: { scale: 1.4 }, motion_preset: "pan_right" },
    { id: "relative", source_page_id: "page-relative", image_url: "/api/projects/project/pages/page-relative/file" },
    { id: "unsigned", source_page_id: "page-unsigned", image_url: "http://localhost:8765/api/projects/project/pages/page-unsigned/file" },
  ] }], narration_clips: [{ id: "voice", start_time_sec: 2 }],
};

test("loading saved layers replaces expired, relative and unsigned URLs with this session's authenticated URLs", async () => {
  const original = globalThis.fetch;
  const before = structuredClone(saved);
  globalThis.fetch = async () => new Response(JSON.stringify({ state: saved }), { status: 200 });
  try {
    const client = new PanelFlowApiClient("http://127.0.0.1:8765", "current-session");
    const result = await client.getStoryEditorState("project");
    for (const layer of result.state.scenes[0].layers) {
      assert.equal(layer.image_url, client.getPageImageUrl("project", layer.source_page_id));
      assert.doesNotMatch(layer.image_url, /previous-session/);
    }
    assert.deepEqual(result.state.narration_clips, saved.narration_clips);
    assert.deepEqual(result.state.scenes[0].layers[0].transform, { scale: 1.4 });
    assert.deepEqual(saved, before);
  } finally { globalThis.fetch = original; }
});

test("saving persists credential-free page references and hydrates the returned aligned state without mutating input", async () => {
  const original = globalThis.fetch;
  const input = structuredClone(saved);
  const before = structuredClone(input);
  let captured: RequestInit | undefined;
  globalThis.fetch = async (_url, init) => {
    captured = init;
    const payload = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ state: payload.state, updated_at: "fixture-time" }), { status: 200 });
  };
  try {
    const client = new PanelFlowApiClient("http://127.0.0.1:8765", "current-session");
    const result = await client.saveStoryEditorState("project", input, true);
    const payload = JSON.parse(String(captured?.body));
    assert.equal(captured?.method, "PUT");
    assert.equal(new Headers(captured?.headers).get("X-PanelFlow-Token"), "current-session");
    assert.equal(payload.align_panels, true);
    for (const layer of payload.state.scenes[0].layers) {
      assert.equal(layer.image_url, `/api/projects/project/pages/${layer.source_page_id}/file`);
    }
    assert.doesNotMatch(String(captured?.body), /pf-token|previous-session|current-session/);
    for (const layer of result.state.scenes[0].layers) {
      assert.equal(layer.image_url, client.getPageImageUrl("project", layer.source_page_id));
    }
    assert.equal(result.updated_at, "fixture-time");
    assert.deepEqual(input, before);
  } finally { globalThis.fetch = original; }
});

test("legacy query credentials normalize to a path capability before retained cache parameters", async () => {
  const original = globalThis.fetch;
  const state = { scenes: [{ layers: [
    { source_page_id: "page", source_panel_id: "panel", image_url: "/api/projects/project/pages/page/file?token=old-query&v=42&pf-token=old-again" },
    { source_page_id: "normalized", image_url: "http://localhost:8765/api/projects/project/pages/normalized/normalized-file;pf-token=old-path?engine_token=old-query&v=43" },
  ] }] };
  const persisted: any[] = [];
  globalThis.fetch = async (_url, init) => {
    const responseState = init?.body ? JSON.parse(String(init.body)).state : state;
    if (init?.body) persisted.push(responseState);
    return new Response(JSON.stringify({ state: responseState, updated_at: "fixture" }));
  };
  try {
    const client = new PanelFlowApiClient("http://127.0.0.1:8765", "first-session");
    client.setEngineToken("next-session");
    const result = await client.getStoryEditorState("project");
    const urls = result.state.scenes[0].layers.map((layer: any) => layer.image_url);
    assert.deepEqual(urls, [
      "http://127.0.0.1:8765/api/projects/project/pages/page/file;pf-token=next-session?v=42",
      "http://127.0.0.1:8765/api/projects/project/pages/normalized/normalized-file;pf-token=next-session?v=43",
    ]);
    await client.saveStoryEditorState("project", result.state);
    assert.deepEqual(persisted[0].scenes[0].layers.map((layer: any) => layer.image_url), [
      "/api/projects/project/pages/page/file?v=42", "/api/projects/project/pages/normalized/normalized-file?v=43",
    ]);
    assert.equal(persisted[0].scenes[0].layers[0].source_panel_id, "panel");
  } finally { globalThis.fetch = original; }
});

test("hydration never signs external, mismatched, credentialed or non-page image references", async () => {
  const original = globalThis.fetch;
  const urls = [
    "https://example.test/api/projects/project/pages/page/file?token=user-owned",
    "http://127.0.0.1:9999/api/projects/project/pages/page/file",
    "http://localhost.evil.test:8765/api/projects/project/pages/page/file",
    "http://user:password@127.0.0.1:8765/api/projects/project/pages/page/file",
    "/api/projects/other-project/pages/page/file",
    "/api/projects/project/pages/other-page/file",
    "/api/projects/project/panels/panel/file",
    "data:image/png;base64,Zml4dHVyZQ==", "blob:https://example.test/fixture", "not-an-engine-image.png", "http://[invalid",
  ];
  const state = { scenes: [{ layers: urls.map((image_url) => ({ source_page_id: "page", image_url })) }] };
  let persisted: any;
  globalThis.fetch = async (_url, init) => {
    if (init?.body) persisted = JSON.parse(String(init.body)).state;
    return new Response(JSON.stringify({ state, updated_at: "fixture" }));
  };
  try {
    const client = new PanelFlowApiClient("http://127.0.0.1:8765", "private-fixture");
    assert.deepEqual((await client.getStoryEditorState("project")).state, state);
    await client.saveStoryEditorState("project", state);
    assert.deepEqual(persisted, state);
    assert.doesNotMatch(JSON.stringify(persisted), /private-fixture/);
  } finally { globalThis.fetch = original; }
});

test("missing editor state and non-layer extension data survive hydration", async () => {
  const original = globalThis.fetch;
  let state: any = null;
  globalThis.fetch = async () => new Response(JSON.stringify({ state }));
  try {
    const client = new PanelFlowApiClient();
    assert.deepEqual(await client.getStoryEditorState("project"), { state: null });
    state = { custom: { image_url: "unchanged" }, scenes: [null, {}, { layers: [null, {}] }] };
    assert.deepEqual((await client.getStoryEditorState("project")).state, state);
    state = saved;
    const result = await client.getStoryEditorState("project");
    assert.equal(result.state.scenes[0].layers[0].image_url, "http://127.0.0.1:8765/api/projects/project/pages/page-old/file");
  } finally { globalThis.fetch = original; }
});

test("saved Setup panel crops rotate capabilities and preserve crop versions only for the matching panel", () => {
  const client = new PanelFlowApiClient("http://127.0.0.1:8765", "current-panel-session");
  const state = { scenes: [{ layers: [{ source_page_id: "page", source_panel_id: "panel",
    image_url: "http://127.0.0.1:8765/api/projects/project/panels/panel/file;pf-token=expired?v=selector.png" }] }] };
  const clean = client.sanitizeStoryEditorState("project", state);
  assert.equal(clean.scenes[0].layers[0].image_url, "/api/projects/project/panels/panel/file?v=selector.png");
  assert.equal(client.hydrateStoryEditorState("project", clean).scenes[0].layers[0].image_url,
    "http://127.0.0.1:8765/api/projects/project/panels/panel/file;pf-token=current-panel-session?v=selector.png");
  const mismatch = { scenes: [{ layers: [{ source_panel_id: "other", image_url: "/api/projects/project/panels/panel/file?v=1" }] }] };
  assert.deepEqual(client.hydrateStoryEditorState("project", mismatch), mismatch);
  assert.match(state.scenes[0].layers[0].image_url, /expired/, "input is immutable");
});
