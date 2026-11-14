import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import { DiagnosticsSection } from "../DiagnosticsSection";

const HARDWARE = { os_name: "Windows", os_release: "11", architecture: "AMD64", cpu_count: 16, total_ram_gb: 31.9, available_ram_gb: 18.2, total_disk_gb: 931.5, free_disk_gb: 412, gpu_name: "RTX 5060 Ti", vram_mb: 16384, cuda_available: true, ffmpeg_available: true, ffmpeg_hwaccels: ["cuda"], neural_performance_tier: "GOOD" };
const EXPORT = { panelflow_version: "1.0.0", diagnostic_schema: "1", generated_at: "2026-11-08T12:00:00Z", hardware: { os: "Windows 11" }, providers: [] };

function stub(over: Record<string, unknown> = {}) {
  const calls = { exports: 0 };
  Object.assign(api as any, {
    getHardwareDiagnostics: async () => HARDWARE,
    exportDiagnostics: async () => { calls.exports++; return EXPORT; },
    ...over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string) => [...d.querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;

test("hardware rows are shown in plain units", async () => {
  stub();
  const view = await mountPage(<DiagnosticsSection />);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("18.2 of 31.9 GB free"));
  assert.ok(body.includes("RTX 5060 Ti, 16.0 GB"));
  assert.ok(body.includes("Good"));
  await view.cleanup();
});

test("Export diagnostics downloads the sanitized file once and says it should be reviewed before sharing", async () => {
  const calls = stub();
  const saved: Array<{ filename: string; json: string }> = [];
  const view = await mountPage(<DiagnosticsSection download={(filename, json) => saved.push({ filename, json })} />);
  await view.settle();
  assert.ok(text(view.document).includes("This file has paths and secrets removed. Review it before you share it."));
  await view.clickTwice(button(view.document, "Export diagnostics")!);
  await view.settle();
  assert.equal(calls.exports, 1);
  assert.equal(saved.length, 1);
  assert.equal(saved[0].filename, "panelflow-diagnostics-2026-11-08T12-00-00Z.json");
  assert.deepEqual(JSON.parse(saved[0].json), EXPORT);
  await view.cleanup();
});

test("Copy diagnostics puts the same JSON on the clipboard and confirms", async () => {
  stub();
  const copied: string[] = [];
  const view = await mountPage(<DiagnosticsSection copy={async (value) => { copied.push(value); }} />);
  await view.settle();
  await view.click(button(view.document, "Copy diagnostics")!);
  await view.settle();
  assert.deepEqual(JSON.parse(copied[0]), EXPORT);
  assert.ok(text(view.document).includes("Copied"));
  await view.cleanup();
});

test("when the export fails the page says what to do and keeps the button", async () => {
  stub({ exportDiagnostics: async () => { throw new Error("secret path C:/Users/x"); } });
  const view = await mountPage(<DiagnosticsSection />);
  await view.settle();
  await view.click(button(view.document, "Export diagnostics")!);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("Couldn't export diagnostics. Check that the engine is running, then try again."));
  assert.ok(!body.includes("C:/Users/x"), "no raw exception text");
  assert.ok(button(view.document, "Export diagnostics"));
  await view.cleanup();
});

test("when hardware cannot be read an error shows but Export is still offered", async () => {
  stub({ getHardwareDiagnostics: async () => { throw new Error("x"); } });
  const view = await mountPage(<DiagnosticsSection />);
  await view.settle();
  await new Promise((resolve) => setTimeout(resolve, 1300)); // one retry after 1 second
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't read the hardware details"));
  assert.ok(button(view.document, "Export diagnostics"));
  await view.cleanup();
});
