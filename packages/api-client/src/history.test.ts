import test from "node:test";
import assert from "node:assert/strict";
import { PanelFlowApiClient } from "./index";

const history = (revision: number) => ({ scope: "project:p", revision, undoCount: revision, redoCount: 0, canUndo: revision > 0, canRedo: false, undoLabel: "Edit", redoLabel: null, busy: false, conflicted: false, recoveryRequired: false, fingerprint: "f".repeat(64), error: null });

test("audio URLs from persisted timeline clips resolve through the authenticated engine file route", () => {
  const client = new PanelFlowApiClient("http://127.0.0.1:8765", "test-only");
  const persisted = "/api/projects/p/audio/dialogue/speech.wav";
  assert.equal(
    client.getAudioFileUrl("p", persisted),
    "http://127.0.0.1:8765/api/projects/p/audio/file;pf-token=test-only?path=audio%2Fdialogue%2Fspeech.wav",
  );
});
test("editor persistence carries loaded history revision, preserves retry ID, and observes authoritative replies", async () => {
  const original = globalThis.fetch;
  const calls: any[] = []; let fail = false;
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), body: options?.body ? JSON.parse(String(options.body)) : null });
    if (fail) throw new Error("network fixture");
    return new Response(JSON.stringify({ state: { project_id: "p", scenes: [] }, history: history(options?.method === "PUT" ? 4 : 3), updated_at: "fixture" }));
  };
  try {
    const client = new PanelFlowApiClient();
    await client.getStoryEditorState("p");
    await client.saveStoryEditorState("p", { project_id: "p", scenes: [] });
    assert.equal(calls[1].body.expected_revision, 3);
    assert.match(calls[1].body.operation_id, /^[a-f0-9-]{36}$/);
    assert.equal(client.getCachedProjectHistory("p")?.revision, 4);
    const state = { project_id: "p", scenes: [{ id: "s", layers: [] }] };
    fail = true; await assert.rejects(client.saveStoryEditorState("p", state));
    const failed = calls.at(-1).body;
    fail = false; await client.saveStoryEditorState("p", state);
    assert.equal(calls.at(-1).body.operation_id, failed.operation_id);
    assert.equal(calls.at(-1).body.expected_revision, failed.expected_revision);
  } finally { globalThis.fetch = original; }
});

test("undo/redo use server revisions and hydrate returned engine image references", async () => {
  const original = globalThis.fetch; const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const undo = String(url).endsWith("/undo");
    calls.push({ url: String(url), body: options?.body && JSON.parse(String(options.body)) });
    return new Response(JSON.stringify({ state: { project_id: "p", scenes: [{ layers: [{ source_panel_id: "panel", image_url: "/api/projects/p/panels/panel/file" }] }] }, history: history(undo ? 2 : 1), replayed: false }));
  };
  try {
    const client = new PanelFlowApiClient("http://127.0.0.1:8765", "test-only");
    await client.getProjectHistory("p");
    const result = await client.moveProjectHistory("p", "undo");
    assert.equal(calls[1].body.expected_revision, 1);
    assert.match(result.state!.scenes[0].layers[0].image_url, /;pf-token=test-only/);
    assert.equal(client.getCachedProjectHistory("p")?.revision, 2);
  } finally { globalThis.fetch = original; }
});

test("panel reorder is a revisioned project command and refreshes canonical panels", async () => {
  const original = globalThis.fetch; const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url); const body = options?.body && JSON.parse(String(options.body));
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(4) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(5) }));
    return new Response(JSON.stringify([{ id: "two" }, { id: "one" }]));
  };
  try {
    const client = new PanelFlowApiClient();
    const panels = await client.reorderPanels("p", ["two", "one"]);
    assert.deepEqual(panels.map(panel => panel.id), ["two", "one"]);
    assert.equal(calls[1].body.type, "panel.reorder");
    assert.equal(calls[1].body.expected_revision, 4);
    assert.deepEqual(calls[1].body.input, { panel_ids: ["two", "one"] });
    assert.equal(client.getCachedProjectHistory("p")?.revision, 5);
  } finally { globalThis.fetch = original; }
});

test("panel geometry is a revisioned project command and returns the canonical panel", async () => {
  const original = globalThis.fetch; const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url); const body = options?.body && JSON.parse(String(options.body));
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(7) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(8) }));
    return new Response(JSON.stringify([{ id: "panel", x: 10, y: 20, width: 30, height: 40 }]));
  };
  try {
    const client = new PanelFlowApiClient();
    const panel = await client.updatePanel("p", "panel", 10, 20, 30, 40, "CONFIRMED", "FULL_PAGE");
    assert.equal(panel.id, "panel");
    assert.equal(calls[1].body.type, "panel.geometry");
    assert.deepEqual(calls[1].body.input, { panel_id: "panel", x: 10, y: 20, width: 30, height: 40, status: "CONFIRMED", panel_type: "FULL_PAGE" });
    assert.equal(client.getCachedProjectHistory("p")?.revision, 8);
  } finally { globalThis.fetch = original; }
});

test("panel creation supplies an identity and returns that canonical panel", async () => {
  const original = globalThis.fetch; const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url); const body = options?.body && JSON.parse(String(options.body)); calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(9) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(10) }));
    return new Response(JSON.stringify([{ id: "old" }, { id: calls[1].body.input.panel_id, x: 1, y: 2, width: 3, height: 4 }]));
  };
  try {
    const client = new PanelFlowApiClient(); const panel = await client.addPanel("p", "page", 1, 2, 3, 4);
    assert.equal(panel.id, calls[1].body.input.panel_id);
    assert.equal(calls[1].body.type, "panel.create");
    assert.match(calls[1].body.input.panel_id, /^[a-f0-9-]{36}$/);
  } finally { globalThis.fetch = original; }
});


test("panel image blur and reset methods route through revisioned project commands", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(11) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(12) }));
    if (endpoint.endsWith("/blur-status")) return new Response(JSON.stringify({ is_blurred: true, has_backup: true, blurred_regions_count: 2 }));
    if (endpoint.endsWith("/panels")) return new Response(JSON.stringify([{ id: "p1" }, { id: "p2" }]));
    return new Response(JSON.stringify({ success: true }));
  };
  try {
    const client = new PanelFlowApiClient();

    // blurPanelRegion
    calls.length = 0;
    const resRegion = await client.blurPanelRegion("p", "p1", { x: 10, y: 20, width: 30, height: 40 });
    assert.equal(resRegion.success, true);
    const cmdRegion = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdRegion.body.type, "panel.image.blur_region");
    assert.deepEqual(cmdRegion.body.input, { panel_id: "p1", x: 10, y: 20, width: 30, height: 40 });

    // blurPanelText
    calls.length = 0;
    const resText = await client.blurPanelText("p", "p1", { region_ids: ["r1"] });
    assert.equal(resText.success, true);
    assert.equal(resText.blurred_count, 2);
    const cmdText = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdText.body.type, "panel.image.blur_text");
    assert.deepEqual(cmdText.body.input, { panel_id: "p1", region_ids: ["r1"] });

    // blurEntirePanel
    calls.length = 0;
    const resEntire = await client.blurEntirePanel("p", "p1", 32);
    assert.equal(resEntire.success, true);
    const cmdEntire = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdEntire.body.type, "panel.image.blur_panel");
    assert.deepEqual(cmdEntire.body.input, { panel_id: "p1", blur_radius: 32 });

    // batchBlurPanels
    calls.length = 0;
    const resBatchBlur = await client.batchBlurPanels("p", { preset: "TOP_WATERMARK" });
    assert.equal(resBatchBlur.success, true);
    const cmdBatchBlur = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdBatchBlur.body.type, "panel.image.batch_blur");

    // batchResetPanels
    calls.length = 0;
    const resBatchReset = await client.batchResetPanels("p", ["p1"]);
    assert.equal(resBatchReset.success, true);
    const cmdBatchReset = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdBatchReset.body.type, "panel.image.batch_reset");
  } finally { globalThis.fetch = original; }
});


test("page reorder, rotate and delete methods route through revisioned project commands", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(20) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(21) }));
    if (endpoint.endsWith("/pages")) return new Response(JSON.stringify([{ id: "page-1" }, { id: "page-2" }]));
    return new Response(JSON.stringify({ success: true }));
  };
  try {
    const client = new PanelFlowApiClient();

    // reorderPages
    calls.length = 0;
    const reordered = await client.reorderPages("p", ["page-2", "page-1"]);
    assert.equal(reordered.length, 2);
    const cmdReorder = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdReorder.body.type, "page.reorder");
    assert.deepEqual(cmdReorder.body.input, { page_ids: ["page-2", "page-1"] });

    // rotatePage
    calls.length = 0;
    const rotated = await client.rotatePage("p", "page-1", 90);
    assert.equal(rotated.id, "page-1");
    const cmdRotate = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdRotate.body.type, "page.rotate");
    assert.deepEqual(cmdRotate.body.input, { page_id: "page-1", degrees: 90 });

    // deletePage
    calls.length = 0;
    await client.deletePage("p", "page-1");
    const cmdDelete = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdDelete.body.type, "page.delete");
    assert.deepEqual(cmdDelete.body.input, { page_id: "page-1" });
  } finally { globalThis.fetch = original; }
});


test("project confirm and OCR methods route through revisioned project commands", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(30) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(31) }));
    if (endpoint.endsWith("/api/projects/p")) return new Response(JSON.stringify({ id: "p", current_stage: "ACQUIRED" }));
    if (endpoint.includes("/text-regions")) {
      const lastCmd = calls.slice().reverse().find(c => c.endpoint.endsWith("/history/commands"));
      const rId = lastCmd?.body?.input?.region_id || "reg-1";
      return new Response(JSON.stringify([{ id: rId, panel_id: "panel-1", corrected_text: "Hello!" }]));
    }
    if (endpoint.endsWith("/ocr")) return new Response(JSON.stringify({ panel_id: "panel-1", adapted_blocks: [{ id: "b1", text: "Updated" }] }));
    return new Response(JSON.stringify({ success: true }));
  };
  try {
    const client = new PanelFlowApiClient();

    // confirmAcquisition
    calls.length = 0;
    const proj = await client.confirmAcquisition("p");
    assert.equal(proj.current_stage, "ACQUIRED");
    const cmdConfirmAcq = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdConfirmAcq.body.type, "project.confirm");

    // createManualTextRegion
    calls.length = 0;
    const createdRegion = await client.createManualTextRegion("p", "panel-1", 10, 20, 30, 40, "SPEECH");
    assert.ok(createdRegion);
    const cmdCreateRegion = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdCreateRegion.body.type, "ocr.region.create");
    assert.equal(cmdCreateRegion.body.input.panel_id, "panel-1");
    assert.equal(cmdCreateRegion.body.input.x, 10);
    assert.equal(cmdCreateRegion.body.input.y, 20);

    // updateTextRegion
    calls.length = 0;
    const updatedRegion = await client.updateTextRegion("p", "reg-1", { corrected_text: "Hello!" });
    assert.equal(updatedRegion.id, "reg-1");
    const cmdUpdateRegion = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdUpdateRegion.body.type, "ocr.region.update");
    assert.equal(cmdUpdateRegion.body.input.region_id, "reg-1");
    assert.equal(cmdUpdateRegion.body.input.corrected_text, "Hello!");

    // deleteTextRegion
    calls.length = 0;
    await client.deleteTextRegion("p", "reg-1");
    const cmdDeleteRegion = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdDeleteRegion.body.type, "ocr.region.delete");
    assert.equal(cmdDeleteRegion.body.input.region_id, "reg-1");

    // updateAdaptedBlock
    calls.length = 0;
    const updatedBlock = await client.updateAdaptedBlock("p", "panel-1", "b1", { text: "Updated" });
    assert.equal(updatedBlock.panel_id, "panel-1");
    const cmdBlock = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdBlock.body.type, "ocr.block.update");
    assert.equal(cmdBlock.body.input.panel_id, "panel-1");
    assert.equal(cmdBlock.body.input.block_id, "b1");
    assert.equal(cmdBlock.body.input.text, "Updated");

    // confirmOCR
    calls.length = 0;
    const ocrApproved = await client.confirmOCR("p");
    assert.equal(ocrApproved.current_stage, "OCR_APPROVED");
    const cmdConfirmOCR = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdConfirmOCR.body.type, "ocr.confirm");
  } finally { globalThis.fetch = original; }
});


test("story, character, scene, script and storyboard methods route through revisioned project commands", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(40) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(41) }));
    if (endpoint.endsWith("/characters")) {
      const lastCmd = calls.slice().reverse().find(c => c.endpoint.endsWith("/history/commands"));
      const charId = lastCmd?.body?.input?.new_character_id || lastCmd?.body?.input?.target_character_id || "char-1";
      return new Response(JSON.stringify([{ id: charId, character_id: charId, display_name: "Hero", aliases: ["Champion"] }]));
    }
    if (endpoint.endsWith("/scenes")) return new Response(JSON.stringify([{ id: "scene-1", scene_id: "scene-1", title: "Merged Scene" }]));
    if (endpoint.endsWith("/scripts")) return new Response(JSON.stringify({ id: "script-1", segments: [{ id: "seg-1", segment_id: "seg-1", text: "New narration", estimated_duration: 3.5 }] }));
    if (endpoint.endsWith("/storyboard")) return new Response(JSON.stringify({ id: "sb-1", segments: [{ segment_id: "seg-1", text: "Updated storyboard" }] }));
    return new Response(JSON.stringify({ success: true }));
  };
  try {
    const client = new PanelFlowApiClient();

    // confirmStory
    calls.length = 0;
    const resConfirm = await client.confirmStory("p");
    assert.equal(resConfirm.current_stage, "STORY_APPROVED");
    const cmdConfirm = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdConfirm.body.type, "story.confirm");

    // updateCharacter
    calls.length = 0;
    const updatedChar = await client.updateCharacter("p", "char-1", {
      display_name: "Hero",
      reference_asset_id: "asset-1",
      generation_params: { seed: 123 },
      proposed_changes: { description: "Updated" },
      change_status: "PENDING_REVIEW",
    });
    assert.equal(updatedChar.id, "char-1");
    const cmdUpdChar = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdUpdChar.body.type, "character.update");
    assert.equal(cmdUpdChar.body.input.character_id, "char-1");
    assert.equal(cmdUpdChar.body.input.display_name, "Hero");
    assert.equal(cmdUpdChar.body.input.reference_asset_id, "asset-1");
    assert.deepEqual(cmdUpdChar.body.input.generation_params, { seed: 123 });
    assert.deepEqual(cmdUpdChar.body.input.proposed_changes, { description: "Updated" });
    assert.equal(cmdUpdChar.body.input.change_status, "PENDING_REVIEW");

    // updateCharacter with explicit null unlinking
    calls.length = 0;
    await client.updateCharacter("p", "char-1", {
      reference_asset_id: null,
    });
    const cmdUnlink = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdUnlink.body.input.reference_asset_id, null);

    // mergeCharacters
    calls.length = 0;
    const mergedChar = await client.mergeCharacters("p", "char-source", "char-target");
    assert.equal(mergedChar.id, "char-target");
    const cmdMergeChar = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdMergeChar.body.type, "character.merge");
    assert.equal(cmdMergeChar.body.input.source_character_id, "char-source");
    assert.equal(cmdMergeChar.body.input.target_character_id, "char-target");

    // splitCharacter
    calls.length = 0;
    const splitChar = await client.splitCharacter("p", "char-1", "New Hero", ["panel-1"]);
    assert.ok(splitChar.id);
    const cmdSplitChar = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdSplitChar.body.type, "character.split");
    assert.equal(cmdSplitChar.body.input.character_id, "char-1");
    assert.equal(cmdSplitChar.body.input.new_name, "New Hero");
    assert.deepEqual(cmdSplitChar.body.input.panel_ids, ["panel-1"]);

    // mergeScenes
    calls.length = 0;
    const mergedScene = await client.mergeScenes("p", "scene-1", "scene-2");
    assert.equal(mergedScene.id, "scene-1");
    const cmdMergeScene = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdMergeScene.body.type, "scene.merge");
    assert.equal(cmdMergeScene.body.input.scene_id_1, "scene-1");
    assert.equal(cmdMergeScene.body.input.scene_id_2, "scene-2");

    // updateScriptSegment
    calls.length = 0;
    const updatedSeg = await client.updateScriptSegment("p", "script-1", "seg-1", { text: "New narration", estimated_duration: 3.5 });
    assert.equal(updatedSeg.id, "seg-1");
    const cmdUpdSeg = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdUpdSeg.body.type, "script.segment.update");
    assert.equal(cmdUpdSeg.body.input.script_id, "script-1");
    assert.equal(cmdUpdSeg.body.input.segment_id, "seg-1");
    assert.equal(cmdUpdSeg.body.input.text, "New narration");

    // approveScript
    calls.length = 0;
    const approvedScript = await client.approveScript("p", "script-1");
    assert.equal(approvedScript.status, "APPROVED");
    const cmdApproveScript = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdApproveScript.body.type, "script.approve");
    assert.equal(cmdApproveScript.body.input.script_id, "script-1");

    // updateStoryboardSegment
    calls.length = 0;
    const updatedSb = await client.updateStoryboardSegment("p", "seg-1", { text: "Updated storyboard" });
    assert.equal(updatedSb.segment_id, "seg-1");
    const cmdUpdSb = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdUpdSb.body.type, "storyboard.segment.update");
    assert.equal(cmdUpdSb.body.input.segment_id, "seg-1");

    // realignStoryboard
    calls.length = 0;
    const realignedSb = await client.realignStoryboard("p");
    assert.ok(realignedSb);
    const cmdRealign = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdRealign.body.type, "storyboard.realign");
  } finally { globalThis.fetch = original; }
});

test("setShotOverrides routes through executeProjectHistoryCommand", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(50) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(51) }));
    return new Response(JSON.stringify({ id: "mt-1", project_id: "p", status: "DRAFT", overrides_json: {} }));
  };
  try {
    const client = new PanelFlowApiClient();
    await client.setShotOverrides("p", { shot1: { pan: "left" } });
    const cmdOvr = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmdOvr.body.type, "motion.overrides");
    assert.deepEqual(cmdOvr.body.input.overrides, { shot1: { pan: "left" } });
  } finally { globalThis.fetch = original; }
});

test("approveMotionTimeline routes through executeProjectHistoryCommand", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(50) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(51) }));
    return new Response(JSON.stringify({ success: true }));
  };
  try {
    const client = new PanelFlowApiClient();
    const res = await client.approveMotionTimeline("p");
    assert.equal(res.approved, true);
    const cmd = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmd.body.type, "motion.approve");
  } finally { globalThis.fetch = original; }
});

test("acceptMotionPlan routes through executeProjectHistoryCommand", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(50) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(51) }));
    return new Response(JSON.stringify({ id: "mt-1", project_id: "p", status: "DRAFT", timeline_json: {} }));
  };
  try {
    const client = new PanelFlowApiClient();
    await client.acceptMotionPlan("p", { total_duration: 12.0, style_preset: "cinematic" });
    const cmd = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmd.body.type, "motion.plan.accept");
    assert.deepEqual(cmd.body.input.plan, { total_duration: 12.0, style_preset: "cinematic" });
  } finally { globalThis.fetch = original; }
});

test("approveAudioTimeline routes through executeProjectHistoryCommand", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(50) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(51) }));
    return new Response(JSON.stringify({ success: true }));
  };
  try {
    const client = new PanelFlowApiClient();
    const res = await client.approveAudioTimeline("p");
    assert.equal(res.approved, true);
    const cmd = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmd.body.type, "audio.approve");
  } finally { globalThis.fetch = original; }
});

test("acceptAudioDraft routes through executeProjectHistoryCommand", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(50) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(51) }));
    return new Response(JSON.stringify({ id: "at-1", project_id: "p", status: "DRAFT", timeline_json: {} }));
  };
  try {
    const client = new PanelFlowApiClient();
    await client.acceptAudioDraft("p", { total_duration: 10.0 });
    const cmd = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmd.body.type, "audio.draft.accept");
    assert.deepEqual(cmd.body.input.draft, { total_duration: 10.0 });
  } finally { globalThis.fetch = original; }
});

test("acceptSynthesizedAudio routes through executeProjectHistoryCommand", async () => {
  const original = globalThis.fetch;
  const calls: any[] = [];
  globalThis.fetch = async (url, options) => {
    const endpoint = String(url);
    const body = options?.body ? JSON.parse(String(options.body)) : null;
    calls.push({ endpoint, body });
    if (endpoint.endsWith("/history")) return new Response(JSON.stringify({ state: null, history: history(50) }));
    if (endpoint.endsWith("/history/commands")) return new Response(JSON.stringify({ state: null, history: history(51) }));
    return new Response(JSON.stringify({ id: "at-1", project_id: "p", status: "DRAFT", timeline_json: {} }));
  };
  try {
    const client = new PanelFlowApiClient();
    await client.acceptSynthesizedAudio("p", { total_duration: 10.5, audio_files: ["audio/clip1.wav"] });
    const cmd = calls.find(c => c.endpoint.endsWith("/history/commands"));
    assert.equal(cmd.body.type, "audio.synthesized.accept");
    assert.deepEqual(cmd.body.input.result, { total_duration: 10.5, audio_files: ["audio/clip1.wav"] });
  } finally { globalThis.fetch = original; }
});
