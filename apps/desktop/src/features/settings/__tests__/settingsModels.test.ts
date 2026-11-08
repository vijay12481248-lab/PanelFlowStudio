import test from "node:test";
import assert from "node:assert/strict";
import type { ProviderHealth, SystemResourcesResponse } from "@panelflow/shared-types";
import { resourceGauges, toolRows } from "../settingsModels";

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
