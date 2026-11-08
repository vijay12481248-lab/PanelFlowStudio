import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import { YouTubeSection } from "../YouTubeSection";

const FakeModal: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) =>
  open ? <div role="dialog" aria-label="Legacy settings"><button onClick={onClose}>Close legacy</button></div> : null;

const status = (over: Record<string, unknown>) => ({ configured: false, connected: false, pending: false, error: null, ...over });
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string) => [...d.querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;

async function show(s: Record<string, unknown> | Error) {
  (api as any).youtubeStatus = async () => { if (s instanceof Error) throw s; return status(s); };
  const view = await mountPage(<YouTubeSection ModalComponent={FakeModal} />);
  await view.settle();
  return view;
}

test("the three connection states are said in words", async () => {
  for (const [state, word] of [[{}, "Not set up"], [{ configured: true }, "Not connected"], [{ configured: true, connected: true }, "Connected"], [{ configured: true, pending: true }, "Waiting for you to finish signing in"]] as const) {
    const view = await show(state);
    assert.ok(text(view.document).includes(word), word);
    await view.cleanup();
  }
});

test("the engine's error text is shown when there is one", async () => {
  const view = await show({ configured: true, error: "The refresh token expired." });
  assert.ok(text(view.document).includes("The refresh token expired."));
  await view.cleanup();
});

test("Open YouTube settings opens the existing settings window, and closing returns here", async () => {
  const view = await show({ configured: true, connected: true });
  assert.equal(view.document.querySelector('[role="dialog"]'), null);
  await view.click(button(view.document, "Open YouTube settings")!);
  assert.ok(view.document.querySelector('[role="dialog"][aria-label="Legacy settings"]'));
  await view.click(button(view.document, "Close legacy")!);
  assert.equal(view.document.querySelector('[role="dialog"]'), null);
  await view.cleanup();
});

test("it says uploads are private by default and that nothing here publishes", async () => {
  const view = await show({});
  const body = text(view.document);
  assert.ok(body.includes("Uploads are private by default."));
  assert.ok(body.includes("Nothing on this page publishes or schedules a video."));
  await view.cleanup();
});

test("when the status cannot be read an error shows but the settings window can still be opened", async () => {
  const view = await show(new Error("down"));
  await new Promise((resolve) => setTimeout(resolve, 1300)); // one retry after 1 second
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't read the YouTube connection"));
  assert.ok(!text(view.document).includes("down"));
  assert.ok(button(view.document, "Open YouTube settings"));
  await view.cleanup();
});
