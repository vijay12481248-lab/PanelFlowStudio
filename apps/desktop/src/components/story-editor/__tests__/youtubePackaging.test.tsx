import test from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRequire } from "node:module";
import { api } from "@panelflow/api-client";
import type { Project, YouTubePackagingData } from "@panelflow/shared-types";
import { YouTubePackagingModal } from "../YouTubePackagingModal";

const project: Project = {
  id: "proj_youtube_1",
  title: "The Jade Lantern Oath",
  source_type: "MANGA",
  rights_status: "PUBLIC_DOMAIN",
  workspace_path: "C:/workspaces/proj_youtube_1",
  current_stage: "RENDERED",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const mockPackaging: YouTubePackagingData = {
  project_id: project.id,
  titles: [
    "He Awakened The Forbidden Power... And Everyone Regretted It! | The Jade Lantern Oath [Motion Comic]",
    "When Lin Xia Broke The Ancient Rule... No One Could Stop Them! [Full Episode]",
    "The Secret Kept For A Thousand Years Revealed! | The Jade Lantern Oath Motion Comic",
    "They Thought Lin Xia Was Weak... Until The Mask Came Off!",
  ],
  selected_title: "He Awakened The Forbidden Power... And Everyone Regretted It! | The Jade Lantern Oath [Motion Comic]",
  description: "Lin Xia uncovers the ancient jade lantern.\n\n00:00 - Prologue\n00:15 - The Turning Point\n\n#MotionComic #Anime",
  tags: ["the jade lantern oath", "motion comic", "manga animation", "lin xia", "anime"],
  tags_string: "the jade lantern oath, motion comic, manga animation, lin xia, anime",
  hashtags: ["#JadeLantern", "#MotionComic", "#Anime"],
  hashtags_string: "#JadeLantern #MotionComic #Anime",
  chapters: [
    { timestamp: "00:00", seconds: 0, title: "Prologue" },
    { timestamp: "00:15", seconds: 15, title: "The Turning Point" },
  ],
  thumbnail: {
    aspect_ratio: "16:9",
    recommended_width: 1280,
    recommended_height: 720,
    prompt: "masterpiece anime YouTube thumbnail key art, Lin Xia, teal-haired warrior in crimson robes...",
    negative_prompt: "text, watermark, logo, bad anatomy, deformed hands...",
    workflow_id: "manga_image_generation",
    seed: 20261023,
    text_hooks: ["HE AWAKENED?!", "THE TRUTH REVEALED!"],
    composition_guidance: "Position main subject off-center with high contrast.",
  },
  generated_at: new Date().toISOString(),
  source_profile: "standard_1080p",
};

test("YouTube packaging modal is inert when closed and renders structure when open", () => {
  assert.equal(
    renderToStaticMarkup(
      <YouTubePackagingModal isOpen={false} onClose={() => {}} project={project} />
    ),
    ""
  );

  const html = renderToStaticMarkup(
    <YouTubePackagingModal isOpen={true} onClose={() => {}} project={project} />
  );
  assert.ok(html.includes("YouTube Packaging &amp; ComfyUI Thumbnail Studio") || html.includes("YouTube Packaging & ComfyUI Thumbnail Studio"));
  assert.ok(html.includes("ComfyUI Thumbnail Studio"));
  assert.ok(html.includes("YouTube Title, Description &amp; Tags") || html.includes("YouTube Title, Description & Tags"));
});

test("YouTube packaging interactive modal loads research, toggles aspect ratios, and generates ComfyUI thumbnails", async () => {
  const { JSDOM } = createRequire(import.meta.url)("jsdom");
  const dom = new JSDOM("<!doctype html><div id='root'></div>", { url: "http://localhost/", pretendToBeVisual: true });
  const keys = ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "HTMLTextAreaElement", "HTMLSelectElement", "IS_REACT_ACT_ENVIRONMENT"];
  const previous = new Map(keys.map(k => [k, Object.getOwnPropertyDescriptor(globalThis, k)]));
  for (const k of keys) Object.defineProperty(globalThis, k, { configurable: true, writable: true, value: k === "IS_REACT_ACT_ENVIRONMENT" ? true : dom.window[k] });

  // Mock clipboard
  let clipboardText = "";
  (dom.window.navigator as any).clipboard = {
    writeText: async (text: string) => { clipboardText = text; },
  };

  // Mock API methods
  const origGetPackaging = api.getYoutubePackaging;
  const origListWorkflows = api.listApprovedComfyWorkflows;
  const origListAssets = api.listGeneratedAssets;
  const origGenComfy = api.generateComfyImage;
  const origWaitJob = api.waitForWorkflowJob;

  let comfyJobTriggered = false;
  let requestedDims = { width: 0, height: 0 };

  api.getYoutubePackaging = async () => mockPackaging;
  api.listApprovedComfyWorkflows = async () => ({
    workflows: [
      { id: "manga_image_generation", purpose: "text_to_image", filename: "manga.json", sha256: "abc", available: true, model_files: [] },
    ],
    errors: [],
  });
  api.listGeneratedAssets = async () => ({ assets: [] });
  api.generateComfyImage = async (_pid, req) => {
    comfyJobTriggered = true;
    requestedDims = { width: req.width ?? 0, height: req.height ?? 0 };
    return { job_id: "comfy_job_123", status: "QUEUED", workflow_id: req.workflow_id || "manga_image_generation" };
  };
  api.waitForWorkflowJob = async () => ({
    job_id: "comfy_job_123",
    status: "COMPLETE",
    progress: 1.0,
    created_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
  } as any);

  try {
    const { createRoot } = await import("react-dom/client");
    const container = dom.window.document.getElementById("root")!;
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <YouTubePackagingModal
          isOpen={true}
          onClose={() => {}}
          project={project}
          profileName="standard_1080p"
        />
      );
    });

    // Verify initial values loaded
    const promptTextarea = container.querySelector("textarea") as HTMLTextAreaElement;
    assert.ok(promptTextarea);
    assert.ok(promptTextarea.value.includes("Lin Xia"));

    // Switch aspect ratio to 9:16 Shorts
    const shortsButton = Array.from(container.querySelectorAll("button")).find(
      (b: any) => b.textContent.includes("9:16 Vertical")
    ) as HTMLButtonElement;
    assert.ok(shortsButton);
    await act(async () => { shortsButton.click(); });

    // Click "Generate Thumbnail with ComfyUI"
    const generateBtn = Array.from(container.querySelectorAll("button")).find(
      (b: any) => b.textContent.includes("Generate Thumbnail with ComfyUI")
    ) as HTMLButtonElement;
    assert.ok(generateBtn);
    await act(async () => { generateBtn.click(); });

    assert.equal(comfyJobTriggered, true);
    assert.equal(requestedDims.width, 720);
    assert.equal(requestedDims.height, 1280);

    // Switch to YouTube Metadata Tab
    const metadataTabBtn = Array.from(container.querySelectorAll("button")).find(
      (b: any) => b.textContent.includes("YouTube Title, Description & Tags")
    ) as HTMLButtonElement;
    assert.ok(metadataTabBtn);
    await act(async () => { metadataTabBtn.click(); });

    // Check title options and tags are present
    const content = container.textContent || "";
    assert.ok(content.includes("He Awakened The Forbidden Power"));
    assert.ok(content.includes("00:00 - Prologue"));
    assert.ok(content.includes("motion comic"));

    // Copy title button
    const copyTitleBtn = Array.from(container.querySelectorAll("button")).find(
      (b: any) => b.textContent.includes("Copy Selected Title")
    ) as HTMLButtonElement;
    assert.ok(copyTitleBtn);
    await act(async () => { copyTitleBtn.click(); });
    assert.ok(clipboardText.includes("He Awakened The Forbidden Power"));

    await act(async () => { root.unmount(); });
  } finally {
    api.getYoutubePackaging = origGetPackaging;
    api.listApprovedComfyWorkflows = origListWorkflows;
    api.listGeneratedAssets = origListAssets;
    api.generateComfyImage = origGenComfy;
    api.waitForWorkflowJob = origWaitJob;

    for (const [k, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, k, descriptor);
      else delete (globalThis as any)[k];
    }
    dom.window.close();
  }
});
