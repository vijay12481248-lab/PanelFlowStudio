import { mountPage } from "../../__tests__/pageHarness";
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import { LibraryPage } from "../LibraryPage";

function stubLibrary() {
  (api as any).listProjects = async () => [
    {
      id: "p1",
      title: "Test Manga Chapter 1",
      current_stage: "OCR_COMPLETE",
      total_pages: 5,
    },
  ];
  (api as any).listPages = async () => [
    { id: "page_1", sequence: 1, filename: "slice_0001.webp", width: 1200, height: 800 },
    { id: "page_2", sequence: 2, filename: "slice_0002.webp", width: 1200, height: 800 },
  ];
  (api as any).getPageImageUrl = (_pid: string, id: string) => `/test-page/${id}.png`;
  (api as any).getAudioProviders = async () => ({
    primary_provider: "chatterbox_turbo",
    providers: [
      {
        id: "chatterbox_turbo",
        name: "Chatterbox Turbo",
        voices: [
          { id: "the narrator", name: "Aria (The Narrator)", gender: "Female", ref: "aria.wav" },
          { id: "marcus", name: "Marcus (Male Warrior)", gender: "Male", ref: "marcus.wav" },
        ],
      },
    ],
  });
}

test("LibraryPage renders PageHeader and the three library tabs", async () => {
  stubLibrary();
  const view = await mountPage(<LibraryPage />, "/page");
  await view.settle();

  // Heading check
  assert.ok(view.document.body.textContent!.includes("Library"));

  // Check the 3 tabs
  const triggers = [...view.document.querySelectorAll('[role="tab"]')];
  const tabNames = triggers.map((t) => t.textContent?.trim());
  assert.ok(tabNames.some((n) => n?.includes("Audio & Music")));
  assert.ok(tabNames.some((n) => n?.includes("Visual Media & Slices")));
  assert.ok(tabNames.some((n) => n?.includes("Voice Cast")));

  // In default audio tab, AudioLibrary container is present
  assert.ok(view.document.querySelector('[data-testid="audio-library-container"]'));

  await view.cleanup();
});

test("LibraryPage media tab renders project selector and slices", async () => {
  stubLibrary();
  const view = await mountPage(<LibraryPage />, "/page");
  await view.settle();

  // Find the media tab and press it
  const mediaTab = [...view.document.querySelectorAll('[role="tab"]')].find((t) =>
    t.textContent?.includes("Visual Media")
  );
  assert.ok(mediaTab);
  await view.press(mediaTab!);
  await view.settle();

  // Project selector should be visible
  assert.ok(view.document.body.textContent!.includes("Select Project:"));
  assert.ok(view.document.body.textContent!.includes("Test Manga Chapter 1"));

  // Slices should render
  assert.ok(view.document.body.textContent!.includes("#1"));
  assert.ok(view.document.body.textContent!.includes("slice_0001.webp"));

  await view.cleanup();
});

test("LibraryPage voices tab renders speech engine and voice profiles", async () => {
  stubLibrary();
  const view = await mountPage(<LibraryPage />, "/page");
  await view.settle();

  // Find the voice cast tab and press it
  const voicesTab = [...view.document.querySelectorAll('[role="tab"]')].find((t) =>
    t.textContent?.includes("Voice Cast")
  );
  assert.ok(voicesTab);
  await view.press(voicesTab!);
  await view.settle();

  // Voice engine status banner and voices should render
  assert.ok(view.document.body.textContent!.includes("Active Speech Engine"));
  assert.ok(view.document.body.textContent!.includes("chatterbox_turbo"));
  assert.ok(view.document.body.textContent!.includes("Aria (The Narrator)"));
  assert.ok(view.document.body.textContent!.includes("Marcus (Male Warrior)"));
  assert.ok(view.document.body.textContent!.includes("Audition Voice"));

  await view.cleanup();
});
