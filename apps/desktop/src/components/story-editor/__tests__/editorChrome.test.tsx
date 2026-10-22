import React from "react";
import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryEditorTopBar } from "../StoryEditorTopBar";
import { StoryEditorLeftRail } from "../StoryEditorLeftRail";
import type { Project, StoryEditorState } from "@panelflow/shared-types";

const state = { mode: "simple", aspect_ratio: "16:9", is_playing: false } as StoryEditorState;
const props = {
  project: { title: "A real project" } as Project,
  state, onUpdateState: () => {}, canUndo: false, canRedo: true,
  onUndo: () => {}, onRedo: () => {}, onBackToDashboard: () => {},
  onExportClick: () => {}, saveStatus: "saved" as const,
  onOpenNarrationStudio: () => {}, onOpenAudioLibrary: () => {},
};

function elements(node: React.ReactNode): React.ReactElement<any>[] {
  if (!React.isValidElement(node)) return [];
  const element = node as React.ReactElement<any>;
  return [element, ...React.Children.toArray(element.props.children).flatMap(elements)];
}

test("top bar renders responsive reference chrome with accessible real controls and no invented chapter", () => {
  const html = renderToStaticMarkup(<StoryEditorTopBar {...props} />);
  assert.match(html, /min-h-\[56px\]/);
  assert.match(html, /bg-\[#0b0d15\]/);
  assert.match(html, /flex-wrap/);
  assert.doesNotMatch(html, /h-13|Chapter 01/);
  assert.match(html, /aria-label="Return to Projects Dashboard"/);
  assert.match(html, /aria-label="Undo"/);
  assert.match(html, /aria-label="Redo"/);
  assert.match(html, /aria-label="Aspect ratio"/);
  assert.match(html, /aria-pressed="true"[^>]*>Simple|aria-pressed="true"/);
  for (const label of ["A real project", "Saved", "Narration Studio", "Audio Library", "Preview", "Export"]) {
    assert.ok(html.includes(label), label);
  }
  const buttons = elements(StoryEditorTopBar(props)).filter(e => e.type === "button");
  const undo = buttons.find(e => e.props["aria-label"] === "Undo");
  const redo = buttons.find(e => e.props["aria-label"] === "Redo");
  assert.equal(undo?.props.disabled, true);
  assert.equal(redo?.props.disabled, false);
});

test("rail exposes selected navigation and truthful tri-state engine status", () => {
  for (const [engineConnected, label] of [[true, "Healthy"], [false, "Offline"], [undefined, "Checking"]] as const) {
    const html = renderToStaticMarkup(<StoryEditorLeftRail activeTab="story" onSelectTab={() => {}} engineConnected={engineConnected} />);
    assert.match(html, /aria-label="Editor workspaces"/);
    assert.match(html, /w-\[72px\]/);
    assert.match(html, /lg:w-\[100px\]/);
    assert.match(html, /aria-pressed="true"/);
    assert.match(html, /role="status"/);
    assert.ok(html.includes(label));
    if (engineConnected !== true) assert.ok(!html.includes("Healthy"));
    for (const tab of ["Pages", "Story", "Voice", "Motion", "Audio", "Settings"]) assert.ok(html.includes(tab));
  }
  const defaultHtml = renderToStaticMarkup(<StoryEditorLeftRail activeTab="pages" onSelectTab={() => {}} />);
  assert.ok(defaultHtml.includes("Checking"));
  assert.ok(!defaultHtml.includes("Healthy"));
});

test("top bar callbacks and functional state updaters preserve editor state", () => {
  let current = { ...state, marker: "preserved" };
  const calls: string[] = [];
  const tree = StoryEditorTopBar({
    ...props, canUndo: true,
    onUpdateState: updater => { current = updater(current) as typeof current; },
    onUndo: () => calls.push("undo"), onRedo: () => calls.push("redo"),
    onBackToDashboard: () => calls.push("dashboard"), onExportClick: () => calls.push("export"),
    onOpenNarrationStudio: () => calls.push("narration"), onOpenAudioLibrary: () => calls.push("audio"),
  });
  const nodes = elements(tree);
  const button = (label: string) => nodes.find(e => e.type === "button" && (e.props["aria-label"] === label || renderToStaticMarkup(e).replace(/<[^>]+>/g, "").trim() === label))!;
  button("Advanced").props.onClick();
  assert.equal(current.mode, "advanced");
  button("Simple").props.onClick();
  assert.equal(current.mode, "simple");
  nodes.find(e => e.type === "select")!.props.onChange({ target: { value: "9:16" } });
  assert.equal(current.aspect_ratio, "9:16");
  button("Preview").props.onClick();
  assert.equal(current.is_playing, true);
  button("Preview").props.onClick();
  assert.equal(current.is_playing, false);
  assert.equal(current.marker, "preserved");
  for (const label of ["Undo", "Redo", "Return to Projects Dashboard", "Narration Studio", "Audio Library", "Export"]) button(label).props.onClick();
  assert.deepEqual(calls, ["undo", "redo", "dashboard", "narration", "audio", "export"]);
});

test("each rail button forwards the existing tab identifier", () => {
  const selected: string[] = [];
  const tree = StoryEditorLeftRail({ activeTab: "story", onSelectTab: tab => selected.push(tab) });
  const buttons = elements(tree).filter(e => e.type === "button");
  assert.equal(buttons.length, 6);
  assert.equal(buttons.filter(e => e.props["aria-pressed"]).length, 1);
  for (const button of buttons) button.props.onClick();
  assert.deepEqual(selected, ["pages", "story", "narration", "motion", "audio", "settings"]);
});

test("save state and playback state remain live; optional launchers stay optional", () => {
  for (const [saveStatus, label] of [["saved", "Saved"], ["saving", "Saving..."], ["unsaved", "Unsaved"]] as const) {
    const html = renderToStaticMarkup(<StoryEditorTopBar {...props} saveStatus={saveStatus} state={{ ...state, mode: "advanced", is_playing: true }} onOpenNarrationStudio={undefined} onOpenAudioLibrary={undefined} />);
    assert.ok(html.includes(label));
    assert.match(html, /aria-label="Pause preview" aria-pressed="true"/);
    assert.doesNotMatch(html, /Narration Studio|Audio Library/);
    const modes = elements(StoryEditorTopBar({ ...props, state: { ...state, mode: "advanced" } })).filter(e => e.type === "button" && typeof e.props.children === "string" && ["Simple", "Advanced"].includes(e.props.children.trim()));
    assert.deepEqual(modes.map(e => e.props["aria-pressed"]), [false, true]);
  }
});
