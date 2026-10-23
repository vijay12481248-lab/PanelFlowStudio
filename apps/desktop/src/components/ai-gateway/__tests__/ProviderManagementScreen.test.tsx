import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ProviderManagementContent, loadProviderManagementData } from "../ProviderManagementScreen";

const provider = { provider_id: "ollama", provider_name: "Local Ollama", is_local: true, is_multimodal: true, is_healthy: false };
const model = { name: "vision-model", supports_vision: true, supports_tools: false, supports_thinking: false, family: "test", parameter_size: "7B", quantization_level: "Q4", format: "gguf", capabilities: ["vision"] };
const data = { providers: [provider], models: [model], errors: [] as string[] };
const render = (section: "overview" | "models" | "routing" | "usage" | "diagnostics", query = "", input = data) => renderToStaticMarkup(
  <ProviderManagementContent data={input} section={section} query={query} />
);

test("provider overview renders actual identity and offline health, not assumed success", () => {
  const html = render("overview");
  assert.match(html, /Local Ollama/);
  assert.match(html, /Unavailable/);
  assert.doesNotMatch(html, /Connected|HEALTHY/);
  assert.doesNotMatch(render("overview", "missing"), /Local Ollama/);
});

test("model explorer uses the model inventory, not provider rows", () => {
  const html = render("models", "VISION");
  assert.match(html, /vision-model/);
  assert.match(html, /Q4/);
  assert.doesNotMatch(render("models", "missing"), /vision-model/);
});

test("unsupported gateway features show unavailable instead of fake statistics or settings", () => {
  for (const section of ["routing", "usage", "diagnostics"] as const) {
    assert.match(render(section), /not available/i);
    assert.doesNotMatch(render(section), /98%|120|Selected Ollama|HEALTHY|Save Settings/);
  }
});

test("load errors are visible and distinct from a successful empty inventory", () => {
  const html = render("overview", "", { providers: [], models: [], errors: ["Provider inventory could not be loaded."] });
  assert.match(html, /role="alert"/);
  assert.match(html, /could not be loaded/);
  assert.doesNotMatch(html, /No providers registered/);
  assert.match(render("overview", "", { providers: [], models: [], errors: [] }), /No providers registered/);
});

test("partial API failure preserves successful data without exposing raw backend errors", async () => {
  const result = await loadProviderManagementData({
    listLLMProviders: async () => [provider],
    getOllamaModels: async () => { throw new Error("secret-backend-detail"); },
  });
  assert.deepEqual(result.providers, [provider]);
  assert.deepEqual(result.models, []);
  assert.deepEqual(result.errors, ["Ollama model inventory could not be loaded."]);
  assert.doesNotMatch(JSON.stringify(result), /secret-backend-detail/);
});

test("Ollama inspection fallback without capabilities does not crash any section", () => {
  // Exact fallback shape returned when the backend's /api/show probe fails.
  const fallback = { name: "uninspected-model", supports_vision: false, supports_tools: false, supports_thinking: false, family: "unknown", parameter_size: "unknown", quantization_level: "unknown" };
  for (const section of ["overview", "models", "routing", "usage", "diagnostics"] as const) {
    const html = renderToStaticMarkup(<ProviderManagementContent data={{ ...data, models: [fallback] }} section={section} query="" />);
    if (section === "models") {
      assert.match(html, /uninspected-model/);
      assert.match(html, /Not reported/);
    }
  }
});

test("provider locality is not inferred from the legacy API's unreliable is_local flag", () => {
  const html = render("overview", "", { ...data, providers: [{ ...provider, provider_name: "Remote server", is_local: true }] });
  assert.match(html, /Remote server/);
  assert.doesNotMatch(html, />Local/);
});
