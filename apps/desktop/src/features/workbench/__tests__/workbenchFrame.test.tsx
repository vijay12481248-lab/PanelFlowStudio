import { mount } from "../../../../../../packages/ui/src/v2/__tests__/dom"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { MemoryRouter } from "react-router";
import type { PipelineStage, Project } from "@panelflow/shared-types";
import { WorkbenchFrame } from "../WorkbenchFrame";

const project = (stage: PipelineStage, over: Partial<Project> = {}) =>
  ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [], ready_pages: 3, total_pages: 3, ...over }) as Project;

async function show(p: Project, stage: "ocr" | "publish" = "ocr", onAutoPilot = () => {}) {
  return mount(<MemoryRouter><WorkbenchFrame project={p} stage={stage} onAutoPilot={onAutoPilot}><p id="child">stage body</p></WorkbenchFrame></MemoryRouter>);
}
const text = (d: Document) => d.body.textContent ?? "";
const labelOf = (li: Element) => (li.textContent ?? "").split(":")[0].replace(/(Stale|Blocked)$/, "");

test("the frame has one page heading with the project title, a way back, and the stage body inside it", async () => {
  const view = await show(project("OCR_COMPLETE"));
  assert.equal(view.document.querySelectorAll("h1").length, 1);
  assert.equal(view.document.querySelector("h1")!.textContent, "Dawn Gate");
  assert.ok([...view.document.querySelectorAll("a")].some((a) => a.textContent === "Projects" && a.getAttribute("href") === "/projects"));
  assert.ok(view.document.querySelector("[data-stage-body] #child"));
  await view.cleanup();
});

test("the stepper lists the ten stages in order and marks the one being viewed", async () => {
  const view = await show(project("OCR_COMPLETE"));
  const items = [...view.document.querySelectorAll('ol[aria-label="Pipeline stages"] > li')];
  assert.deepEqual(items.map(labelOf), ["Source", "Pages", "Panels", "OCR", "Story", "Script", "Audio", "Motion", "Render", "Publish"]);
  const current = view.document.querySelectorAll('ol[aria-label="Pipeline stages"] [aria-current="step"]');
  assert.equal(current.length, 1);
  assert.ok(current[0].textContent!.startsWith("OCR"));
  await view.cleanup();
});

test("steps are links to their stage, except stages that are not reachable yet", async () => {
  const view = await show(project("OCR_COMPLETE"));
  const li = (label: string) => [...view.document.querySelectorAll('ol[aria-label="Pipeline stages"] > li')].find((x) => labelOf(x) === label)!;
  assert.equal(li("Panels").querySelector("a")!.getAttribute("href"), "/projects/p1/panels");
  assert.ok(li("Story").querySelector("a"), "the next stage can be opened");
  assert.equal(li("Publish").querySelector("a"), null, "later stages are not links");
  await view.cleanup();
});

test("stale and blocked stages say so in words", async () => {
  const view = await show(project("MOTION_APPROVED", { rights_status: "UNKNOWN" as Project["rights_status"], stale_stages: ["audio"] }));
  const body = text(view.document);
  assert.ok(body.includes("Stale"));
  assert.ok(body.includes("Blocked"));
  assert.ok(body.includes("Rights unknown"));
  assert.ok(body.includes("Needs a rerun"));
  await view.cleanup();
});

test("there is exactly one Auto-Pilot button and it opens Auto-Pilot", async () => {
  let opened = 0;
  const view = await show(project("OCR_COMPLETE"), "ocr", () => { opened++; });
  const buttons = [...view.document.querySelectorAll("button")].filter((b) => b.textContent?.trim() === "Auto-Pilot");
  assert.equal(buttons.length, 1);
  await view.click(buttons[0]);
  assert.equal(opened, 1);
  await view.cleanup();
});

test("Open story editor links to the editor for this project", async () => {
  const view = await show(project("OCR_COMPLETE"));
  const link = [...view.document.querySelectorAll("a")].filter((a) => a.textContent?.trim() === "Open story editor");
  assert.equal(link.length, 1);
  assert.equal(link[0].getAttribute("href"), "/editor/p1");
  await view.cleanup();
});

test("the header says where the project is in plain words", async () => {
  const view = await show(project("OCR_COMPLETE"));
  assert.ok(text(view.document).includes("OCR ready for review"));
  assert.ok(text(view.document).includes("Authorized web"));
  await view.cleanup();
});
