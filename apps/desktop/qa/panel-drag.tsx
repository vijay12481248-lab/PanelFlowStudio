// Isolated fixture: no project reads or writes. Image routes are supplied by the browser check.
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import type { Page, Panel } from "@panelflow/shared-types";
import { SourcePageBrowser } from "../src/components/story-editor/SourcePageBrowser";
import { StoryEditorTimeline } from "../src/components/story-editor/StoryEditorTimeline";
import { createEmptyEditorState } from "../src/components/story-editor/editorWorkspace";
import "../src/index.css";

const page = { id: "page", project_id: "drag-qa", sequence: 1, width: 800, height: 1200 } as Page;
const panels = Array.from({ length: 4 }, (_, i) => ({ id: `panel-${i + 1}`, page_id: page.id, page_sequence: i + 1,
  x: 0, y: i * 300, width: 800, height: 300 } as Panel));
function Fixture() {
  const [state, setState] = useState(createEmptyEditorState("drag-qa"));
  const [selected, setSelected] = useState<string | null>(null);
  return <div className="h-screen flex flex-col bg-zinc-950 text-zinc-200">
    <main className="flex flex-1 min-h-0"><div className="flex-1 p-8">Panel drag acceptance — isolated fixture</div>
      <aside className="w-96 p-2"><SourcePageBrowser compact hideEditingTools activeSubTab="panels" projectId="drag-qa" pages={[page]} panels={panels}
        selectedPageId={page.id} onSelectPage={() => {}} selectedPanelId={selected} onSelectPanel={p => setSelected(p?.id || null)} onAddPanelToScene={() => {}} /></aside>
    </main>
    <div className="h-80"><StoryEditorTimeline state={state} onUpdateState={setState} projectId="drag-qa"
      onSelectScene={() => {}} onSelectLayer={() => {}} onAddBlankScene={() => {}} onSplitScene={() => {}} onDuplicateScene={() => {}} onDeleteScene={() => {}} /></div>
    <output id="qa-state" className="hidden">{JSON.stringify(state)}</output>
  </div>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
