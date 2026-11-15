import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { RenderJob } from "@panelflow/shared-types";
import { RenderResult } from "../RenderResult";

const REPORT = {
  is_valid: true, gate_status: "PRODUCTION_READY", file_size_bytes: 92299740, planned_duration_sec: 137.87, actual_duration_sec: 137.866667, duration_diff_sec: 0.003,
  black_frames_count: 0, timeline_gaps_count: 0, clipping_samples_count: 0, sync_valid: false, duration_sec: 137.866667, warnings: ["Two black frames near 0:12"],
  frame_samples: [{ timestamp_sec: 2, frame_index: 60, mean_luminance: 101.2 }, { timestamp_sec: 60.5, frame_index: 1815, mean_luminance: 88 }],
  quality_flags: {}, semantic_qa: {},
};
const complete = (over: Record<string, unknown> = {}) => ({ render_id: "r1", project_id: "p1", status: "COMPLETE", current_stage: "COMPLETE", progress: 1, frames_done: 4136, frames_total: 4136, output_profile: "standard_1080p", output_path: "C:\\renders\\video.mp4", validation_report: REPORT, ...over }) as unknown as RenderJob;

const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? "") || label.test(b.getAttribute("aria-label") ?? ""))) as HTMLButtonElement | undefined;
const tab = (d: Document, label: RegExp) => [...d.querySelectorAll('[role="tab"]')].find((t) => label.test(t.textContent ?? "")) as HTMLElement;

function stub() {
  const opened: any[][] = [];
  Object.assign(api as any, {
    getRenderVideoUrl: (_p: string, id: string) => `/video/${id}.mp4`,
    getRenderContactSheetUrl: (_p: string, id: string) => `/sheet/${id}.jpg`,
    getRenderAuditSampleUrl: (_p: string, id: string, i: number) => `/sample/${id}/${i}.jpg`,
    openPath: async (...a: any[]) => { opened.push(a); return { opened: true, path: a[0] }; },
  });
  return opened;
}
async function show(render: RenderJob, extra: Partial<React.ComponentProps<typeof RenderResult>> = {}) {
  const view = await mountPage(<RenderResult projectId="p1" render={render} onPublish={() => {}} {...extra} />);
  await view.settle();
  return view;
}

test("a finished render shows the video, its verdict, the explained sync flag, duration, size and warnings", async () => {
  stub();
  const view = await show(complete());
  assert.equal(view.document.querySelector("video")!.getAttribute("src"), "/video/r1.mp4");
  const body = text(view.document);
  assert.ok(body.includes("Ready for production"));
  assert.ok(body.includes("Not confirmed"));
  assert.ok(body.includes("still passed the render as production ready"));
  assert.ok(body.includes("137.87s") && body.includes("0.003s"));
  assert.ok(body.includes("88.0 MiB"));
  assert.ok(body.includes("Two black frames near 0:12"));
  assert.ok(body.includes("video.mp4"));
  await view.cleanup();
});

test("the contact sheet and audit samples have their own tabs, and each broken image says so on its own", async () => {
  stub();
  const view = await show(complete());
  await view.press(tab(view.document, /^Contact sheet/));
  const sheet = view.document.querySelector('img[src="/sheet/r1.jpg"]')!;
  assert.ok(sheet);
  await view.fire(sheet, "error");
  assert.ok(text(view.document).includes("Contact sheet unavailable"));
  await view.press(tab(view.document, /^Audit samples/));
  const first = view.document.querySelector('img[src="/sample/r1/0.jpg"]')!;
  assert.ok(first && view.document.querySelector('img[src="/sample/r1/1.jpg"]'));
  await view.fire(first, "error");
  assert.ok(text(view.document).includes("Sample 1 unavailable"));
  assert.ok(view.document.querySelector('img[src="/sample/r1/1.jpg"]'), "the other sample is unaffected");
  await view.cleanup();
});

test("a sample marker seeks the video to its time", async () => {
  stub();
  const view = await show(complete());
  const video = view.document.querySelector("video") as HTMLVideoElement;
  let seeked = -1;
  Object.defineProperty(video, "currentTime", { configurable: true, get: () => seeked, set: (v: number) => { seeked = v; } });
  await view.click(button(view.document, "Seek to 60.5 seconds")!);
  assert.equal(seeked, 60.5);
  await view.cleanup();
});

test("Open file and Open folder open once each, with the right flag", async () => {
  const opened = stub();
  const view = await show(complete());
  await view.clickTwice(button(view.document, "Open file")!);
  await view.click(button(view.document, "Open folder")!);
  assert.deepEqual(opened, [["C:\\renders\\video.mp4", true], ["C:\\renders\\video.mp4", false]]);
  await view.cleanup();
});

test("Export QA audit hands the report to the download function and never uses a browser dialog", async () => {
  stub();
  const downloads: Array<[string, string]> = [];
  const w = window as any;
  const savedAlert = w.alert; w.alert = () => { throw new Error("alert must not be used"); };
  try {
    const view = await show(complete(), { download: (name, content) => { downloads.push([name, content]); } });
    await view.click(button(view.document, "Export QA audit")!);
    assert.equal(downloads.length, 1);
    assert.equal(downloads[0][0], "qa_audit_r1.json");
    assert.equal(JSON.parse(downloads[0][1]).gate_status, "PRODUCTION_READY");
    await view.cleanup();
  } finally { w.alert = savedAlert; }
});

test("a render whose report arrives as a string is read", async () => {
  stub();
  const view = await show(complete({ validation_report: JSON.stringify(REPORT) }));
  assert.ok(text(view.document).includes("Ready for production"));
  await view.cleanup();
});

test("a render with no report says the checks are missing and still shows the video", async () => {
  stub();
  const view = await show(complete({ validation_report: null }));
  assert.ok(text(view.document).includes("No checks yet"));
  assert.ok(view.document.querySelector("video"));
  await view.cleanup();
});

test("a failed render shows its error in words and no media", async () => {
  stub();
  const view = await show(complete({ status: "FAILED", error_message: "The encoder stopped.", validation_report: null }));
  assert.ok(text(view.document).includes("The encoder stopped."));
  assert.equal(view.document.querySelector("video"), null);
  assert.equal(view.document.querySelectorAll('[role="tab"]').length, 0);
  await view.cleanup();
});

test("Continue to publish hands over to the Publish stage", async () => {
  stub();
  let published = 0;
  const view = await show(complete(), { onPublish: () => { published++; } });
  assert.ok(text(view.document).includes("check the render and copy the packaging in Publish"));
  await view.click(button(view.document, "Continue to publish")!);
  assert.equal(published, 1);
  await view.cleanup();
});
