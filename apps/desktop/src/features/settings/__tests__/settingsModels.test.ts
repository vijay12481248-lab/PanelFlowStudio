import test from "node:test";
import assert from "node:assert/strict";
import type { ProviderHealth, SystemResourcesResponse } from "@panelflow/shared-types";
import type { OllamaConfig, OllamaModelCapability } from "@panelflow/shared-types";
import type { GlobalLLMSettings, LLMProviderInfo } from "@panelflow/shared-types";
import type { HardwareDiagnostics } from "@panelflow/shared-types";
import { diagnosticsFilename, hardwareRows, WORKFLOWS, localFirstWarning, providerOptions, routingChanged, routingFromSettings, routingToRequest, changedOllamaFields, draftFromConfig, modelsForRole, pullPercent, resourceGauges, toolRows, validateEndpointUrl } from "../settingsModels";

const resources = (gpuUsed: number, over: Partial<SystemResourcesResponse["gpu"]> = {}, ramUsedPct = 40): SystemResourcesResponse => ({
  ram: { total_gb: 32, available_gb: 32 * (1 - ramUsedPct / 100), used_percent: ramUsedPct, sufficient_for_inference: true },
  gpu: { available: true, device_name: "RTX 5060 Ti", total_mb: 16384, free_mb: 16384 - gpuUsed, used_mb: gpuUsed, used_percent: (gpuUsed / 16384) * 100, headroom_mb: 1000, ...over },
  ollama: { online: true, loaded_models_count: 0, total_ollama_vram_mb: 0, models: [] },
} as SystemResourcesResponse);

test("resourceGauges shows GPU memory and RAM with rounded percentages and readable sizes", () => {
  const [gpu, ram] = resourceGauges(resources(13_100));
  assert.equal(gpu.id, "gpu");
  assert.equal(gpu.label, "GPU memory");
  assert.equal(gpu.usedLabel, "12.8 of 16.0 GB");
  assert.equal(gpu.percent, 80);
  assert.equal(ram.id, "ram");
  assert.equal(ram.usedLabel, "12.8 of 32.0 GB");
  assert.equal(ram.percent, 40);
});

test("a gauge turns to warning at 85 percent and to bad at 95", () => {
  const tone = (used: number) => resourceGauges(resources(used))[0].tone;
  assert.equal(tone(Math.round(16384 * 0.84)), "ok");
  assert.equal(tone(Math.round(16384 * 0.85)), "warn");
  assert.equal(tone(Math.round(16384 * 0.94)), "warn");
  assert.equal(tone(Math.round(16384 * 0.95)), "bad");
});

test("without a GPU only the RAM gauge is shown", () => {
  const gauges = resourceGauges(resources(0, { available: false }));
  assert.deepEqual(gauges.map((g) => g.id), ["ram"]);
});

const provider = (id: string, status: string, details = ""): ProviderHealth => ({ id, name: id.toUpperCase(), category: "audio_engine", status, version: "", path: "", required: true, details });

test("toolRows reports FFmpeg and maps provider statuses to ready, problem or missing", () => {
  const rows = toolRows({
    ffmpeg: { found: true, version: "6.1" },
    providers: [provider("a", "HEALTHY"), provider("b", "READY"), provider("c", "DEGRADED"), provider("d", "OFFLINE"), provider("e", "BROWSER_RUNTIME_MISSING"), provider("f", "ERROR")],
  });
  assert.deepEqual(rows[0], { id: "ffmpeg", label: "FFmpeg", state: "ready", detail: "Found, version 6.1" });
  assert.deepEqual(rows.slice(1).map((r) => [r.id, r.state]), [["a", "ready"], ["b", "ready"], ["c", "problem"], ["d", "missing"], ["e", "missing"], ["f", "missing"]]);
});

test("toolRows says FFmpeg is not found and copes with nothing loaded yet", () => {
  assert.equal(toolRows({ ffmpeg: { found: false, version: null } })[0].detail, "Not found");
  assert.equal(toolRows({ ffmpeg: { found: false, version: null } })[0].state, "missing");
  assert.deepEqual(toolRows({}), []);
});

test("a provider row explains its status in words, not the raw code", () => {
  const [row] = toolRows({ providers: [provider("x", "NOT_RUNNING", "Start the service.")] });
  assert.equal(row.detail, "Not running. Start the service.");
});

const CONFIG: OllamaConfig = { endpoint_url: "http://127.0.0.1:11434", is_remote: false, has_auth_token: true, vision_model: "v:1", reasoning_model: "r:1", narration_model: "n:1", num_ctx: 8192, concurrency_mode: "AUTO", max_gpu_concurrency: 1 };

test("an untouched draft changes nothing and never carries the saved token", () => {
  const draft = draftFromConfig(CONFIG);
  assert.equal(draft.auth_token, "");
  assert.deepEqual(changedOllamaFields(CONFIG, draft), {});
});

test("only the fields that changed are sent, and the token only when one was typed", () => {
  const draft = draftFromConfig(CONFIG);
  assert.deepEqual(changedOllamaFields(CONFIG, { ...draft, vision_model: "v:2" }), { vision_model: "v:2" });
  assert.deepEqual(changedOllamaFields(CONFIG, { ...draft, concurrency_mode: "MANUAL", max_gpu_concurrency: 2 }), { concurrency_mode: "MANUAL", max_gpu_concurrency: 2 });
  assert.deepEqual(changedOllamaFields(CONFIG, { ...draft, auth_token: "abc" }), { auth_token: "abc" });
});

test("validateEndpointUrl explains what to fix", () => {
  assert.equal(validateEndpointUrl("http://127.0.0.1:11434"), null);
  assert.equal(validateEndpointUrl("https://ollama.example.com"), null);
  assert.equal(validateEndpointUrl(""), "Enter the address of your Ollama server, for example http://127.0.0.1:11434.");
  assert.equal(validateEndpointUrl("not a url"), "Enter the address of your Ollama server, for example http://127.0.0.1:11434.");
  assert.equal(validateEndpointUrl("ftp://host"), "Use an http or https address.");
  assert.equal(validateEndpointUrl("http://user:pw@host:11434"), "Remove the username and password from the address and use the token field.");
});

const model = (name: string, over: Partial<OllamaModelCapability> = {}): OllamaModelCapability => ({
  name, supports_vision: false, supports_tools: false, supports_thinking: false, family: "f", parameter_size: "9B", quantization_level: "Q4", format: "gguf", capabilities: ["completion"], ...over,
});

test("modelsForRole offers vision models for vision and text models for the rest", () => {
  const models = [model("vision", { supports_vision: true, capabilities: ["completion", "vision"] }), model("text"), model("embed", { capabilities: ["embedding"] })];
  assert.deepEqual(modelsForRole(models, "vision").map((m) => m.name), ["vision"]);
  assert.deepEqual(modelsForRole(models, "reasoning").map((m) => m.name), ["vision", "text"]);
  assert.deepEqual(modelsForRole([model("old", { capabilities: [] })], "narration").map((m) => m.name), ["old"]);
});

test("pullPercent uses bytes when it can and stays within 0 to 100", () => {
  assert.equal(pullPercent({ completed_bytes: 250, total_bytes: 1000 }), 25);
  assert.equal(pullPercent({ completed_bytes: 0, total_bytes: 0, percent: 42 }), 42);
  assert.equal(pullPercent({ completed_bytes: 2000, total_bytes: 1000 }), 100);
  assert.equal(pullPercent({ completed_bytes: 0, total_bytes: 0 }), 0);
});

const SETTINGS: GlobalLLMSettings = {
  global_default_provider: "ollama", global_default_model: "qwen:9b",
  flow_overrides: { story_script: { provider_id: "groq", model_name: "llama-3.3" } },
  providers: [
    { id: "ollama", name: "Local Ollama", type: "local", is_configured: true, is_healthy: true, models: [] },
    { id: "openrouter", name: "OpenRouter", type: "cloud", is_configured: false, is_healthy: false, models: [] },
    { id: "groq", name: "Groq", type: "cloud", is_configured: true, is_healthy: true, models: [] },
  ],
};
const INFO: LLMProviderInfo[] = [{ provider_id: "ollama", provider_name: "Local Ollama", is_local: true, is_multimodal: true, is_healthy: true }, { provider_id: "custom", provider_name: "My gateway", is_local: false, is_multimodal: false, is_healthy: false }];

test("the four workflows are listed in a fixed order with plain names", () => {
  assert.deepEqual(WORKFLOWS.map((w) => [w.key, w.label]), [["story_narration", "Story narration"], ["story_script", "Script writing"], ["character_analysis", "Character profiling"], ["vision_inspection", "Panel and OCR inspection"]]);
});

test("routing round-trips and an untouched draft is not a change", () => {
  const draft = routingFromSettings(SETTINGS);
  assert.deepEqual(draft, { provider: "ollama", model: "qwen:9b", overrides: SETTINGS.flow_overrides });
  assert.equal(routingChanged(SETTINGS, draft), false);
  assert.equal(routingChanged(SETTINGS, { ...draft, model: "other" }), true);
  assert.equal(routingChanged(SETTINGS, { ...draft, overrides: { ...draft.overrides, story_narration: { provider_id: "groq" } } }), true);
});

test("choosing 'use the default' for a workflow is not saved as an override, and is not a change from nothing", () => {
  const draft = routingFromSettings({ ...SETTINGS, flow_overrides: {} });
  const withGlobal = { ...draft, overrides: { story_script: { provider_id: "global", model_name: "" } } };
  assert.equal(routingChanged({ ...SETTINGS, flow_overrides: {} }, withGlobal), false);
  assert.deepEqual(routingToRequest(withGlobal), { global_default_provider: "ollama", global_default_model: "qwen:9b", flow_overrides: {} });
  assert.deepEqual(routingToRequest(routingFromSettings(SETTINGS)).flow_overrides, { story_script: { provider_id: "groq", model_name: "llama-3.3" } });
});

test("providerOptions merges the catalog and the provider list and marks readiness", () => {
  const options = providerOptions(SETTINGS, INFO);
  assert.deepEqual(options.map((o) => [o.id, o.local, o.ready]), [["ollama", true, true], ["openrouter", false, false], ["groq", false, true], ["custom", false, false]]);
  assert.equal(options.find((o) => o.id === "custom")!.name, "My gateway");
});

test("localFirstWarning names every cloud provider in use and stays quiet for local-only routing", () => {
  const options = providerOptions(SETTINGS, INFO);
  assert.equal(localFirstWarning({ provider: "ollama", model: "m", overrides: {} }, options), null);
  assert.equal(localFirstWarning({ provider: "ollama", model: "m", overrides: { story_script: { provider_id: "global", model_name: "" } } }, options), null);
  assert.equal(localFirstWarning({ provider: "ollama", model: "m", overrides: { story_script: { provider_id: "openrouter" } } }, options), "Cloud routing sends your text to OpenRouter. Keep Local Ollama as the default unless you mean to.");
  assert.match(localFirstWarning({ provider: "groq", model: "m", overrides: { story_script: { provider_id: "openrouter" } } }, options)!, /OpenRouter and Groq|Groq and OpenRouter/);
  assert.match(localFirstWarning({ provider: "mystery", model: "m", overrides: {} }, options)!, /mystery/);
});

const HARDWARE: HardwareDiagnostics = {
  os_name: "Windows", os_release: "11", architecture: "AMD64", cpu_count: 16, total_ram_gb: 31.9, available_ram_gb: 18.2, total_disk_gb: 931.5, free_disk_gb: 412.04,
  gpu_name: "NVIDIA GeForce RTX 5060 Ti", vram_mb: 16384, cuda_available: true, ffmpeg_available: true, ffmpeg_hwaccels: ["cuda", "d3d11va"], neural_performance_tier: "GOOD",
} as HardwareDiagnostics;

test("hardwareRows reads like a spec sheet in plain units", () => {
  const rows = Object.fromEntries(hardwareRows(HARDWARE).map((r) => [r.label, r.value]));
  assert.equal(rows["System"], "Windows 11, AMD64");
  assert.equal(rows["Processor cores"], "16");
  assert.equal(rows["RAM"], "18.2 of 31.9 GB free");
  assert.equal(rows["Disk"], "412.0 of 931.5 GB free");
  assert.equal(rows["GPU"], "NVIDIA GeForce RTX 5060 Ti, 16.0 GB");
  assert.equal(rows["CUDA"], "Yes");
  assert.equal(rows["FFmpeg"], "Yes, with cuda, d3d11va");
  assert.equal(rows["Performance"], "Good");
});

test("hardwareRows handles no CUDA, no FFmpeg and every tier", () => {
  const none = Object.fromEntries(hardwareRows({ ...HARDWARE, cuda_available: false, ffmpeg_available: false, ffmpeg_hwaccels: [], vram_mb: 0, gpu_name: "" }).map((r) => [r.label, r.value]));
  assert.equal(none["CUDA"], "No");
  assert.equal(none["FFmpeg"], "No");
  assert.equal(none["GPU"], "None found");
  const tier = (t: HardwareDiagnostics["neural_performance_tier"]) => hardwareRows({ ...HARDWARE, neural_performance_tier: t }).find((r) => r.label === "Performance")!.value;
  assert.deepEqual(["GOOD", "SUPPORTED", "LIMITED", "UNSUPPORTED"].map((t) => tier(t as never)), ["Good", "Supported", "Limited", "Not supported"]);
});

test("diagnosticsFilename is safe on Windows and sorts by time", () => {
  assert.equal(diagnosticsFilename({ generated_at: "2026-11-08T12:00:00.123Z" }), "panelflow-diagnostics-2026-11-08T12-00-00Z.json");
  assert.equal(diagnosticsFilename({ generated_at: "" }).startsWith("panelflow-diagnostics-"), true);
  assert.ok(!/[:*?"<>|]/.test(diagnosticsFilename({ generated_at: "2026-11-08T12:00:00Z" })));
});
