import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import { ProvidersSection } from "../ProvidersSection";

const API_KEY = "sk-or-SECRET-9c1d";
const CATALOG = [
  { id: "ollama", name: "Local Ollama", type: "local", is_configured: true, is_healthy: true, models: [] },
  { id: "openrouter", name: "OpenRouter", type: "cloud", is_configured: true, is_healthy: true, models: [] },
];

function stub(over: Record<string, unknown> = {}) {
  const state = {
    global: { global_default_provider: "ollama", global_default_model: "qwen:9b", flow_overrides: {} as Record<string, unknown>, providers: CATALOG } as Record<string, unknown>,
    cloud: { provider_type: "openrouter", endpoint_url: "https://openrouter.ai/api/v1", model_name: "llama", has_api_key: false, masked_api_key: "" } as Record<string, unknown>,
    routingSaves: [] as unknown[], cloudSaves: [] as unknown[],
  };
  Object.assign(api as any, {
    getGlobalLLMSettings: async () => JSON.parse(JSON.stringify(state.global)),
    saveGlobalLLMSettings: async (req: Record<string, unknown>) => { state.routingSaves.push(req); Object.assign(state.global, req); return {}; },
    listLLMProviders: async () => [{ provider_id: "ollama", provider_name: "Local Ollama", is_local: true, is_multimodal: true, is_healthy: true }, { provider_id: "openrouter", provider_name: "OpenRouter", is_local: false, is_multimodal: false, is_healthy: true }],
    getCloudLLMConfig: async () => ({ ...state.cloud }),
    saveCloudLLMConfig: async (req: Record<string, unknown>) => { state.cloudSaves.push(req); const { api_key, ...rest } = req; Object.assign(state.cloud, rest, api_key ? { has_api_key: true, masked_api_key: "sk-…9c1d" } : {}); return { ...state.cloud }; },
    testCloudLLMConnection: async () => ({ status: "HEALTHY", connected: true, latency_ms: 120, models_count: 3, models: [] }),
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

test("the four workflows are listed in order and default to the global provider", async () => {
  stub();
  const view = await mountPage(<ProvidersSection />);
  await view.settle();
  const labels = [...view.document.querySelectorAll("label")].map((l) => l.textContent).filter((t) => t?.startsWith("Provider for"));
  assert.deepEqual(labels, ["Provider for Story narration", "Provider for Script writing", "Provider for Character profiling", "Provider for Panel and OCR inspection"]);
  assert.equal(field(view.document, "Provider for Story narration").value, "global");
  await view.cleanup();
});

test("choosing a cloud provider for a workflow warns that text leaves this PC", async () => {
  stub();
  const view = await mountPage(<ProvidersSection />);
  await view.settle();
  assert.ok(!text(view.document).includes("Cloud routing sends your text"));
  await view.setSelect(field(view.document, "Provider for Script writing"), "openrouter");
  assert.ok(text(view.document).includes("Cloud routing sends your text to OpenRouter. Keep Local Ollama as the default unless you mean to."));
  await view.cleanup();
});

test("Save routing is off until a change, saves once on a double click, and drops 'use the default' rows", async () => {
  const state = stub();
  const view = await mountPage(<ProvidersSection />);
  await view.settle();
  assert.equal(button(view.document, "Save routing")!.disabled, true);
  await view.setValue(field(view.document, "Default model"), "qwen:27b");
  await view.clickTwice(button(view.document, "Save routing")!);
  await view.settle();
  assert.deepEqual(state.routingSaves, [{ global_default_provider: "ollama", global_default_model: "qwen:27b", flow_overrides: {} }]);
  assert.equal(button(view.document, "Save routing")!.disabled, true, "clean after saving");
  await view.cleanup();
});

test("a failed routing save keeps the draft and says what failed", async () => {
  stub({ saveGlobalLLMSettings: async () => { throw new Error("Rejected by the engine."); } });
  const view = await mountPage(<ProvidersSection />);
  await view.settle();
  await view.setValue(field(view.document, "Default model"), "x");
  await view.click(button(view.document, "Save routing")!);
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't save the setting"));
  assert.equal(field(view.document, "Default model").value, "x");
  await view.cleanup();
});

test("a cloud API key is write-only: cleared after saving and found nowhere in the page, caches or storage", async () => {
  const state = stub();
  const view = await mountPage(<ProvidersSection />);
  await view.settle();
  const input = field(view.document, "API key");
  assert.equal(input.type, "password");
  assert.equal(input.autocomplete, "off");
  await view.setValue(input, API_KEY);
  await view.click(button(view.document, "Save cloud provider")!);
  await view.settle();
  assert.deepEqual(state.cloudSaves, [{ provider_type: "openrouter", endpoint_url: "https://openrouter.ai/api/v1", model_name: "llama", api_key: API_KEY }]);
  assert.equal(field(view.document, "API key").value, "");
  assert.ok(text(view.document).includes("sk-…9c1d"), "only the engine's masked form is shown");
  assert.ok(!view.document.body.innerHTML.includes(API_KEY));
  const queries = JSON.stringify(view.client.getQueryCache().getAll().map((q) => q.state.data));
  const mutations = JSON.stringify(view.client.getMutationCache().getAll().map((m) => [m.state.variables, m.state.data]));
  assert.ok(!queries.includes(API_KEY) && !mutations.includes(API_KEY));
  assert.ok(!JSON.stringify(Object.entries(localStorage)).includes(API_KEY));
  await view.cleanup();
});

test("saving a cloud provider says it does not switch anything to cloud, and Test connection reports in words", async () => {
  stub();
  const view = await mountPage(<ProvidersSection />);
  await view.settle();
  assert.ok(text(view.document).includes("Saving a cloud provider does not switch any job to it."));
  await view.click(button(view.document, "Test connection")!);
  await view.settle();
  assert.ok(text(view.document).includes("Connected"));
  await view.cleanup();
});

test("the provider list shows Local or Cloud and Ready or Not ready in words", async () => {
  stub();
  const view = await mountPage(<ProvidersSection />);
  await view.settle();
  const body = text(view.document);
  assert.ok(/Local Ollama[\s\S]*Local/.test(body) && body.includes("Ready"));
  assert.ok(body.includes("Cloud"));
  await view.cleanup();
});

test("when routing cannot be read the section says what to do and offers no Save routing", async () => {
  stub({ getGlobalLLMSettings: async () => { throw new Error("nope"); } });
  const view = await mountPage(<ProvidersSection />);
  await view.settle();
  await new Promise((resolve) => setTimeout(resolve, 1300)); // one retry after 1 second
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't load routing settings"));
  assert.ok(!text(view.document).includes("nope"));
  assert.equal(button(view.document, "Save routing"), undefined);
  await view.cleanup();
});
