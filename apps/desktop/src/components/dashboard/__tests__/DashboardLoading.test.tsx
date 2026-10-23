import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ProjectsWorkspace } from "../ProjectsWorkspace";

const props = {
  projects: [], favorites: {}, onToggleFavorite: () => {}, onNewProject: () => {},
  onOpenStoryEditor: () => {}, onOpenOCR: () => {}, onOpenPanels: () => {},
  onOpenFolder: () => {}, onDeleteProject: () => {},
};

test("pending project load is not presented as an empty workspace", () => {
  const html = renderToStaticMarkup(<ProjectsWorkspace {...props} loading={true} />);
  assert.match(html, /role="status"/);
  assert.match(html, /Loading projects/);
  assert.doesNotMatch(html, /No projects in this category|Create your first project/);
});

test("project load failure offers retry instead of claiming no projects exist", () => {
  const html = renderToStaticMarkup(<ProjectsWorkspace {...props} error="Could not load projects." onRetry={() => {}} />);
  assert.match(html, /role="alert"/);
  assert.match(html, /Could not load projects/);
  assert.match(html, /Retry/);
  assert.doesNotMatch(html, /No projects in this category|Create your first project/);
});

test("successful empty project load retains the existing empty-state UI", () => {
  assert.match(renderToStaticMarkup(<ProjectsWorkspace {...props} loading={false} />), /No projects in this category/);
});
