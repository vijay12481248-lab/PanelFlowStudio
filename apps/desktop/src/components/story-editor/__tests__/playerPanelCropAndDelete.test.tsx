import React from "react";
import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { VideoCompositionCanvas } from "../VideoCompositionCanvas";
import { StoryEditorTimeline } from "../StoryEditorTimeline";
import { ContextualInspector } from "../ContextualInspector";
import type { StoryEditorState, VideoScene, VisualLayer } from "@panelflow/shared-types";

const mockScene: VideoScene = {
  id: "scene-1",
  sequence: 1,
  title: "Scene 1 — Panel #1",
  duration_sec: 4.0,
  start_time_sec: 0,
  transition_in: "none",
  layers: [
    {
      id: "layer-1",
      source_page_id: "page-1",
      source_panel_id: "panel-123",
      image_url: "/api/projects/test-proj/pages/page-1/file", // unmigrated page url
      crop_filename: "panel_0001.png",
      page_sequence: 1,
      crop: { x: 10, y: 20, width: 400, height: 300 },
      transform: { x: 0, y: 0, scale: 1.0, rotation: 0, opacity: 1.0, z_index: 1 },
      clip_path: "polygon(0% 0%, 100% 0%, 100% 70%, 0% 100%)",
      polygon_points: [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 70 }, { x: 0, y: 100 }],
      name: "Panel #1",
    },
  ],
};

const mockState: StoryEditorState = {
  schema_version: 2,
  project_id: "test-proj",
  scenes: [mockScene],
  narration_chapter: null,
  narration_clips: [],
  bgm_tracks: [],
  sfx_cues: [],
  selected_object: { type: "layer", id: "layer-1", sceneId: "scene-1" },
  playhead_sec: 0,
  is_playing: false,
  viewport: { width: 1920, height: 1080 },
  snapping: true,
  ripple_edit: true,
};

test("VideoCompositionCanvas resolves panel crop URL instead of full page when source_panel_id exists", () => {
  const html = renderToStaticMarkup(
    <VideoCompositionCanvas
      previewOnly
      projectId="test-proj"
      state={mockState}
      onUpdateState={() => {}}
      onSelectLayer={() => {}}
    />
  );

  // Must render panel crop endpoint, NOT full page
  assert.match(html, /\/api\/projects\/test-proj\/panels\/panel-123\/file\?v=panel_0001\.png/);
  assert.doesNotMatch(html, /\/pages\/page-1\/file/);
  // Polygon clip-path must be applied
  assert.match(html, /clip-path:polygon\(0% 0%, 100% 0%, 100% 70%, 0% 100%\)/);
});

test("StoryEditorTimeline renders delete buttons on scene and layer clips, and resolves panel thumbnail", () => {
  let deletedSceneId = "";
  let deletedLayerInfo: { layerId: string; sceneId: string } | null = null;

  const html = renderToStaticMarkup(
    <StoryEditorTimeline
      projectId="test-proj"
      state={mockState}
      onUpdateState={() => {}}
      onSelectScene={() => {}}
      onSelectLayer={() => {}}
      onAddBlankScene={() => {}}
      onSplitScene={() => {}}
      onDuplicateScene={() => {}}
      onDeleteScene={(id) => { deletedSceneId = id; }}
      onDeleteLayer={(lid, sid) => { deletedLayerInfo = { layerId: lid, sceneId: sid }; }}
    />
  );

  // Scene clip delete button
  assert.match(html, /aria-label="Delete Scene 1 — Panel #1"/);
  assert.match(html, /title="Delete Scene 1 — Panel #1 from timeline \(Del\)"/);

  // Layer clip delete button
  assert.match(html, /aria-label="Delete layer Panel #1"/);

  // Toolbar delete button
  assert.match(html, /aria-label="Delete Selected Clip \(Del\)"/);

  // Filmstrip thumbnails must point to panel crop, not full page
  assert.match(html, /\/api\/projects\/test-proj\/panels\/panel-123\/file/);
});

test("ContextualInspector renders Remove Panel from Timeline and Delete Scene buttons with panel crop preview", () => {
  let deletedLayerSceneId: string = "";
  let deletedSceneId: string = "";

  const html = renderToStaticMarkup(
    <ContextualInspector
      projectId="test-proj"
      state={mockState}
      onUpdateState={() => {}}
      onDeleteLayer={(_, sid) => { deletedLayerSceneId = sid; }}
      onDeleteScene={(sid) => { deletedSceneId = sid; }}
      activeTab="image"
    />
  );

  // Header delete button
  assert.match(html, /aria-label="Delete panel from timeline"/);

  // Remove Panel from Timeline button in Image tab
  assert.match(html, /Remove Panel from Timeline/);

  // Inspector thumbnail must resolve to panel crop URL
  assert.match(html, /\/api\/projects\/test-proj\/panels\/panel-123\/file/);
});
