// Isolated acceptance fixture; only used by tools/qa_setup_selectors.py.
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, PanelFlowApiClient } from "@panelflow/api-client";
import type { Panel, Page } from "@panelflow/shared-types";
import { SourceSetupCanvas } from "../src/components/story-editor/SourceSetupCanvas";
import { SourcePageBrowser } from "../src/components/story-editor/SourcePageBrowser";
import { VideoCompositionCanvas } from "../src/components/story-editor/VideoCompositionCanvas";
import { createEmptyEditorState } from "../src/components/story-editor/editorWorkspace";
import "../src/index.css";
Object.assign(api, new PanelFlowApiClient("http://127.0.0.1:5189"));
const page = { id: "page", project_id: "qa", sequence: 1, width: 800, height: 1200 } as Page;
const sourcePages = [page, { ...page, id: "page-two", sequence: 2 }];
function Fixture() {
  const [panels, setPanels] = useState<Panel[]>([]);
  const [selected, setSelected] = useState<string | null>("panel");
  const [pageId, setPageId] = useState(page.id);
  const activePage = sourcePages.find(p => p.id === pageId)!;
  const [mode, setMode] = useState("setup");
  const [state, setState] = useState(createEmptyEditorState("qa"));
  useEffect(() => { void api.listPanels("qa").then(setPanels); }, []);
  return <div className="h-screen flex flex-col bg-zinc-950 text-zinc-200">
    <header className="p-3 flex gap-3 border-b border-zinc-800"><span className="text-sm">Isolated selector acceptance</span>
      <button onClick={() => setMode("setup")}>Setup</button><button onClick={() => setMode("player")}>Player</button></header>
    <main className="flex flex-1 min-h-0">
      {mode === "setup" ? <SourceSetupCanvas projectId="qa" page={activePage} pages={sourcePages} onSelectPage={id => { setPageId(id); setSelected(null); }}
        initialView="panels" panels={panels} selectedPanelId={selected}
        onSelectPanel={p => setSelected(p.id)} onPanelSaved={() => {}} onPanelsChanged={setPanels} onAddPanel={(_page, panel) => {
          setState({ ...createEmptyEditorState("qa"), scenes: [{ id: "scene", sequence: 1, title: "Saved selector", start_time_sec: 0, duration_sec: 4, layers: [{
            id: "layer", source_panel_id: panel.id, image_url: `${api.getPanelImageUrl("qa", panel.id)}?v=${panel.crop_filename}`, crop: panel,
            name: "Saved panel", transform: { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1, z_index: 1 }, motion_preset: "none",
          }] }], selected_object: { type: "layer", id: "layer", sceneId: "scene" } }); setMode("player");
        }} /> : <VideoCompositionCanvas previewOnly state={state} onUpdateState={setState} onSelectLayer={() => {}} />}
      <aside className="w-80 shrink-0 p-2 border-l border-zinc-800"><SourcePageBrowser compact hideEditingTools projectId="qa"
        pages={sourcePages} panels={panels} selectedPageId={pageId} selectedPanelId={selected} onSelectPage={id => { setPageId(id); setMode("setup"); }}
        onSelectPanel={p => { setSelected(p?.id || null); setMode("setup"); }} onAddPanelToScene={() => {}} /></aside>
    </main>
  </div>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
