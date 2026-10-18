import React, { useState, useRef } from "react";
import { Icons, Button, Badge } from "@panelflow/ui";
import type { Page, Panel } from "@panelflow/shared-types";
import { api } from "@panelflow/api-client";

interface SourcePageBrowserProps {
  projectId: string;
  pages: Page[];
  panels: Panel[];
  selectedPageId: string | null;
  onSelectPage: (pageId: string) => void;
  selectedPanelId: string | null;
  onSelectPanel: (panel: Panel | null) => void;
  onAddPanelToScene: (
    page: Page,
    panel: Panel | null,
    customCrop?: { x: number; y: number; width: number; height: number },
    asNewScene?: boolean
  ) => void;
  onClose?: () => void;
  activeSubTab?: "pages" | "panels";
  onSubTabChange?: (tab: "pages" | "panels") => void;
}

export const SourcePageBrowser: React.FC<SourcePageBrowserProps> = ({
  projectId,
  pages,
  panels,
  selectedPageId,
  onSelectPage,
  selectedPanelId,
  onSelectPanel,
  onAddPanelToScene,
  onClose,
  activeSubTab: externalSubTab,
  onSubTabChange,
}) => {
  const [internalSubTab, setInternalSubTab] = useState<"pages" | "panels">("pages");
  const subTab = externalSubTab ?? internalSubTab;
  const setSubTab = (tab: "pages" | "panels") => {
    setInternalSubTab(tab);
    onSubTabChange?.(tab);
  };
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [toolMode, setToolMode] = useState<"select" | "crop" | "pan">("select");
  const [isDrawing, setIsDrawing] = useState<boolean>(false);
  const [drawBox, setDrawBox] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const imageContainerRef = useRef<HTMLDivElement>(null);

  const activePageIndex = pages.findIndex((p) => p.id === selectedPageId);
  const activePage = pages[activePageIndex >= 0 ? activePageIndex : 0] || null;

  // Filter panels for active page
  const pagePanels = activePage
    ? panels.filter((p) => p.page_id === activePage.id).sort((a, b) => a.page_sequence - b.page_sequence)
    : [];

  const activeSelectedPanel =
    pagePanels.find((p) => p.id === selectedPanelId) ||
    (pagePanels.length > 0 ? pagePanels[0] : null);

  const handlePrevPage = () => {
    if (activePageIndex > 0) {
      onSelectPage(pages[activePageIndex - 1].id);
      onSelectPanel(null);
      setDrawBox(null);
    }
  };

  const handleNextPage = () => {
    if (activePageIndex < pages.length - 1) {
      onSelectPage(pages[activePageIndex + 1].id);
      onSelectPanel(null);
      setDrawBox(null);
    }
  };

  // Chapter 3: Drag panel onto composition canvas or timeline
  const handlePanelDragStart = (e: React.DragEvent, panel: Panel) => {
    if (!activePage) return;
    const payload = {
      pageId: activePage.id,
      panelId: panel.id,
      pageSequence: panel.page_sequence,
      crop: { x: panel.x, y: panel.y, width: panel.width, height: panel.height },
      imageUrl: api.getPageImageUrl(projectId, activePage.id),
      name: `Panel #${panel.page_sequence}`,
    };
    e.dataTransfer.setData("application/panelflow-panel", JSON.stringify(payload));
    e.dataTransfer.effectAllowed = "copy";
  };

  // Freeform Draw Handlers on SVG
  const handleSvgMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!activePage || toolMode === "pan") return;
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const clickX = ((e.clientX - rect.left) / rect.width) * (activePage.width || 1200);
    const clickY = ((e.clientY - rect.top) / rect.height) * (activePage.height || 1800);

    setIsDrawing(true);
    setDrawBox({ x: clickX, y: clickY, w: 0, h: 0 });
    onSelectPanel(null);
  };

  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDrawing || !drawBox || !activePage) return;
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const currentX = ((e.clientX - rect.left) / rect.width) * (activePage.width || 1200);
    const currentY = ((e.clientY - rect.top) / rect.height) * (activePage.height || 1800);

    setDrawBox((prev) => {
      if (!prev) return null;
      return {
        x: Math.min(prev.x, currentX),
        y: Math.min(prev.y, currentY),
        w: Math.abs(currentX - prev.x),
        h: Math.abs(currentY - prev.y),
      };
    });
  };

  const handleSvgMouseUp = () => {
    setIsDrawing(false);
  };

  // Distinct bounding box border colors matching the screenshot
  const panelColors = [
    { border: "#38bdf8", fill: "rgba(56, 189, 248, 0.12)" }, // cyan
    { border: "#f87171", fill: "rgba(248, 113, 113, 0.12)" }, // red
    { border: "#c084fc", fill: "rgba(192, 132, 252, 0.12)" }, // purple
    { border: "#4ade80", fill: "rgba(74, 222, 128, 0.12)" }, // green
    { border: "#fbbf24", fill: "rgba(251, 191, 36, 0.12)" }, // amber
  ];

  return (
    <div className="h-full flex flex-col bg-zinc-900 border-l border-zinc-800 select-none overflow-hidden">
      {/* Top Header: Source Pages title, page counter, and sub-tabs */}
      <div className="p-2.5 border-b border-zinc-800 bg-zinc-950/70 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
            Source Pages
          </span>
          <span className="text-[11px] font-mono text-zinc-400">
            {activePageIndex + 1} / {pages.length || 1}
          </span>
        </div>

        {/* Sub-tabs: Pages | Panels and Page Pager */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-zinc-900 rounded p-0.5 border border-zinc-800">
            <button
              type="button"
              onClick={() => setSubTab("pages")}
              className={`px-2 py-0.5 text-[11px] font-semibold rounded ${
                subTab === "pages"
                  ? "bg-indigo-600 text-white"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Pages
            </button>
            <button
              type="button"
              onClick={() => setSubTab("panels")}
              className={`px-2 py-0.5 text-[11px] font-semibold rounded ${
                subTab === "panels"
                  ? "bg-indigo-600 text-white"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Panels
            </button>
          </div>

          <div className="flex items-center gap-0.5 bg-zinc-950 border border-zinc-800 rounded px-1">
            <button
              type="button"
              onClick={handlePrevPage}
              disabled={activePageIndex <= 0}
              className="p-1 text-zinc-400 hover:text-white disabled:opacity-30"
              title="Previous Page"
            >
              <Icons.ChevronDown className="w-3.5 h-3.5 rotate-90" />
            </button>
            <span className="text-[11px] font-mono font-bold text-zinc-200 px-1">
              {activePageIndex + 1}
            </span>
            <button
              type="button"
              onClick={handleNextPage}
              disabled={activePageIndex >= pages.length - 1}
              className="p-1 text-zinc-400 hover:text-white disabled:opacity-30"
              title="Next Page"
            >
              <Icons.ChevronDown className="w-3.5 h-3.5 -rotate-90" />
            </button>
          </div>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 text-zinc-400 hover:text-white ml-1"
              title="Close Source Panel"
            >
              <Icons.XCircle className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Main Area: Page Canvas on Left + Vertical Filmstrip on Right */}
      <div className="flex-1 flex overflow-hidden bg-zinc-950 relative">
        {subTab === "panels" && activePage ? (
          /* Draggable Panels Gallery Grid */
          <div className="flex-1 overflow-auto p-3 grid grid-cols-2 gap-3 content-start">
            {pagePanels.length > 0 ? (
              pagePanels.map((p) => {
                const isSelected = selectedPanelId === p.id;
                return (
                  <div
                    key={p.id}
                    draggable
                    onDragStart={(e) => handlePanelDragStart(e, p)}
                    onClick={() => onSelectPanel(p)}
                    className={`p-2 rounded-lg border bg-zinc-900 flex flex-col gap-1.5 cursor-grab active:cursor-grabbing transition-all select-none ${
                      isSelected
                        ? "border-indigo-500 ring-2 ring-indigo-500/40 bg-zinc-850"
                        : "border-zinc-800 hover:border-zinc-700 hover:bg-zinc-850/60"
                    }`}
                  >
                    <div className="flex items-center justify-between text-[11px] text-zinc-300 font-medium">
                      <span className="flex items-center gap-1 font-bold">
                        <span className="text-zinc-500">⠿</span>
                        Panel #{p.page_sequence}
                      </span>
                      <span className="text-[10px] font-mono text-zinc-500">
                        {Math.round(p.width)}×{Math.round(p.height)}
                      </span>
                    </div>

                    {/* Cropped thumbnail representation */}
                    <div className="relative w-full aspect-[4/3] bg-black rounded overflow-hidden border border-zinc-800 pointer-events-none">
                      <div
                        style={{
                          position: "absolute",
                          width: `${((activePage.width || 1200) / Math.max(1, p.width)) * 100}%`,
                          height: `${((activePage.height || 1800) / Math.max(1, p.height)) * 100}%`,
                          left: `-${(p.x / Math.max(1, p.width)) * 100}%`,
                          top: `-${(p.y / Math.max(1, p.height)) * 100}%`,
                        }}
                      >
                        <img
                          src={api.getPageImageUrl(projectId, activePage.id)}
                          alt={`Panel ${p.page_sequence}`}
                          className="w-full h-full object-fill"
                        />
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center justify-between gap-1 pt-1 mt-auto">
                      <span className="text-[9px] text-indigo-400 font-bold tracking-tight">
                        DRAG TO TIMELINE
                      </span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onAddPanelToScene(activePage, p, undefined, false);
                          }}
                          className="px-1.5 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] text-zinc-300"
                          title="Add as layer to active scene"
                        >
                          + Layer
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onAddPanelToScene(activePage, p, undefined, true);
                          }}
                          className="px-1.5 py-0.5 rounded bg-indigo-600 hover:bg-indigo-500 text-[10px] text-white"
                          title="Add as new scene"
                        >
                          + Scene
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="col-span-2 text-center text-zinc-500 py-12 text-xs">
                No detected panels on Page #{activePage.sequence}.
              </div>
            )}
          </div>
        ) : (
          /* Manga Page Viewer with Colored Bounding Boxes */
          <div className="flex-1 overflow-auto p-3 flex justify-center items-start">
            {activePage ? (
              <div
                ref={imageContainerRef}
                className="relative shadow-2xl rounded overflow-hidden border border-zinc-800 transition-all duration-150 mx-auto"
                style={{ width: `${zoomLevel}%` }}
              >
                <img
                  src={api.getPageImageUrl(projectId, activePage.id)}
                  alt={`Manga Page ${activePage.sequence}`}
                  className="w-full h-auto block pointer-events-none"
                />

                {/* SVG Overlay of Detected Panels & Draggable Regions */}
                <svg
                  className={`absolute inset-0 w-full h-full ${
                    toolMode === "crop" ? "cursor-crosshair" : "cursor-pointer"
                  }`}
                  viewBox={`0 0 ${activePage.width || 1200} ${activePage.height || 1800}`}
                  preserveAspectRatio="none"
                  onMouseDown={handleSvgMouseDown}
                  onMouseMove={handleSvgMouseMove}
                  onMouseUp={handleSvgMouseUp}
                >
                  {pagePanels.map((p, pIdx) => {
                    const isSelected = selectedPanelId === p.id;
                    const colorScheme = panelColors[pIdx % panelColors.length];
                    return (
                      <g
                        key={p.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectPanel(p);
                          setDrawBox(null);
                        }}
                        className="cursor-pointer group"
                      >
                        <rect
                          x={p.x}
                          y={p.y}
                          width={p.width}
                          height={p.height}
                          fill={isSelected ? "rgba(99, 102, 241, 0.3)" : colorScheme.fill}
                          stroke={isSelected ? "#ffffff" : colorScheme.border}
                          strokeWidth={isSelected ? 4 : 2}
                          className="transition-colors group-hover:fill-indigo-500/25"
                        />

                        {/* Corner Drag Handles */}
                        {isSelected && (
                          <>
                            <circle cx={p.x} cy={p.y} r={5} fill="#ffffff" stroke="#6366f1" strokeWidth={2} />
                            <circle cx={p.x + p.width} cy={p.y} r={5} fill="#ffffff" stroke="#6366f1" strokeWidth={2} />
                            <circle cx={p.x} cy={p.y + p.height} r={5} fill="#ffffff" stroke="#6366f1" strokeWidth={2} />
                            <circle cx={p.x + p.width} cy={p.y + p.height} r={5} fill="#ffffff" stroke="#6366f1" strokeWidth={2} />
                          </>
                        )}
                      </g>
                    );
                  })}

                  {/* Freeform Drawn Crop Box */}
                  {drawBox && drawBox.w > 4 && drawBox.h > 4 && (
                    <rect
                      x={drawBox.x}
                      y={drawBox.y}
                      width={drawBox.w}
                      height={drawBox.h}
                      fill="rgba(245, 158, 11, 0.25)"
                      stroke="#fbbf24"
                      strokeWidth={3}
                      strokeDasharray="4 2"
                    />
                  )}
                </svg>

                {/* Draggable chip overlay for selected panel in Page view */}
                {activeSelectedPanel && (
                  <div
                    draggable
                    onDragStart={(e) => handlePanelDragStart(e, activeSelectedPanel)}
                    style={{
                      left: `${(activeSelectedPanel.x / (activePage.width || 1200)) * 100}%`,
                      top: `${(activeSelectedPanel.y / (activePage.height || 1800)) * 100}%`,
                    }}
                    className="absolute z-20 m-1 px-2 py-0.5 rounded bg-indigo-600 text-white text-[10px] font-bold flex items-center gap-1 shadow-lg cursor-grab active:cursor-grabbing border border-indigo-400 select-none"
                    title="Drag this panel onto the Timeline or Canvas"
                  >
                    <span>⠿</span>
                    <span>Panel #{activeSelectedPanel.page_sequence} (Drag)</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-zinc-500 p-6 text-center">
                <Icons.BookOpen className="w-10 h-10 mb-2 opacity-40" />
                <p className="text-xs">No pages available</p>
              </div>
            )}
          </div>
        )}

        {/* Right Vertical Filmstrip Column (matching the screenshot) */}
        <div className="w-16 border-l border-zinc-800 bg-zinc-950 p-1.5 flex flex-col gap-2 overflow-y-auto shrink-0 select-none">
          {pages.map((page, idx) => {
            const isCurrent = page.id === activePage?.id;
            return (
              <button
                key={page.id}
                type="button"
                onClick={() => {
                  onSelectPage(page.id);
                  onSelectPanel(null);
                  setDrawBox(null);
                }}
                className={`relative w-full aspect-[2/3] rounded overflow-hidden border transition-all ${
                  isCurrent
                    ? "border-indigo-500 ring-2 ring-indigo-500/40 scale-105"
                    : "border-zinc-800 opacity-60 hover:opacity-100 hover:border-zinc-600"
                }`}
                title={`Page ${idx + 1}`}
              >
                <img
                  src={api.getPageImageUrl(projectId, page.id)}
                  alt={`Thumb ${page.sequence}`}
                  className="w-full h-full object-cover object-top"
                />
                <span className="absolute bottom-0 right-0 bg-black/80 px-1 text-[9px] font-mono text-zinc-300">
                  {idx + 1}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Bottom Toolbar: Zoom, Crop/Selection Tool, Hand Tool, and Add to Scene */}
      <div className="h-10 bg-zinc-950/90 border-t border-zinc-800 px-3 flex items-center justify-between shrink-0">
        {/* Left: Tools */}
        <div className="flex items-center gap-1.5 text-zinc-400">
          <button
            type="button"
            onClick={() => setToolMode("select")}
            className={`p-1 rounded transition-colors ${
              toolMode === "select" ? "text-indigo-400 bg-zinc-900 border border-zinc-800" : "hover:text-white"
            }`}
            title="Selection Tool"
          >
            <Icons.Layout className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setToolMode("crop")}
            className={`p-1 rounded transition-colors ${
              toolMode === "crop" ? "text-amber-400 bg-zinc-900 border border-zinc-800" : "hover:text-white"
            }`}
            title="Draw Freeform Crop Box"
          >
            <Icons.Scissors className="w-3.5 h-3.5" />
          </button>

          <div className="h-4 w-px bg-zinc-800 mx-1" />

          {/* Zoom controls */}
          <span className="text-[10px] font-mono text-zinc-300">{zoomLevel}%</span>
          <button
            type="button"
            onClick={() => setZoomLevel((z) => Math.max(50, z - 20))}
            className="p-1 hover:text-white"
            title="Zoom Out"
          >
            <Icons.ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setZoomLevel((z) => Math.min(200, z + 20))}
            className="p-1 hover:text-white"
            title="Zoom In"
          >
            <Icons.ZoomIn className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Right: Add to Scene / Add as New Scene */}
        <div className="flex items-center gap-1.5">
          <Button
            variant="secondary"
            size="sm"
            disabled={!activePage}
            onClick={() => {
              if (activePage) {
                if (drawBox && drawBox.w > 20 && drawBox.h > 20) {
                  onAddPanelToScene(activePage, null, {
                    x: Math.round(drawBox.x),
                    y: Math.round(drawBox.y),
                    width: Math.round(drawBox.w),
                    height: Math.round(drawBox.h),
                  }, false);
                } else if (activeSelectedPanel) {
                  onAddPanelToScene(activePage, activeSelectedPanel, undefined, false);
                } else {
                  onAddPanelToScene(activePage, null, undefined, false);
                }
              }
            }}
            className="text-[11px] py-0.5 px-2 h-6"
            title={activeSelectedPanel ? `Add Panel #${activeSelectedPanel.page_sequence} as layer to scene` : "Add page as layer to scene"}
          >
            + Layer
          </Button>

          <Button
            variant="primary"
            size="sm"
            disabled={!activePage}
            onClick={() => {
              if (activePage) {
                if (drawBox && drawBox.w > 20 && drawBox.h > 20) {
                  onAddPanelToScene(activePage, null, {
                    x: Math.round(drawBox.x),
                    y: Math.round(drawBox.y),
                    width: Math.round(drawBox.w),
                    height: Math.round(drawBox.h),
                  }, true);
                } else if (activeSelectedPanel) {
                  onAddPanelToScene(activePage, activeSelectedPanel, undefined, true);
                } else {
                  onAddPanelToScene(activePage, null, undefined, true);
                }
              }
            }}
            className="text-[11px] py-0.5 px-2 h-6 bg-indigo-600 hover:bg-indigo-500 text-white"
            title={activeSelectedPanel ? `Create new scene from Panel #${activeSelectedPanel.page_sequence}` : "Create new scene from page"}
          >
            + Scene
          </Button>
        </div>
      </div>
    </div>
  );
};
