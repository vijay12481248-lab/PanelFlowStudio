import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Project } from "@panelflow/shared-types";
import { AutoPilotModal } from "../AutoPilotModal";

const mockProject: Project = {
  id: "proj_autopilot_test",
  title: "Magic Emperor - Chapter 924",
  source_type: "MANGA",
  rights_status: "AUTHORIZED_WEB",
  workspace_path: "C:/workspaces/proj_autopilot_test",
  current_stage: "NEW",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

test("AutoPilot modal is inert when closed and renders structure when open", () => {
  const closedMarkup = renderToStaticMarkup(
    <AutoPilotModal
      isOpen={false}
      onClose={() => {}}
      project={mockProject}
    />
  );
  assert.equal(closedMarkup, "", "Should render nothing when closed");

  const openMarkup = renderToStaticMarkup(
    <AutoPilotModal
      isOpen={true}
      onClose={() => {}}
      project={mockProject}
    />
  );

  assert.ok(openMarkup.includes("1-Click End-to-End Pipeline Auto-Pilot"), "Should contain header title");
  assert.ok(openMarkup.includes("Magic Emperor - Chapter 924"), "Should display project title");
  assert.ok(openMarkup.includes("Pipeline Stages Execution"), "Should display stages execution column");
  assert.ok(openMarkup.includes("Live Orchestration Console"), "Should display live console");

  // Verify all 9 stages are present
  assert.ok(openMarkup.includes("1. Page Ingest &amp; Normalization") || openMarkup.includes("Page Ingest"), "Stage 1 present");
  assert.ok(openMarkup.includes("2. Panel Segmentation &amp; Ordering") || openMarkup.includes("Panel Segmentation"), "Stage 2 present");
  assert.ok(openMarkup.includes("3. Speech Bubble &amp; Text Extraction") || openMarkup.includes("Speech Bubble"), "Stage 3 present");
  assert.ok(openMarkup.includes("4. Narrative &amp; Scene Breakdown") || openMarkup.includes("Narrative"), "Stage 4 present");
  assert.ok(openMarkup.includes("5. Script &amp; Dialogue Adaptation") || openMarkup.includes("Script"), "Stage 5 present");
  assert.ok(openMarkup.includes("6. Master Audio &amp; Voice Synthesis") || openMarkup.includes("Master Audio"), "Stage 6 present");
  assert.ok(openMarkup.includes("7. Motion Director Keyframing") || openMarkup.includes("Motion Director"), "Stage 7 present");
  assert.ok(openMarkup.includes("8. Production Video Rendering (MP4)") || openMarkup.includes("Production Video"), "Stage 8 present");
  assert.ok(openMarkup.includes("9. YouTube Packaging &amp; AI Thumbnail") || openMarkup.includes("YouTube Packaging"), "Stage 9 present");

  // Verify Action Buttons & Controls
  assert.ok(openMarkup.includes("Start Auto-Pilot Run"), "Should have start button");
  assert.ok(openMarkup.includes("Smart Skip (Preserve existing verified stages)"), "Should have smart skip checkbox");
  assert.ok(openMarkup.includes("Generate ComfyUI Thumbnail &amp; YouTube Packaging"), "Should have packaging checkbox");
});
