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
    customCrop?: {
      x: number;
      y: number;
      width: number;
      height: number;
      crop_type?: "rect" | "polygon" | "pen";
      polygon_points?: Array<{ x: number; y: number }>;
      clip_path?: string;
    },
    asNewScene?: boolean,
    autoPlay?: boolean
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
  type ToolMode = "select" | "crop" | "rect" | "polygon" | "pen" | "pan";

  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [toolMode, setToolMode] = useState<ToolMode>("select");

  // Rectangle Crop State
  const [isDrawing, setIsDrawing] = useState<boolean>(false);
  const [drawBox, setDrawBox] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [activeRectHandle, setActiveRectHandle] = useState<string | null>(null);
  const [rectDragOrigin, setRectDragOrigin] = useState<{ startX: number; startY: number; box: { x: number; y: number; w: number; h: number } } | null>(null);

  // Polygon Crop State
  const [polygonPoints, setPolygonPoints] = useState<Array<{ x: number; y: number }>>([]);
  const [isPolygonClosed, setIsPolygonClosed] = useState<boolean>(false);
  const [activePolyVertex, setActivePolyVertex] = useState<number | null>(null);
  const [polyHoverCursor, setPolyHoverCursor] = useState<{ x: number; y: number } | null>(null);

  // Pen Cut State
  const [penPoints, setPenPoints] = useState<Array<{ x: number; y: number }>>([]);
  const [isPenDrawing, setIsPenDrawing] = useState<boolean>(false);

  // Auto-Add and Confirmation Prompt State
  const [autoAddToTimeline, setAutoAddToTimeline] = useState<boolean>(() => {
    try {
      return localStorage.getItem("panelflow_auto_add_timeline") === "true";
    } catch {
      return false;
    }
  });
  const [showAddPromptModal, setShowAddPromptModal] = useState<boolean>(false);
  const [pendingCropData, setPendingCropData] = useState<{
    crop_type: "rect" | "polygon" | "pen";
    x: number;
    y: number;
    width: number;
    height: number;
    polygon_points?: Array<{ x: number; y: number }>;
    clip_path?: string;
  } | null>(null);

  const imageContainerRef = useRef<HTMLDivElement>(null);

  const activePageIndex = pages.findIndex((p) => p.id === selectedPageId);
  const activePage = pages[activePageIndex >= 0 ? activePageIndex : 0] || null;

  // Compute Bounding Box from list of arbitrary 2D points
  const getBoundingBoxFromPoints = (points: Array<{ x: number; y: number }>) => {
    if (!points || points.length === 0) return { x: 0, y: 0, width: 100, height: 100 };
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of points) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    return {
      x: Math.round(minX),
      y: Math.round(minY),
      width: Math.max(12, Math.round(maxX - minX)),
      height: Math.max(12, Math.round(maxY - minY)),
    };
  };

  // Convert points to percentage CSS polygon() clip-path relative to bounding box
  const getRelativeClipPath = (
    points: Array<{ x: number; y: number }>,
    bbox: { x: number; y: number; width: number; height: number }
  ) => {
    if (!points || points.length === 0 || bbox.width <= 0 || bbox.height <= 0) return undefined;
    const relPoints = points.map((p) => {
      const rx = Math.max(0, Math.min(100, Math.round(((p.x - bbox.x) / bbox.width) * 1000) / 10));
      const ry = Math.max(0, Math.min(100, Math.round(((p.y - bbox.y) / bbox.height) * 1000) / 10));
      return `${rx}% ${ry}%`;
    });
    return `polygon(${relPoints.join(", ")})`;
  };

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
      setPolygonPoints([]);
      setPenPoints([]);
    }
  };

  const handleNextPage = () => {
    if (activePageIndex < pages.length - 1) {
      onSelectPage(pages[activePageIndex + 1].id);
      onSelectPanel(null);
      setDrawBox(null);
      setPolygonPoints([]);
      setPenPoints([]);
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

  // SVG Coordinates Helper
  const getSvgPoint = (e: React.MouseEvent<SVGElement>) => {
    if (!activePage) return { x: 0, y: 0 };
    const svg = e.currentTarget instanceof SVGSVGElement
      ? e.currentTarget
      : e.currentTarget.ownerSVGElement;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * (activePage.width || 1200);
    const y = ((e.clientY - rect.top) / rect.height) * (activePage.height || 1800);
    return { x: Math.round(x), y: Math.round(y) };
  };

  // SVG Mouse Down handler
  const handleSvgMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!activePage || toolMode === "pan" || toolMode === "select") return;
    const pt = getSvgPoint(e);

    if (toolMode === "rect") {
      // If clicking inside or on handles of existing drawBox, handle dragging is initiated directly on handle elements.
      // Otherwise start drawing new box:
      setIsDrawing(true);
      setDrawBox({ x: pt.x, y: pt.y, w: 0, h: 0 });
      onSelectPanel(null);
    } else if (toolMode === "polygon") {
      if (isPolygonClosed) {
        // If clicking outside, start fresh polygon
        setPolygonPoints([pt]);
        setIsPolygonClosed(false);
      } else {
        // If clicking near first point (within 20px), close polygon!
        if (polygonPoints.length >= 3) {
          const first = polygonPoints[0];
          const dist = Math.hypot(pt.x - first.x, pt.y - first.y);
          if (dist < 25) {
            setIsPolygonClosed(true);
            setPolyHoverCursor(null);
            return;
          }
        }
        setPolygonPoints((prev) => [...prev, pt]);
      }
    } else if (toolMode === "pen") {
      setIsPenDrawing(true);
      setPenPoints([pt]);
      onSelectPanel(null);
    }
  };

  // SVG Mouse Move handler
  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!activePage || toolMode === "pan" || toolMode === "select") return;
    const pt = getSvgPoint(e);

    if (toolMode === "rect") {
      if (activeRectHandle && rectDragOrigin) {
        // Resizing or moving drawBox handles
        const dx = pt.x - rectDragOrigin.startX;
        const dy = pt.y - rectDragOrigin.startY;
        const b = rectDragOrigin.box;

        setDrawBox(() => {
          let nx = b.x, ny = b.y, nw = b.w, nh = b.h;
          if (activeRectHandle === "center") {
            nx = b.x + dx;
            ny = b.y + dy;
          } else if (activeRectHandle === "se") {
            nw = Math.max(15, b.w + dx);
            nh = Math.max(15, b.h + dy);
          } else if (activeRectHandle === "nw") {
            nx = b.x + dx;
            ny = b.y + dy;
            nw = Math.max(15, b.w - dx);
            nh = Math.max(15, b.h - dy);
          } else if (activeRectHandle === "ne") {
            ny = b.y + dy;
            nw = Math.max(15, b.w + dx);
            nh = Math.max(15, b.h - dy);
          } else if (activeRectHandle === "sw") {
            nx = b.x + dx;
            nw = Math.max(15, b.w - dx);
            nh = Math.max(15, b.h + dy);
          } else if (activeRectHandle === "n") {
            ny = b.y + dy;
            nh = Math.max(15, b.h - dy);
          } else if (activeRectHandle === "s") {
            nh = Math.max(15, b.h + dy);
          } else if (activeRectHandle === "w") {
            nx = b.x + dx;
            nw = Math.max(15, b.w - dx);
          } else if (activeRectHandle === "e") {
            nw = Math.max(15, b.w + dx);
          }
          return { x: Math.round(nx), y: Math.round(ny), w: Math.round(nw), h: Math.round(nh) };
        });
      } else if (isDrawing && drawBox) {
        setDrawBox((prev) => {
          if (!prev) return null;
          return {
            x: Math.min(prev.x, pt.x),
            y: Math.min(prev.y, pt.y),
            w: Math.abs(pt.x - prev.x),
            h: Math.abs(pt.y - prev.y),
          };
        });
      }
    } else if (toolMode === "polygon") {
      if (activePolyVertex !== null) {
        setPolygonPoints((prev) => {
          const updated = [...prev];
          updated[activePolyVertex] = pt;
          return updated;
        });
      } else if (!isPolygonClosed) {
        setPolyHoverCursor(pt);
      }
    } else if (toolMode === "pen") {
      if (isPenDrawing) {
        setPenPoints((prev) => {
          const last = prev[prev.length - 1];
          if (!last || Math.hypot(pt.x - last.x, pt.y - last.y) > 6) {
            return [...prev, pt];
          }
          return prev;
        });
      }
    }
  };

  // SVG Mouse Up handler
  const handleSvgMouseUp = () => {
    setIsDrawing(false);
    setActiveRectHandle(null);
    setRectDragOrigin(null);
    setActivePolyVertex(null);
    if (isPenDrawing) {
      setIsPenDrawing(false);
    }
  };

  // SVG Double-Click to close polygon or pen cut
  const handleSvgDoubleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    e.stopPropagation();
    if (toolMode === "polygon" && polygonPoints.length >= 3) {
      setIsPolygonClosed(true);
      setPolyHoverCursor(null);
    }
  };

  // Compile active crop information into standard payload
  const getActiveCropPayload = () => {
    if (!activePage) return null;

    if (toolMode === "polygon" && polygonPoints.length >= 3) {
      const bbox = getBoundingBoxFromPoints(polygonPoints);
      const clipPath = getRelativeClipPath(polygonPoints, bbox);
      return {
        crop_type: "polygon" as const,
        x: bbox.x,
        y: bbox.y,
        width: bbox.width,
        height: bbox.height,
        polygon_points: polygonPoints,
        clip_path: clipPath,
      };
    }

    if (toolMode === "pen" && penPoints.length >= 3) {
      const bbox = getBoundingBoxFromPoints(penPoints);
      const clipPath = getRelativeClipPath(penPoints, bbox);
      return {
        crop_type: "pen" as const,
        x: bbox.x,
        y: bbox.y,
        width: bbox.width,
        height: bbox.height,
        polygon_points: penPoints,
        clip_path: clipPath,
      };
    }

    if (drawBox && drawBox.w > 15 && drawBox.h > 15) {
      return {
        crop_type: "rect" as const,
        x: Math.round(drawBox.x),
        y: Math.round(drawBox.y),
        width: Math.round(drawBox.w),
        height: Math.round(drawBox.h),
      };
    }

    if (activeSelectedPanel) {
      return {
        crop_type: "rect" as const,
        x: activeSelectedPanel.x,
        y: activeSelectedPanel.y,
        width: activeSelectedPanel.width,
        height: activeSelectedPanel.height,
      };
    }

    return null;
  };

  // Handle "Add to Timeline" triggering
  const handleTriggerAddToTimeline = (preferredMode?: "scene" | "layer") => {
    const cropData = getActiveCropPayload();
    if (!cropData || !activePage) return;

    if (autoAddToTimeline) {
      // Auto-add directly and start player playback
      onAddPanelToScene(
        activePage,
        activeSelectedPanel,
        cropData,
        preferredMode === "layer" ? false : true,
        true // autoPlay!
      );
      setDrawBox(null);
      setPolygonPoints([]);
      setIsPolygonClosed(false);
      setPenPoints([]);
    } else {
      // Prompt user with confirmation modal
      setPendingCropData(cropData);
      setShowAddPromptModal(true);
    }
  };

  // Clear current active crops
  const handleClearCrop = () => {
    setDrawBox(null);
    setPolygonPoints([]);
    setIsPolygonClosed(false);
    setPenPoints([]);
    setPendingCropData(null);
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
                    toolMode === "select"
                      ? "cursor-default"
                      : toolMode === "rect" || toolMode === "pen"
                      ? "cursor-crosshair"
                      : "cursor-pointer"
                  }`}
                  viewBox={`0 0 ${activePage.width || 1200} ${activePage.height || 1800}`}
                  preserveAspectRatio="none"
                  onMouseDown={handleSvgMouseDown}
                  onMouseMove={handleSvgMouseMove}
                  onMouseUp={handleSvgMouseUp}
                  onDoubleClick={handleSvgDoubleClick}
                >
                  {/* Detected Panels */}
                  {pagePanels.map((p, pIdx) => {
                    const isSelected = selectedPanelId === p.id && toolMode === "select";
                    const colorScheme = panelColors[pIdx % panelColors.length];
                    return (
                      <g
                        key={p.id}
                        onClick={(e) => {
                          if (toolMode === "select") {
                            e.stopPropagation();
                            onSelectPanel(p);
                            setDrawBox(null);
                            setPolygonPoints([]);
                            setPenPoints([]);
                          }
                        }}
                        className={toolMode === "select" ? "cursor-pointer group" : "pointer-events-none"}
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

                  {/* 1. Rectangle Adjustment Crop Box & Interactive Handles */}
                  {drawBox && drawBox.w > 4 && drawBox.h > 4 && (
                    <g>
                      <rect
                        x={drawBox.x}
                        y={drawBox.y}
                        width={drawBox.w}
                        height={drawBox.h}
                        fill="rgba(245, 158, 11, 0.22)"
                        stroke="#fbbf24"
                        strokeWidth={3}
                        strokeDasharray={isDrawing ? "6 3" : "none"}
                        className="transition-all"
                      />

                      {/* Dimension Readout Pill */}
                      <rect
                        x={drawBox.x}
                        y={Math.max(0, drawBox.y - 24)}
                        width={120}
                        height={20}
                        rx={4}
                        fill="rgba(24, 24, 27, 0.9)"
                        stroke="#fbbf24"
                        strokeWidth={1}
                      />
                      <text
                        x={drawBox.x + 8}
                        y={Math.max(14, drawBox.y - 10)}
                        fill="#fde68a"
                        fontSize={12}
                        fontFamily="monospace"
                        fontWeight="bold"
                      >
                        {Math.round(drawBox.w)} × {Math.round(drawBox.h)} px
                      </text>

                      {/* 8 Resize Handles on Rectangle (4 corners + 4 edges) */}
                      {!isDrawing && (
                        <>
                          {/* NW */}
                          <circle
                            cx={drawBox.x}
                            cy={drawBox.y}
                            r={7}
                            fill="#ffffff"
                            stroke="#fbbf24"
                            strokeWidth={2.5}
                            className="cursor-nwse-resize hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("nw");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                          {/* NE */}
                          <circle
                            cx={drawBox.x + drawBox.w}
                            cy={drawBox.y}
                            r={7}
                            fill="#ffffff"
                            stroke="#fbbf24"
                            strokeWidth={2.5}
                            className="cursor-nesw-resize hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("ne");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                          {/* SW */}
                          <circle
                            cx={drawBox.x}
                            cy={drawBox.y + drawBox.h}
                            r={7}
                            fill="#ffffff"
                            stroke="#fbbf24"
                            strokeWidth={2.5}
                            className="cursor-nesw-resize hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("sw");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                          {/* SE */}
                          <circle
                            cx={drawBox.x + drawBox.w}
                            cy={drawBox.y + drawBox.h}
                            r={7}
                            fill="#ffffff"
                            stroke="#fbbf24"
                            strokeWidth={2.5}
                            className="cursor-nwse-resize hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("se");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                          {/* N */}
                          <rect
                            x={drawBox.x + drawBox.w / 2 - 5}
                            y={drawBox.y - 5}
                            width={10}
                            height={10}
                            fill="#ffffff"
                            stroke="#fbbf24"
                            strokeWidth={2}
                            rx={1}
                            className="cursor-ns-resize hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("n");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                          {/* S */}
                          <rect
                            x={drawBox.x + drawBox.w / 2 - 5}
                            y={drawBox.y + drawBox.h - 5}
                            width={10}
                            height={10}
                            fill="#ffffff"
                            stroke="#fbbf24"
                            strokeWidth={2}
                            rx={1}
                            className="cursor-ns-resize hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("s");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                          {/* W */}
                          <rect
                            x={drawBox.x - 5}
                            y={drawBox.y + drawBox.h / 2 - 5}
                            width={10}
                            height={10}
                            fill="#ffffff"
                            stroke="#fbbf24"
                            strokeWidth={2}
                            rx={1}
                            className="cursor-ew-resize hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("w");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                          {/* E */}
                          <rect
                            x={drawBox.x + drawBox.w - 5}
                            y={drawBox.y + drawBox.h / 2 - 5}
                            width={10}
                            height={10}
                            fill="#ffffff"
                            stroke="#fbbf24"
                            strokeWidth={2}
                            rx={1}
                            className="cursor-ew-resize hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("e");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                          {/* Center Move Anchor */}
                          <rect
                            x={drawBox.x + drawBox.w / 2 - 8}
                            y={drawBox.y + drawBox.h / 2 - 8}
                            width={16}
                            height={16}
                            fill="#fbbf24"
                            rx={3}
                            className="cursor-move hover:scale-115 transition-transform shadow-md"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              const pt = getSvgPoint(e);
                              setActiveRectHandle("center");
                              setRectDragOrigin({ startX: pt.x, startY: pt.y, box: { ...drawBox } });
                            }}
                          />
                        </>
                      )}
                    </g>
                  )}

                  {/* 2. Polygon Adjustment Crop */}
                  {polygonPoints.length > 0 && (
                    <g>
                      {/* Polygon fill & stroke */}
                      {isPolygonClosed ? (
                        <polygon
                          points={polygonPoints.map((p) => `${p.x},${p.y}`).join(" ")}
                          fill="rgba(6, 182, 212, 0.25)"
                          stroke="#06b6d4"
                          strokeWidth={3}
                          className="shadow-lg"
                        />
                      ) : (
                        <>
                          <polyline
                            points={polygonPoints.map((p) => `${p.x},${p.y}`).join(" ")}
                            fill="none"
                            stroke="#06b6d4"
                            strokeWidth={3}
                            strokeDasharray="6 3"
                          />
                          {polyHoverCursor && (
                            <line
                              x1={polygonPoints[polygonPoints.length - 1].x}
                              y1={polygonPoints[polygonPoints.length - 1].y}
                              x2={polyHoverCursor.x}
                              y2={polyHoverCursor.y}
                              stroke="#38bdf8"
                              strokeWidth={2}
                              strokeDasharray="4 2"
                            />
                          )}
                        </>
                      )}

                      {/* Interactive Vertex Handles */}
                      {polygonPoints.map((p, idx) => (
                        <circle
                          key={idx}
                          cx={p.x}
                          cy={p.y}
                          r={idx === 0 && !isPolygonClosed ? 8 : 6}
                          fill={idx === 0 && !isPolygonClosed ? "#22d3ee" : "#ffffff"}
                          stroke="#06b6d4"
                          strokeWidth={2.5}
                          className="cursor-move hover:scale-125 transition-transform"
                          onMouseDown={(e) => {
                            e.stopPropagation();
                            if (!isPolygonClosed && idx === 0 && polygonPoints.length >= 3) {
                              setIsPolygonClosed(true);
                              setPolyHoverCursor(null);
                            } else {
                              setActivePolyVertex(idx);
                            }
                          }}
                        />
                      ))}

                      {/* Close Polygon Guide Indicator */}
                      {!isPolygonClosed && polygonPoints.length >= 3 && (
                        <circle
                          cx={polygonPoints[0].x}
                          cy={polygonPoints[0].y}
                          r={14}
                          fill="none"
                          stroke="#22d3ee"
                          strokeWidth={2}
                          strokeDasharray="3 3"
                          className="animate-spin pointer-events-none"
                        />
                      )}
                    </g>
                  )}

                  {/* 3. Pen Cut Freehand / Polyline Tool */}
                  {penPoints.length > 0 && (
                    <g>
                      {penPoints.length >= 3 && !isPenDrawing ? (
                        <polygon
                          points={penPoints.map((p) => `${p.x},${p.y}`).join(" ")}
                          fill="rgba(244, 63, 94, 0.25)"
                          stroke="#f43f5e"
                          strokeWidth={3}
                          className="shadow-lg"
                        />
                      ) : (
                        <polyline
                          points={penPoints.map((p) => `${p.x},${p.y}`).join(" ")}
                          fill="none"
                          stroke="#f43f5e"
                          strokeWidth={3.5}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      )}
                      {/* Start/End handles */}
                      {penPoints.length > 0 && (
                        <circle
                          cx={penPoints[0].x}
                          cy={penPoints[0].y}
                          r={5}
                          fill="#ffffff"
                          stroke="#f43f5e"
                          strokeWidth={2}
                        />
                      )}
                    </g>
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

      {/* Bottom Toolbar: Tools, Zoom, Auto-Add Toggle, and Add to Timeline */}
      <div className="h-10 bg-zinc-950/95 border-t border-zinc-800 px-3 flex items-center justify-between shrink-0 select-none">
        {/* Left: Tool Selection & Zoom */}
        <div className="flex items-center gap-1.5 text-zinc-400">
          {/* Select Tool */}
          <button
            type="button"
            onClick={() => setToolMode("select")}
            className={`px-2 py-1 rounded text-[11px] font-semibold flex items-center gap-1 transition-colors ${
              toolMode === "select"
                ? "text-indigo-400 bg-zinc-900 border border-indigo-500/40"
                : "hover:text-white"
            }`}
            title="Selection Tool (Select Panels)"
          >
            <Icons.Layout className="w-3.5 h-3.5" />
            <span>Select</span>
          </button>

          {/* Rectangle Adjustment Crop */}
          <button
            type="button"
            onClick={() => {
              setToolMode("rect");
              onSelectPanel(null);
            }}
            className={`px-2 py-1 rounded text-[11px] font-semibold flex items-center gap-1 transition-colors ${
              toolMode === "rect"
                ? "text-amber-400 bg-amber-950/40 border border-amber-500/50"
                : "hover:text-white"
            }`}
            title="Rectangle Adjustment Crop Tool"
          >
            <Icons.Maximize className="w-3.5 h-3.5" />
            <span>Rect</span>
          </button>

          {/* Polygon Adjustment Crop */}
          <button
            type="button"
            onClick={() => {
              setToolMode("polygon");
              onSelectPanel(null);
            }}
            className={`px-2 py-1 rounded text-[11px] font-semibold flex items-center gap-1 transition-colors ${
              toolMode === "polygon"
                ? "text-cyan-400 bg-cyan-950/40 border border-cyan-500/50"
                : "hover:text-white"
            }`}
            title="Polygon Adjustment Crop Tool (Click vertices, close to finish)"
          >
            <Icons.Sparkles className="w-3.5 h-3.5" />
            <span>Polygon</span>
          </button>

          {/* Pen Cut Tool */}
          <button
            type="button"
            onClick={() => {
              setToolMode("pen");
              onSelectPanel(null);
            }}
            className={`px-2 py-1 rounded text-[11px] font-semibold flex items-center gap-1 transition-colors ${
              toolMode === "pen"
                ? "text-rose-400 bg-rose-950/40 border border-rose-500/50"
                : "hover:text-white"
            }`}
            title="Pen Cut Tool (Freehand / Click Cutline)"
          >
            <Icons.Scissors className="w-3.5 h-3.5" />
            <span>Pen Cut</span>
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

          <div className="h-4 w-px bg-zinc-800 mx-1" />

          {/* Auto-Add to Timeline Toggle */}
          <button
            type="button"
            onClick={() => {
              setAutoAddToTimeline((prev) => {
                const next = !prev;
                try {
                  localStorage.setItem("panelflow_auto_add_timeline", String(next));
                } catch {}
                return next;
              });
            }}
            className={`px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 transition-colors ${
              autoAddToTimeline
                ? "bg-cyan-950/80 text-cyan-300 border border-cyan-700/60"
                : "bg-zinc-850 text-zinc-400 hover:text-white border border-zinc-800"
            }`}
            title="Toggle: automatically add completed crops directly to timeline"
          >
            <span>⚡ Auto-Add: {autoAddToTimeline ? "ON" : "OFF"}</span>
          </button>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1.5">
          {/* If any custom crop is active (Rect, Polygon, or Pen) */}
          {((drawBox && drawBox.w > 15) || polygonPoints.length >= 3 || penPoints.length >= 3) ? (
            <>
              <button
                type="button"
                onClick={handleClearCrop}
                className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors"
                title="Clear Current Crop"
              >
                Clear
              </button>

              <Button
                variant="primary"
                size="sm"
                onClick={() => handleTriggerAddToTimeline("scene")}
                className="text-[11px] py-0.5 px-3 h-6 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-1 shadow-md"
                title="Add cropped region to timeline"
              >
                <Icons.Play className="w-3 h-3 fill-current" />
                <span>+ Add to Timeline</span>
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="secondary"
                size="sm"
                disabled={!activePage}
                onClick={() => {
                  if (activePage) {
                    if (activeSelectedPanel) {
                      onAddPanelToScene(activePage, activeSelectedPanel, undefined, false, true);
                    } else {
                      onAddPanelToScene(activePage, null, undefined, false, true);
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
                    if (activeSelectedPanel) {
                      onAddPanelToScene(activePage, activeSelectedPanel, undefined, true, true);
                    } else {
                      onAddPanelToScene(activePage, null, undefined, true, true);
                    }
                  }
                }}
                className="text-[11px] py-0.5 px-2 h-6 bg-indigo-600 hover:bg-indigo-500 text-white"
                title={activeSelectedPanel ? `Create new scene from Panel #${activeSelectedPanel.page_sequence}` : "Create new scene from page"}
              >
                + Scene
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Confirmation Modal: "May I add to the timeline this cropping?" */}
      {showAddPromptModal && pendingCropData && activePage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-zinc-900 border border-zinc-700/80 rounded-2xl shadow-2xl max-w-md w-full p-6 flex flex-col gap-4 text-zinc-100 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <span className="p-1.5 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
                  <Icons.Scissors className="w-5 h-5" />
                </span>
                <div>
                  <h3 className="text-sm font-bold">Add Crop to Timeline?</h3>
                  <p className="text-[11px] text-zinc-400">
                    May I add this {pendingCropData.crop_type.toUpperCase()} crop to your timeline?
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowAddPromptModal(false)}
                className="text-zinc-500 hover:text-zinc-300"
              >
                <Icons.XCircle className="w-5 h-5" />
              </button>
            </div>

            {/* Cutout Preview Box */}
            <div className="relative aspect-[16/9] w-full bg-zinc-950 rounded-xl overflow-hidden border border-zinc-800 flex items-center justify-center p-2">
              <img
                src={api.getPageImageUrl(projectId, activePage.id)}
                alt="Crop preview"
                className="max-w-full max-h-full object-contain"
                style={{
                  clipPath: pendingCropData.clip_path,
                }}
              />
              <div className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/80 font-mono text-[10px] text-cyan-300 border border-cyan-500/40">
                {pendingCropData.crop_type.toUpperCase()} • {pendingCropData.width}×{pendingCropData.height}px
              </div>
            </div>

            {/* Remember Choice Checkbox */}
            <label className="flex items-center gap-2.5 text-xs text-zinc-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoAddToTimeline}
                onChange={(e) => {
                  setAutoAddToTimeline(e.target.checked);
                  try {
                    localStorage.setItem("panelflow_auto_add_timeline", String(e.target.checked));
                  } catch {}
                }}
                className="w-4 h-4 rounded accent-indigo-600 cursor-pointer"
              />
              <span>Always add future crops automatically without asking</span>
            </label>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowAddPromptModal(false)}
              >
                Cancel
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  if (activePage && pendingCropData) {
                    onAddPanelToScene(activePage, activeSelectedPanel, pendingCropData, false, true);
                    setShowAddPromptModal(false);
                    handleClearCrop();
                  }
                }}
              >
                + Add as Layer
              </Button>

              <Button
                variant="primary"
                size="sm"
                className="bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1.5 font-semibold"
                onClick={() => {
                  if (activePage && pendingCropData) {
                    onAddPanelToScene(activePage, activeSelectedPanel, pendingCropData, true, true);
                    setShowAddPromptModal(false);
                    handleClearCrop();
                  }
                }}
              >
                <Icons.Play className="w-3.5 h-3.5 fill-current" />
                <span>+ Add as Scene & Play</span>
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
