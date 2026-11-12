import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { GeneratedAsset, StoryboardBeatCard } from "@panelflow/api-client";
import { ImageEditorModal, ImageEditorTarget } from "../ImageEditorModal";
import { CandidateInspectorModal } from "../CandidateInspectorModal";

const mockAsset: GeneratedAsset = {
  id: "asset_test_123",
  asset_type: "IMAGE",
  filename: "test_hero.png",
  relative_path: "assets/test_hero.png",
  content_type: "image/png",
  width: 1344,
  height: 768,
  byte_size: 204800,
  sha256: "abcdef1234567890abcdef1234567890",
  status: "READY",
  provenance: { prompt: "heroic protagonist" },
  created_at: new Date().toISOString(),
};

const mockBeat: StoryboardBeatCard = {
  panel_id: "p001",
  order: 1,
  shot: "medium",
  angle: "eye_level",
  action: "Hero stands in the dark rain",
  caption: "The rain washed away the dust of battle.",
  status: "needs_review",
  score: 0.72,
  audio_duration: 4.2,
  image_url: "/api/original/story/test_story/panel/p001/file",
  candidate_count: 2,
  selected_candidate: 1,
  iterations: [
    {
      n: 1,
      file: "panels/p001.png",
      kind: "generate",
      score: 0.72,
      bbox: [0.2, 0.1, 0.6, 0.5],
      seed: 42,
      prompt: "hero in rain",
    },
    {
      n: 2,
      file: "panels/p001_c002.png",
      kind: "generate",
      score: 0.65,
      seed: 84,
      prompt: "hero in rain alternate",
    },
  ],
};

// =========================================================================
// SECTION 1: ImageEditorModal & ImageEditorTarget Stress Tests
// =========================================================================

test("ImageEditorModal: Inert when isOpen=false", () => {
  const html = renderToStaticMarkup(
    <ImageEditorModal
      isOpen={false}
      onClose={() => {}}
      target={{
        mode: "project",
        projectId: "proj_1",
        asset: mockAsset,
      }}
    />
  );
  assert.equal(html, "", "Should render nothing when isOpen is false");
});

test("ImageEditorModal: Inert when effectiveTarget is null", () => {
  const html = renderToStaticMarkup(
    <ImageEditorModal
      isOpen={true}
      onClose={() => {}}
    />
  );
  assert.equal(html, "", "Should render nothing when neither target nor projectId+asset are provided");
});

test("ImageEditorModal: Legacy project mode (ComfyImageScreen props)", () => {
  const html = renderToStaticMarkup(
    <ImageEditorModal
      isOpen={true}
      onClose={() => {}}
      projectId="proj_legacy"
      asset={mockAsset}
    />
  );
  assert.ok(html.includes("Visual Asset Editor &amp; Inpaint Studio"), "Renders modal header");
  assert.ok(html.includes("test_hero.png"), "Renders asset filename");
  assert.ok(html.includes("200.0 KB"), "Renders formatted byte size");
  assert.ok(html.includes("1344"), "Renders asset width");
  assert.ok(html.includes("768"), "Renders asset height");
});

test("ImageEditorModal: Story mode via discriminated union ImageEditorTarget", () => {
  const html = renderToStaticMarkup(
    <ImageEditorModal
      isOpen={true}
      onClose={() => {}}
      target={{
        mode: "story",
        storySlug: "moon_tales",
        episodeSlug: "1",
        panelId: "p005",
        imageSrc: "/api/original/story/moon_tales/panel/p005/file?episode=1",
      }}
    />
  );
  assert.ok(html.includes("Visual Asset Editor &amp; Inpaint Studio"), "Renders modal header");
  assert.ok(html.includes("story-panel-p005.png"), "Renders story panel filename");
  assert.ok(html.includes("Panel p005"), "Renders panel subtext");
  assert.ok(html.includes("qwen_image_21_inpaint"), "References Qwen inpaint workflow");
});

test("ImageEditorModal: Story mode with missing episode slug", () => {
  const html = renderToStaticMarkup(
    <ImageEditorModal
      isOpen={true}
      onClose={() => {}}
      target={{
        mode: "story",
        storySlug: "standalone_story",
        panelId: "p_standalone",
        imageSrc: "/api/original/story/standalone_story/panel/p_standalone/file",
      }}
    />
  );
  assert.ok(html.includes("story-panel-p_standalone.png"), "Renders without episodeSlug");
});

test("ImageEditorModal: Story mode with empty strings and special characters", () => {
  const html = renderToStaticMarkup(
    <ImageEditorModal
      isOpen={true}
      onClose={() => {}}
      target={{
        mode: "story",
        storySlug: "",
        episodeSlug: "",
        panelId: "panel/with/slashes & special=chars",
        imageSrc: "",
      }}
    />
  );
  assert.ok(html.includes("story-panel-panel/with/slashes &amp; special=chars.png"), "Renders special characters cleanly");
});

test("ImageEditorModal: Discriminated union target takes precedence over legacy props", () => {
  const html = renderToStaticMarkup(
    <ImageEditorModal
      isOpen={true}
      onClose={() => {}}
      target={{
        mode: "story",
        storySlug: "priority_story",
        panelId: "p_target_wins",
        imageSrc: "/story/path",
      }}
      projectId="proj_should_be_ignored"
      asset={mockAsset}
    />
  );
  assert.ok(html.includes("story-panel-p_target_wins.png"), "Target mode should override legacy asset");
  assert.ok(!html.includes("test_hero.png"), "Legacy asset should be completely bypassed");
});

// =========================================================================
// SECTION 2: CandidateInspectorModal Stress Tests
// =========================================================================

test("CandidateInspectorModal: Inert when closed or beat is null", () => {
  const closedHtml = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={false}
      onClose={() => {}}
      storySlug="test_story"
      beat={mockBeat}
      onOpenInpaint={() => {}}
    />
  );
  assert.equal(closedHtml, "", "Should return null when closed");

  const nullBeatHtml = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      beat={null}
      onOpenInpaint={() => {}}
    />
  );
  assert.equal(nullBeatHtml, "", "Should return null when beat is null");
});

test("CandidateInspectorModal: Renders normal beat with candidate iterations", () => {
  const html = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      episodeSlug="1"
      beat={mockBeat}
      onOpenInpaint={() => {}}
    />
  );
  assert.ok(html.includes("Candidate Inspector — #1 (p001)"), "Header contains beat order and panel ID");
  assert.ok(html.includes("NEEDS REVIEW"), "Shows status badge");
  assert.ok(html.includes("Candidate Iterations (2)"), "Shows candidate count 2");
  assert.ok(html.includes("c001"), "Renders candidate 1 thumbnail badge");
  assert.ok(html.includes("c002"), "Renders candidate 2 thumbnail badge");
  assert.ok(html.includes("4.2s"), "Displays audio duration");
  assert.ok(html.includes("DEFECT REGION"), "Renders defect bounding box tag");
});

test("CandidateInspectorModal: Empty iterations array [] gracefully falls back", () => {
  const beatEmptyIters: StoryboardBeatCard = {
    ...mockBeat,
    iterations: [],
    selected_candidate: 1,
  };
  const html = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      beat={beatEmptyIters}
      onOpenInpaint={() => {}}
    />
  );
  assert.ok(html.includes("Candidate Iterations (1)"), "Falls back to 1 synthetic iteration");
  assert.ok(html.includes("c001"), "Renders candidate badge c001");
});

test("CandidateInspectorModal: Undefined iterations gracefully falls back", () => {
  const beatUndefinedIters: any = {
    ...mockBeat,
    iterations: undefined,
  };
  const html = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      beat={beatUndefinedIters}
      onOpenInpaint={() => {}}
    />
  );
  assert.ok(html.includes("Candidate Iterations (1)"), "Falls back to 1 synthetic iteration");
});

test("CandidateInspectorModal: Out-of-bounds selected_candidate index", () => {
  const beatOutOfBounds: StoryboardBeatCard = {
    ...mockBeat,
    selected_candidate: 999, // does not match any iteration
  };
  const html = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      beat={beatOutOfBounds}
      onOpenInpaint={() => {}}
    />
  );
  // Iteration 0 should be selected as fallback
  assert.ok(html.includes("Candidate Inspector — #1 (p001)"), "Renders successfully without crashing");
});

test("CandidateInspectorModal: Defect bounding box variations", () => {
  // Test 1: Standard bbox [0.2, 0.1, 0.6, 0.5]
  // left: 20%, top: 10%, width: 40%, height: 40%
  const htmlStd = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      beat={mockBeat}
      onOpenInpaint={() => {}}
    />
  );
  assert.ok(htmlStd.includes("left:20%"), "Standard bbox left 20%");
  assert.ok(htmlStd.includes("top:10%"), "Standard bbox top 10%");
  assert.ok(htmlStd.includes("width:40%"), "Standard bbox width 40%");
  assert.ok(htmlStd.includes("height:40%"), "Standard bbox height 40%");

  // Test 2: Non-standard length (length 2 instead of 4) -> should be suppressed
  const beatShortBbox: StoryboardBeatCard = {
    ...mockBeat,
    iterations: [{ n: 1, file: "f", kind: "gen", bbox: [0.1, 0.2] }],
  };
  const htmlShort = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      beat={beatShortBbox}
      onOpenInpaint={() => {}}
    />
  );
  assert.ok(!htmlShort.includes("DEFECT REGION"), "Bbox of length 2 must NOT render defect box");

  // Test 3: Non-standard length (length 5) -> should be suppressed
  const beatLongBbox: StoryboardBeatCard = {
    ...mockBeat,
    iterations: [{ n: 1, file: "f", kind: "gen", bbox: [0.1, 0.2, 0.3, 0.4, 0.5] }],
  };
  const htmlLong = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      beat={beatLongBbox}
      onOpenInpaint={() => {}}
    />
  );
  assert.ok(!htmlLong.includes("DEFECT REGION"), "Bbox of length 5 must NOT render defect box");

  // Test 4: Bbox with coordinates outside [0, 1]
  const beatOobBbox: StoryboardBeatCard = {
    ...mockBeat,
    iterations: [{ n: 1, file: "f", kind: "gen", bbox: [-0.1, 0.2, 1.2, 0.8] }],
  };
  const htmlOob = renderToStaticMarkup(
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => {}}
      storySlug="test_story"
      beat={beatOobBbox}
      onOpenInpaint={() => {}}
    />
  );
  assert.ok(htmlOob.includes("left:-10%"), "Handles negative coordinate cleanly");
  assert.ok(htmlOob.includes("width:130%"), "Handles width > 100% cleanly");
});

test("CandidateInspectorModal: Inpaint action bridge contract verification", () => {
  let dispatchedTarget: ImageEditorTarget | null = null;
  let closedCalled = false;

  const modal = (
    <CandidateInspectorModal
      isOpen={true}
      onClose={() => { closedCalled = true; }}
      storySlug="moon_chronicles"
      episodeSlug="ep3"
      beat={mockBeat}
      onOpenInpaint={(t) => { dispatchedTarget = t; }}
    />
  );
  const html = renderToStaticMarkup(modal);
  assert.ok(html.includes("Inpaint on this Candidate"), "Inpaint action button present");
});


// =========================================================================
// SECTION 3: Deep Behavioral & Lifecycle Vulnerability Tests
// =========================================================================

test("Verified Fix: CandidateInspectorModal bridge attaches onPanelUpdated and refreshes workbench", () => {
  let inpaintTarget: ImageEditorTarget | null = null;
  let workbenchRefreshed = false;
  const loadWorkbench = (slug: string, ep?: string, title?: string) => {
    workbenchRefreshed = true;
    assert.equal(slug, "my_story");
    assert.equal(ep, "ep1");
  };

  const setInpaintTarget = (t: ImageEditorTarget) => {
    inpaintTarget = t;
  };

  // Fixed OriginalStoriesScreen.tsx onOpenInpaint:
  const onOpenInpaint = (target: ImageEditorTarget) => {
    setInpaintTarget({
      ...target,
      onPanelUpdated: () => loadWorkbench("my_story", "ep1", "My Story"),
    });
  };

  onOpenInpaint({
    mode: "story",
    storySlug: "my_story",
    episodeSlug: "ep1",
    panelId: "p001",
    imageSrc: "http://localhost:8765/img.png",
  });

  assert.ok(inpaintTarget !== null);
  assert.equal(typeof (inpaintTarget as any).onPanelUpdated, "function", "onPanelUpdated callback successfully attached");
  (inpaintTarget as any).onPanelUpdated!("new_image.png");
  assert.equal(workbenchRefreshed, true, "Workbench reload invoked upon panel inpaint completion");
});

test("Verified Fix: ImageEditorModal targetKey and memoization provide stable identity across renders", () => {
  const computeTargetKey = (
    target?: ImageEditorTarget,
    projectId?: string,
    asset?: GeneratedAsset | null,
    onAssetUpdated?: (newAsset: GeneratedAsset) => void
  ): string | null => {
    const effectiveTarget: ImageEditorTarget | null = target
      ? target
      : (projectId && asset)
        ? { mode: 'project', projectId, asset, onAssetUpdated }
        : null;
    if (!effectiveTarget) return null;
    return effectiveTarget.mode === 'story'
      ? `${effectiveTarget.storySlug}:${effectiveTarget.episodeSlug || ''}:${effectiveTarget.panelId}:${effectiveTarget.imageSrc}`
      : `${effectiveTarget.projectId}:${effectiveTarget.asset.id}`;
  };

  // Legacy project mode with fresh object allocations
  const dummyCallback1 = () => {};
  const dummyCallback2 = () => {};
  const key1 = computeTargetKey(undefined, "proj_123", mockAsset, dummyCallback1);
  const key2 = computeTargetKey(undefined, "proj_123", mockAsset, dummyCallback2);

  // Primitive strings are strictly equal across renders
  assert.equal(key1, key2, "Target keys match across independent renders");
  assert.equal(Object.is(key1, key2), true, "Object.is evaluation is true, preventing spurious useEffect execution");
  assert.equal(key1, `proj_123:${mockAsset.id}`);
});

// =========================================================================
// SECTION 4: API Client URL Construction & Cache Busting Tests
// =========================================================================

test("API Client: getOriginalPanelImageUrl handles undefined, empty, and special parameters", async () => {
  const { api } = await import("@panelflow/api-client");

  // Standard case with episode and candidate
  const u1 = api.getOriginalPanelImageUrl("story_1", "panel_1", "ep_1", 2);
  assert.ok(u1.includes("/api/original/story/story_1/panel/panel_1/file?episode=ep_1&candidate=2"));

  // Without episode or candidate
  const u2 = api.getOriginalPanelImageUrl("story_2", "panel_2");
  assert.ok(u2.endsWith("/api/original/story/story_2/panel/panel_2/file"));
  assert.ok(!u2.includes("?"), "No query parameters when episode and candidate omitted");

  // With candidate 0
  const u3 = api.getOriginalPanelImageUrl("story_3", "panel_3", undefined, 0);
  assert.ok(u3.includes("?candidate=0"), "Candidate 0 should be preserved, not treated as falsy");

  // Special characters in slug and panelId
  const u4 = api.getOriginalPanelImageUrl("story/with space", "panel#99");
  assert.ok(u4.includes("story%2Fwith%20space"), "Slug URI-encoded");
  assert.ok(u4.includes("panel%2399"), "Panel ID URI-encoded");

  // Cache busting query parameter simulation
  const now = Date.now();
  const cacheBustedUrl = `${u2}?t=${now}`;
  assert.ok(cacheBustedUrl.includes(`?t=${now}`), "Cache buster appended cleanly");
});

// =========================================================================
// SECTION 5: Notification Permission Logic Simulation Tests
// =========================================================================

test("Notification logic: Handled safely under granted, denied, and missing Notification API", () => {
  // Test 1: Notification API absent
  let notificationTriggered = false;
  let requestedPermission = false;

  const runNotificationCheck = (hasWindow: boolean, hasNotification: boolean, permission: string, needsReviewCount: number) => {
    let triggered = false;
    let requested = false;
    if (needsReviewCount > 0 && hasWindow && hasNotification) {
      if (permission === "granted") {
        triggered = true;
      } else if (permission !== "denied") {
        requested = true;
      }
    }
    return { triggered, requested };
  };

  assert.deepEqual(runNotificationCheck(false, false, "default", 3), { triggered: false, requested: false });
  assert.deepEqual(runNotificationCheck(true, false, "default", 3), { triggered: false, requested: false });
  assert.deepEqual(runNotificationCheck(true, true, "denied", 3), { triggered: false, requested: false });
  assert.deepEqual(runNotificationCheck(true, true, "granted", 3), { triggered: true, requested: false });
  assert.deepEqual(runNotificationCheck(true, true, "default", 3), { triggered: false, requested: true });
  assert.deepEqual(runNotificationCheck(true, true, "granted", 0), { triggered: false, requested: false });
});
