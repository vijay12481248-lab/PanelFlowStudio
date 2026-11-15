import { mountPage } from "../../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import { BlurPanelControls } from "../BlurPanelControls";
import { BatchBlurDialog } from "../BatchBlurDialog";
import { useRedaction } from "../useRedaction";

interface Calls { blur: any[][]; reset: string[]; batch: any[][]; batchReset: number; changed: number }
function stub(opts: { status?: any; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { blur: [], reset: [], batch: [], batchReset: 0, changed: 0 };
  Object.assign(api as any, {
    getPanelBlurStatus: async () => opts.status ?? { is_blurred: false, has_backup: false, blurred_regions_count: 0 },
    blurEntirePanel: async (...a: any[]) => { calls.blur.push(a); return { success: true, panel_id: a[1] }; },
    resetPanelImage: async (_p: string, id: string) => { calls.reset.push(id); return { success: true, panel_id: id }; },
    batchBlurPanels: async (...a: any[]) => { calls.batch.push(a); return { success: true, project_id: "p1", preset: a[1].preset, blurred_panels_count: 46, total_panels: 46 }; },
    batchResetPanels: async () => { calls.batchReset++; return { success: true, project_id: "p1", restored_panels_count: 46, total_panels: 46 }; },
    ...opts.over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;
const dialogButton = (d: Document, label: string) => button(d.querySelector('[role="dialog"]')!, label);
async function until(cond: () => boolean, ms = 3000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

const Controls: React.FC<{ onChanged: () => void }> = ({ onChanged }) => {
  const redaction = useRedaction("p1", onChanged);
  return <>{redaction.error && <p role="alert">{redaction.error}</p>}<BlurPanelControls projectId="p1" panelId="pn1" buster={1} redaction={redaction} /></>;
};
const Batch: React.FC<{ open: boolean; onClose: () => void; onChanged: () => void }> = ({ open, onClose, onChanged }) => {
  const redaction = useRedaction("p1", onChanged);
  return <BatchBlurDialog open={open} onClose={onClose} redaction={redaction} />;
};

test("the controls say whether a panel is blurred, in words", async () => {
  stub({ status: { is_blurred: true, has_backup: true, blurred_regions_count: 3 } });
  const view = await mountPage(<Controls onChanged={() => {}} />);
  await view.settle();
  await until(() => text(view.document).includes("Blurred"));
  assert.ok(text(view.document).includes("Blurred, 3 regions"));
  assert.ok(text(view.document).includes("Original saved"));
  await view.cleanup();
  stub();
  const plain = await mountPage(<Controls onChanged={() => {}} />);
  await plain.settle();
  await until(() => text(plain.document).includes("Not blurred"));
  assert.ok(text(plain.document).includes("Not blurred"));
  await plain.cleanup();
});

test("Blur panel blurs once on a double click and tells the page something changed", async () => {
  const calls = stub();
  let changed = 0;
  const view = await mountPage(<Controls onChanged={() => { changed++; }} />);
  await view.settle();
  await view.clickTwice(button(view.document, "Blur panel")!);
  await until(() => calls.blur.length > 0);
  await view.settle();
  assert.deepEqual(calls.blur, [["p1", "pn1", 32]]);
  assert.equal(changed, 1);
  await view.cleanup();
});

test("Restore original asks first when the panel is blurred, and restores once", async () => {
  const calls = stub({ status: { is_blurred: true, has_backup: true, blurred_regions_count: 1 } });
  const view = await mountPage(<Controls onChanged={() => {}} />);
  await view.settle();
  await until(() => Boolean(button(view.document, "Restore original") && !button(view.document, "Restore original")!.disabled));
  await view.click(button(view.document, "Restore original")!);
  assert.ok(text(view.document).includes("Restore the original image?"));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(calls.reset.length, 0);
  await view.click(button(view.document, "Restore original")!);
  await view.clickTwice(dialogButton(view.document, "Restore original")!);
  await until(() => calls.reset.length > 0);
  assert.deepEqual(calls.reset, ["pn1"]);
  await view.cleanup();
});

test("a panel that is not blurred has nothing to restore", async () => {
  stub();
  const view = await mountPage(<Controls onChanged={() => {}} />);
  await view.settle();
  await until(() => text(view.document).includes("Not blurred"));
  assert.equal(button(view.document, "Restore original")!.disabled, true);
  await view.cleanup();
});

test("a blur the engine refuses is explained in words", async () => {
  stub({ over: { blurEntirePanel: async () => { throw new Error("Panel image is missing."); } } });
  const view = await mountPage(<Controls onChanged={() => {}} />);
  await view.settle();
  await view.click(button(view.document, "Blur panel")!);
  await until(() => text(view.document).includes("Couldn't blur the panel"));
  assert.ok(text(view.document).includes("Couldn't blur the panel. Panel image is missing."));
  await view.cleanup();
});

test("the batch dialog sends the chosen preset and height once, and reports that the request was sent without claiming a count", async () => {
  const calls = stub();
  let closed = 0;
  const view = await mountPage(<Batch open onClose={() => { closed++; }} onChanged={() => {}} />);
  await view.click(view.document.querySelector('[role="dialog"] input[value="BOTTOM_SUBSCRIBE"]')!);
  const height = view.document.querySelector('[role="dialog"] input[type="number"]') as HTMLInputElement;
  await view.setValue(height, "120");
  await view.clickTwice(dialogButton(view.document, "Blur panels")!);
  await until(() => calls.batch.length > 0);
  await view.settle();
  assert.deepEqual(calls.batch, [["p1", { preset: "BOTTOM_SUBSCRIBE", height_px: 120 }]]);
  const body = text(view.document);
  assert.ok(body.includes("Blur request sent for the panels. Check them, then use Undo if it isn't right."));
  assert.ok(!/\d+ of \d+ panels/.test(body), "the client's own count is not presented as a result");
  await view.click(dialogButton(view.document, "Close")!);
  await view.cleanup();
  void closed;
});

test("presets that do not use a height hide the height field", async () => {
  stub();
  const view = await mountPage(<Batch open onClose={() => {}} onChanged={() => {}} />);
  assert.ok(view.document.querySelector('[role="dialog"] input[type="number"]'), "the default preset uses a height");
  await view.click(view.document.querySelector('[role="dialog"] input[value="ENTIRE_PANEL"]')!);
  assert.equal(view.document.querySelector('[role="dialog"] input[type="number"]'), null);
  await view.click(dialogButton(view.document, "Close")!);
  await view.cleanup();
});

test("restoring every panel needs a second, explicit confirmation and then sends once", async () => {
  const calls = stub();
  const view = await mountPage(<Batch open onClose={() => {}} onChanged={() => {}} />);
  await view.click(dialogButton(view.document, "Restore every panel")!);
  assert.equal(calls.batchReset, 0, "the first click only asks");
  assert.ok(text(view.document).includes("This puts every panel back to its original image. It can't be undone."));
  await view.clickTwice(dialogButton(view.document, "Yes, restore every panel")!);
  await until(() => calls.batchReset > 0);
  await view.settle();
  assert.equal(calls.batchReset, 1);
  await view.click(dialogButton(view.document, "Close")!);
  await view.cleanup();
});

test("a failed batch blur shows words inside the dialog and leaves it open", async () => {
  stub({ over: { batchBlurPanels: async () => { throw new Error("No panels."); } } });
  const view = await mountPage(<Batch open onClose={() => {}} onChanged={() => {}} />);
  await view.click(dialogButton(view.document, "Blur panels")!);
  await until(() => text(view.document).includes("Couldn't blur the panels"));
  assert.ok(text(view.document).includes("Couldn't blur the panels. No panels."));
  assert.ok(view.document.querySelector('[role="dialog"]'));
  await view.click(dialogButton(view.document, "Close")!);
  await view.cleanup();
});
