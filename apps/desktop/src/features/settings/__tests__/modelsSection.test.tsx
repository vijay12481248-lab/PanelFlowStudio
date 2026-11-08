import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import { ModelsSection } from "../ModelsSection";

const SECRET = "SECRET-TOKEN-4f9a";
const model = (name: string, vision = false) => ({ name, supports_vision: vision, supports_tools: true, supports_thinking: false, family: "qwen", parameter_size: "9B", quantization_level: "Q4_K_M", format: "gguf", capabilities: vision ? ["completion", "vision"] : ["completion"] });

function stub(over: Record<string, unknown> = {}) {
  const state = { config: { endpoint_url: "http://127.0.0.1:11434", is_remote: false, has_auth_token: false, vision_model: "qwen:9b", reasoning_model: "qwen:9b", narration_model: "qwen:9b", num_ctx: 8192, concurrency_mode: "AUTO", max_gpu_concurrency: 1 } as Record<string, unknown>, saves: [] as unknown[], pulls: [] as string[], pullStatusCalls: 0, pullStatus: { status: "IDLE", model_name: "", status_text: "", completed_bytes: 0, total_bytes: 0, percent: 0, error_message: null } as Record<string, unknown> };
  Object.assign(api as any, {
    getOllamaConfig: async () => ({ ...state.config }),
    getOllamaModels: async () => ({ models: [model("qwen:9b", true), model("llama:3b")], recommendations: { vision_model: "qwen:9b", reasoning_model: "qwen:9b", narration_model: "qwen:9b" }, endpoint_url: "x", is_remote: false, healthy: true }),
    saveOllamaConfig: async (fields: Record<string, unknown>) => { state.saves.push(fields); const { auth_token, ...rest } = fields; Object.assign(state.config, rest, auth_token ? { has_auth_token: true } : {}); return { ...state.config }; },
    testOllamaConnection: async () => ({ status: "OK", connected: true }),
    pullOllamaModel: async (name: string) => { state.pulls.push(name); return { status: "STARTED", model: name }; },
    getOllamaPullStatus: async () => { state.pullStatusCalls++; return state.pullStatus; },
    ...over,
  });
  return state;
}

const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string) => [...d.querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const field = (d: Document, label: string) => {
  const l = [...d.querySelectorAll("label")].find((x) => x.textContent === label);
  return (l ? d.getElementById(l.getAttribute("for")!) : null) as HTMLInputElement & HTMLSelectElement;
};

test("Save changes is off until something changes, then saves once with only that field", async () => {
  const state = stub();
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  assert.equal(button(view.document, "Save changes")!.disabled, true);
  await view.setSelect(field(view.document, "Vision model"), "qwen:9b"); // same value: still clean
  assert.equal(button(view.document, "Save changes")!.disabled, true);
  await view.setSelect(field(view.document, "Narration model"), "llama:3b");
  assert.equal(button(view.document, "Save changes")!.disabled, false);
  await view.clickTwice(button(view.document, "Save changes")!);
  await view.settle();
  assert.deepEqual(state.saves, [{ narration_model: "llama:3b" }]);
  assert.equal(button(view.document, "Save changes")!.disabled, true, "clean again after saving");
  await view.cleanup();
});

test("Discard puts the form back as it was saved", async () => {
  stub();
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  await view.setSelect(field(view.document, "Narration model"), "llama:3b");
  await view.click(button(view.document, "Discard")!);
  assert.equal(field(view.document, "Narration model").value, "qwen:9b");
  await view.cleanup();
});

test("a typed token is write-only: cleared after saving and found nowhere in the page or the caches", async () => {
  const state = stub();
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  const token = field(view.document, "Access token (optional)");
  assert.equal(token.type, "password");
  assert.equal(token.autocomplete, "off");
  await view.setValue(token, SECRET);
  await view.click(button(view.document, "Save changes")!);
  await view.settle();
  assert.deepEqual(state.saves, [{ auth_token: SECRET }]);
  assert.equal(field(view.document, "Access token (optional)").value, "", "input cleared");
  assert.ok(text(view.document).includes("Saved in the system keychain"));
  assert.ok(!view.document.body.innerHTML.includes(SECRET), "not in the DOM");
  const queries = JSON.stringify(view.client.getQueryCache().getAll().map((q) => q.state.data));
  const mutations = JSON.stringify(view.client.getMutationCache().getAll().map((m) => [m.state.variables, m.state.data]));
  assert.ok(!queries.includes(SECRET) && !mutations.includes(SECRET), "not in the query or mutation cache");
  assert.ok(!JSON.stringify(Object.entries(localStorage)).includes(SECRET), "not in storage");
  await view.cleanup();
});

test("a failed save keeps your changes and says what failed", async () => {
  stub({ saveOllamaConfig: async () => { throw new Error("The engine refused the change."); } });
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  await view.setSelect(field(view.document, "Narration model"), "llama:3b");
  await view.click(button(view.document, "Save changes")!);
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't save the setting"));
  assert.equal(field(view.document, "Narration model").value, "llama:3b");
  assert.equal(button(view.document, "Save changes")!.disabled, false);
  await view.cleanup();
});

test("a bad endpoint is explained before anything is sent", async () => {
  const state = stub();
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  await view.setValue(field(view.document, "Server address"), "http://user:pw@host:11434");
  await view.click(button(view.document, "Save changes")!);
  assert.ok(text(view.document).includes("Remove the username and password from the address"));
  assert.deepEqual(state.saves, []);
  await view.cleanup();
});

test("when Ollama's settings cannot be read the section says what to do and offers no Save", async () => {
  stub({ getOllamaConfig: async () => { throw new Error("connection refused"); } });
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  await new Promise((resolve) => setTimeout(resolve, 1300)); // one retry after 1 second
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("Couldn't reach Ollama's settings"));
  assert.ok(!body.includes("connection refused"));
  assert.equal(button(view.document, "Save changes"), undefined);
  await view.cleanup();
});

test("Test connection reports the result in words", async () => {
  stub();
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  await view.click(button(view.document, "Test connection")!);
  await view.settle();
  assert.ok(text(view.document).includes("Connected"));
  await view.cleanup();
});

test("models are listed with their size and capabilities, and recommended ones are marked", async () => {
  stub();
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("llama:3b") && body.includes("9B") && body.includes("Q4_K_M"));
  assert.ok(body.includes("Vision"));
  assert.ok(body.includes("Recommended"));
  await view.cleanup();
});

test("pulling a model shows progress, allows one pull at a time, and stops polling when you leave", async () => {
  const state = stub();
  const view = await mountPage(<ModelsSection />);
  await view.settle();
  await view.setValue(field(view.document, "Model to download"), "gemma:2b");
  await view.clickTwice(button(view.document, "Pull model")!);
  await view.settle();
  assert.deepEqual(state.pulls, ["gemma:2b"], "one pull started");
  state.pullStatus = { status: "PULLING", model_name: "gemma:2b", status_text: "pulling layers", completed_bytes: 250, total_bytes: 1000, percent: 25, error_message: null };
  await new Promise((resolve) => setTimeout(resolve, 1800));
  await view.settle();
  assert.ok([...view.document.querySelectorAll('[role="progressbar"]')].some((b) => b.getAttribute("aria-valuenow") === "25"));
  assert.equal(button(view.document, "Pull model")!.disabled, true);
  await view.cleanup();
  const calls = state.pullStatusCalls;
  await new Promise((resolve) => setTimeout(resolve, 1800));
  assert.equal(state.pullStatusCalls, calls, "no polling after the page is left");
});
