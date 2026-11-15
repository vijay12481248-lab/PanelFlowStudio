import { mountPage, engineState } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import { EngineSection } from "../EngineSection";

const RESOURCES = {
  ram: { total_gb: 32, available_gb: 19, used_percent: 40, sufficient_for_inference: true },
  gpu: { available: true, device_name: "RTX 5060 Ti", total_mb: 16384, free_mb: 3000, used_mb: 13384, used_percent: 82, headroom_mb: 3000 },
  ollama: { online: true, loaded_models_count: 1, total_ollama_vram_mb: 9000, models: [] },
};
const PROVIDERS = { system_ready: true, providers: [
  { id: "comfyui", name: "ComfyUI", category: "video_engine", status: "HEALTHY", version: "", path: "", required: true, details: "" },
  { id: "tts", name: "Voice engine", category: "audio_engine", status: "OFFLINE", version: "", path: "", required: true, details: "" },
  { id: "playwright", name: "Playwright Reader Engine", category: "acquisition_engine", status: "BROWSER_RUNTIME_MISSING", version: "", path: "", required: false, details: "Chromium is not installed." },
] };

function stub(over: Record<string, unknown> = {}) {
  const calls = { install: 0, provision: 0 };
  Object.assign(api as any, {
    getSystemResources: async () => RESOURCES,
    getProviderHealth: async () => PROVIDERS,
    locateFfmpeg: async () => ({ found: true, ffmpeg_path: "C:/ffmpeg.exe", ffprobe_path: null, version: "6.1", injected_into_path: false }),
    getPlaywrightInstallStatus: async () => ({ status: "IDLE", log_lines: [], error_message: null, exit_code: null }),
    installPlaywrightBrowsers: async () => { calls.install++; return { status: "STARTED", message: "" }; },
    provisionVoices: async () => { calls.provision++; return { success: true, voice_directory: "C:/v", copied_count: 7, total_profiles: 7, profiles: [] }; },
    ...over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string) => [...d.querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;

test("the Engine section shows version, resource gauges and tool status", async () => {
  stub();
  const view = await mountPage(<EngineSection />);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("1.0.0-beta.2"));
  assert.ok(body.includes("Engine ready"));
  const values = [...view.document.querySelectorAll('[role="progressbar"]')].map((b) => b.getAttribute("aria-valuenow"));
  assert.deepEqual(values, ["82", "40"]);
  assert.ok(body.includes("Found, version 6.1"));
  assert.ok(body.includes("COMFYUI") || body.includes("ComfyUI"));
  assert.ok(/Voice engine[\s\S]*Offline/.test(body) || body.includes("Offline"));
  await view.cleanup();
});

test("a failed tool check says so, offers Retry, and the other rows still show", async () => {
  stub({ getProviderHealth: async () => { throw new Error("boom"); } });
  const view = await mountPage(<EngineSection />);
  await view.settle();
  await new Promise((resolve) => setTimeout(resolve, 1300)); // the hook retries a failed read once, after 1 second
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("Couldn't load tool status"));
  assert.ok(!body.includes("boom"), "no raw exception text");
  assert.ok(button(view.document, "Retry"));
  assert.ok(body.includes("Found, version 6.1"), "FFmpeg row still shown");
  await view.cleanup();
});

test("Install Chromium is offered only while it is missing and starts the install once", async () => {
  const calls = stub();
  const view = await mountPage(<EngineSection />);
  await view.settle();
  await view.clickTwice(button(view.document, "Install Chromium")!);
  await view.settle();
  assert.equal(calls.install, 1);
  await view.cleanup();

  stub({ getProviderHealth: async () => ({ system_ready: true, providers: [{ ...PROVIDERS.providers[2], status: "HEALTHY" }] }) });
  const healthy = await mountPage(<EngineSection />);
  await healthy.settle();
  assert.equal(button(healthy.document, "Install Chromium"), undefined);
  await healthy.cleanup();
});

test("Provision voices copies the default voices once and reports how many", async () => {
  const calls = stub();
  const view = await mountPage(<EngineSection />);
  await view.settle();
  await view.clickTwice(button(view.document, "Provision voices")!);
  await view.settle();
  assert.equal(calls.provision, 1);
  assert.ok(text(view.document).includes("7 voices copied"));
  await view.cleanup();
});

test("Restart engine restarts once even on a fast double click", async () => {
  stub();
  let restarts = 0;
  const view = await mountPage(<EngineSection />, "/page", engineState({ restart: async () => { restarts++; } }));
  await view.settle();
  await view.clickTwice(button(view.document, "Restart engine")!);
  await view.settle();
  assert.equal(restarts, 1);
  await view.cleanup();
});

test("a provider that shares an id with the FFmpeg row renders both rows without React key warnings", async () => {
  stub({ getProviderHealth: async () => ({ system_ready: true, providers: [{ id: "ffmpeg", name: "FFmpeg Video Encoder", category: "video_engine", status: "HEALTHY", version: "", path: "", required: true, details: "" }] }) });
  const errors: string[] = [];
  const original = console.error;
  console.error = (...args: unknown[]) => { errors.push(String(args[0])); };
  try {
    const view = await mountPage(<EngineSection />);
    await view.settle();
    assert.ok(text(view.document).includes("FFmpeg Video Encoder"));
    assert.ok(text(view.document).includes("Found, version 6.1"));
    await view.cleanup();
  } finally {
    console.error = original;
  }
  assert.deepEqual(errors.filter((e) => e.includes("same key")), []);
});
