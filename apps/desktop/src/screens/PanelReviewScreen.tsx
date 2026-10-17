import React, { useEffect, useState, useRef, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type { Project, Page, Panel } from "@panelflow/shared-types";
import { Button, Card, Badge, Modal, Input, Icons } from "@panelflow/ui";

interface PanelReviewScreenProps {
  project: Project;
  onBack: () => void;
  onPanelsApproved: (updatedProject: Project) => void;
  onProceedToOCR?: (project: Project) => void;
}

type DragMode = "none" | "move" | "resize" | "draw";
type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

export const PanelReviewScreen: React.FC<PanelReviewScreenProps> = ({
  project,
  onBack,
  onPanelsApproved,
  onProceedToOCR,
}) => {
  const [pages, setPages] = useState<Page[]>([]);
  const [selectedPageIndex, setSelectedPageIndex] = useState<number>(0);
  const [panels, setPanels] = useState<Panel[]>([]);
  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null);
  const [selectedForMerge, setSelectedForMerge] = useState<string[]>([]);

  const [loading, setLoading] = useState<boolean>(true);
  const [normalizing, setNormalizing] = useState<boolean>(false);
  const [detecting, setDetecting] = useState<boolean>(false);
  const [confirming, setConfirming] = useState<boolean>(false);

  const [readingDirection, setReadingDirection] = useState<"ltr" | "rtl">("ltr");
  const [detectionProfile, setDetectionProfile] = useState<string>("AUTO");
  const [cacheBuster, setCacheBuster] = useState<number>(Date.now());

  // Canvas View Controls
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [showBoxes, setShowBoxes] = useState<boolean>(true);
  const [isDrawMode, setIsDrawMode] = useState<boolean>(false);

  // Manual Add Modal State
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [manualX, setManualX] = useState<number>(50);
  const [manualY, setManualY] = useState<number>(50);
  const [manualW, setManualW] = useState<number>(400);
  const [manualH, setManualH] = useState<number>(300);

  // Undo / Redo History Stack
  const [undoStack, setUndoStack] = useState<Array<Panel[]>>([]);
  const [redoStack, setRedoStack] = useState<Array<Panel[]>>([]);

  // Dragging / Resizing / Drawing refs & state
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [dragMode, setDragMode] = useState<DragMode>("none");
  const [activeHandle, setActiveHandle] = useState<ResizeHandle | null>(null);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [initialBox, setInitialBox] = useState<{ x: number; y: number; w: number; h: number }>({ x: 0, y: 0, w: 0, h: 0 });
  const [drawCurrent, setDrawCurrent] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  const activePage = pages[selectedPageIndex] || null;
  const pagePanels = activePage
    ? panels.filter((p) => p.page_id === activePage.id).sort((a, b) => a.page_sequence - b.page_sequence)
    : [];
  const selectedPanel = panels.find((p) => p.id === selectedPanelId) || null;

  const pushUndo = useCallback((currentPanels: Panel[]) => {
    setUndoStack((prev) => [...prev.slice(-20), currentPanels]);
    setRedoStack([]);
  }, []);

  const handleUndo = useCallback(async () => {
    if (undoStack.length === 0) return;
    const previous = undoStack[undoStack.length - 1];
    setUndoStack((prev) => prev.slice(0, -1));
    setRedoStack((prev) => [...prev, panels]);
    setPanels(previous);
    setCacheBuster(Date.now());
  }, [undoStack, panels]);

  const handleRedo = useCallback(async () => {
    if (redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    setRedoStack((prev) => prev.slice(0, -1));
    setUndoStack((prev) => [...prev, panels]);
    setPanels(next);
    setCacheBuster(Date.now());
  }, [redoStack, panels]);

  const loadData = async () => {
    try {
      setLoading(true);
      const pageList = await api.listPages(project.id);
      setPages(pageList);
      const allPanels = await api.listPanels(project.id);
      setPanels(allPanels);
    } catch (err: any) {
      alert(`Failed to load project data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [project.id]);

  // Keyboard Navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          handleRedo();
        } else {
          handleUndo();
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        handleRedo();
      } else if (e.key === "ArrowLeft" && !e.shiftKey) {
        if (selectedPageIndex > 0) {
          setSelectedPageIndex((prev) => prev - 1);
          setSelectedPanelId(null);
        }
      } else if (e.key === "ArrowRight" && !e.shiftKey) {
        if (selectedPageIndex < pages.length - 1) {
          setSelectedPageIndex((prev) => prev + 1);
          setSelectedPanelId(null);
        }
      } else if (e.key === "[" || (e.shiftKey && e.key === "Tab")) {
        e.preventDefault();
        if (pagePanels.length > 0) {
          const currIdx = pagePanels.findIndex((p) => p.id === selectedPanelId);
          const prevIdx = currIdx > 0 ? currIdx - 1 : pagePanels.length - 1;
          setSelectedPanelId(pagePanels[prevIdx].id);
        }
      } else if (e.key === "]" || (!e.shiftKey && e.key === "Tab")) {
        e.preventDefault();
        if (pagePanels.length > 0) {
          const currIdx = pagePanels.findIndex((p) => p.id === selectedPanelId);
          const nextIdx = currIdx >= 0 && currIdx < pagePanels.length - 1 ? currIdx + 1 : 0;
          setSelectedPanelId(pagePanels[nextIdx].id);
        }
      } else if ((e.key === "Delete" || e.key === "Backspace") && selectedPanelId) {
        e.preventDefault();
        handleDeletePanel(selectedPanelId);
      } else if (e.key === "Escape") {
        setIsDrawMode(false);
        setSelectedPanelId(null);
        setSelectedForMerge([]);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedPageIndex, pages.length, pagePanels, selectedPanelId, handleUndo, handleRedo]);

  const handleNormalize = async () => {
    setNormalizing(true);
    try {
      const res = await api.normalizeProject(project.id, 1920);
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 600));
        const job = await api.getJob(res.job_id);
        if (job.status === "SUCCEEDED" || job.status === "FAILED") break;
      }
      setCacheBuster(Date.now());
      alert("Page normalization completed successfully!");
    } catch (err: any) {
      alert(`Normalization failed: ${err.message}`);
    } finally {
      setNormalizing(false);
    }
  };

  const handleAutoDetect = async () => {
    setDetecting(true);
    try {
      const res = await api.detectPanels(project.id, readingDirection, 0.02);
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 600));
        const job = await api.getJob(res.job_id);
        if (job.status === "SUCCEEDED" || job.status === "FAILED") break;
      }
      const updatedPanels = await api.listPanels(project.id);
      pushUndo(panels);
      setPanels(updatedPanels);
      setCacheBuster(Date.now());
    } catch (err: any) {
      alert(`Panel detection failed: ${err.message}`);
    } finally {
      setDetecting(false);
    }
  };

  const handleDetectSinglePage = async () => {
    if (!activePage) return;
    setDetecting(true);
    try {
      pushUndo(panels);
      const updatedPagePanels = await api.detectPagePanels(
        project.id,
        activePage.id,
        readingDirection,
        detectionProfile
      );
      const otherPanels = panels.filter((p) => p.page_id !== activePage.id);
      setPanels([...otherPanels, ...updatedPagePanels]);
      setCacheBuster(Date.now());
    } catch (err: any) {
      alert(`Page detection failed: ${err.message}`);
    } finally {
      setDetecting(false);
    }
  };

  const handleAddManualPanel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activePage) return;
    try {
      pushUndo(panels);
      const newPanel = await api.addPanel(
        project.id,
        activePage.id,
        Number(manualX),
        Number(manualY),
        Number(manualW),
        Number(manualH)
      );
      setPanels((prev) => [...prev, newPanel]);
      setIsAddModalOpen(false);
      setSelectedPanelId(newPanel.id);
      setCacheBuster(Date.now());
    } catch (err: any) {
      alert(`Failed to add panel: ${err.message}`);
    }
  };

  const handleDeletePanel = async (panelId: string) => {
    try {
      pushUndo(panels);
      await api.deletePanel(project.id, panelId);
      setPanels((prev) => prev.filter((p) => p.id !== panelId));
      if (selectedPanelId === panelId) setSelectedPanelId(null);
      setSelectedForMerge((prev) => prev.filter((id) => id !== panelId));
    } catch (err: any) {
      alert(`Failed to delete panel: ${err.message}`);
    }
  };

  const handleSplit = async (splitType: "horizontal" | "vertical") => {
    if (!selectedPanelId) return;
    try {
      pushUndo(panels);
      const updatedPagePanels = await api.splitPanel(project.id, selectedPanelId, splitType, 0.5);
      const otherPanels = panels.filter((p) => p.page_id !== activePage?.id);
      setPanels([...otherPanels, ...updatedPagePanels]);
      setCacheBuster(Date.now());
    } catch (err: any) {
      alert(`Split failed: ${err.message}`);
    }
  };

  const handleMerge = async () => {
    if (selectedForMerge.length < 2) {
      alert("Please select at least 2 panels to merge.");
      return;
    }
    try {
      pushUndo(panels);
      const merged = await api.mergePanels(project.id, selectedForMerge);
      const updatedAll = await api.listPanels(project.id);
      setPanels(updatedAll);
      setSelectedForMerge([]);
      setSelectedPanelId(merged.id);
      setCacheBuster(Date.now());
    } catch (err: any) {
      alert(`Merge failed: ${err.message}`);
    }
  };

  const handleMarkFullPage = async () => {
    if (!selectedPanel || !activePage) return;
    try {
      pushUndo(panels);
      const updated = await api.updatePanel(
        project.id,
        selectedPanel.id,
        0,
        0,
        activePage.width || 1200,
        activePage.height || 1800,
        "CONFIRMED",
        "FULL_PAGE"
      );
      setPanels((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setCacheBuster(Date.now());
    } catch (err: any) {
      alert(`Failed to set full page: ${err.message}`);
    }
  };

  const handleReorder = async (index: number, direction: "up" | "down") => {
    const target = direction === "up" ? index - 1 : index + 1;
    if (target < 0 || target >= pagePanels.length) return;

    pushUndo(panels);
    const newPagePanels = [...pagePanels];
    const [moved] = newPagePanels.splice(index, 1);
    newPagePanels.splice(target, 0, moved);

    // Map back into overall panels
    const otherPanels = panels.filter((p) => p.page_id !== activePage?.id);
    const combined = [...otherPanels, ...newPagePanels];
    setPanels(combined);

    try {
      const updated = await api.reorderPanels(project.id, combined.map((p) => p.id));
      setPanels(updated);
    } catch (err: any) {
      alert(`Reordering failed: ${err.message}`);
      loadData();
    }
  };

  const handleConfirm = async () => {
    if (panels.length === 0) {
      alert("Please detect or add at least one panel before confirming.");
      return;
    }
    setConfirming(true);
    try {
      await api.confirmPanels(project.id);
      const updatedProj = await api.getProject(project.id);
      alert("Panels confirmed successfully! Project stage transitioned to PANELS_DETECTED.");
      onPanelsApproved(updatedProj);
    } catch (err: any) {
      alert(`Confirmation failed: ${err.message}`);
    } finally {
      setConfirming(false);
    }
  };

  // Convert client mouse event to SVG coordinate space
  const getSvgCoordinates = (e: React.MouseEvent<SVGSVGElement>): { x: number; y: number } => {
    if (!svgRef.current || !activePage) return { x: 0, y: 0 };
    const svg = svgRef.current;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const transformed = pt.matrixTransform(svg.getScreenCTM()?.inverse());
    return {
      x: Math.round(transformed.x),
      y: Math.round(transformed.y),
    };
  };

  const handleSvgMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    const coords = getSvgCoordinates(e);
    if (isDrawMode) {
      setDragMode("draw");
      setDragStart(coords);
      setDrawCurrent({ x: coords.x, y: coords.y, w: 0, h: 0 });
    }
  };

  const handleBoxMouseDown = (e: React.MouseEvent, panel: Panel) => {
    e.stopPropagation();
    if (isDrawMode) return;

    if (e.shiftKey) {
      setSelectedForMerge((prev) =>
        prev.includes(panel.id) ? prev.filter((id) => id !== panel.id) : [...prev, panel.id]
      );
      return;
    }

    setSelectedPanelId(panel.id);
    const coords = getSvgCoordinates(e as any);
    setDragMode("move");
    setDragStart(coords);
    setInitialBox({ x: panel.x, y: panel.y, w: panel.width, h: panel.height });
  };

  const handleResizeMouseDown = (e: React.MouseEvent, handle: ResizeHandle, panel: Panel) => {
    e.stopPropagation();
    setSelectedPanelId(panel.id);
    const coords = getSvgCoordinates(e as any);
    setDragMode("resize");
    setActiveHandle(handle);
    setDragStart(coords);
    setInitialBox({ x: panel.x, y: panel.y, w: panel.width, h: panel.height });
  };

  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (dragMode === "none") return;
    const coords = getSvgCoordinates(e);
    const dx = coords.x - dragStart.x;
    const dy = coords.y - dragStart.y;

    if (dragMode === "draw" && dragStart) {
      const x = Math.min(dragStart.x, coords.x);
      const y = Math.min(dragStart.y, coords.y);
      const w = Math.abs(coords.x - dragStart.x);
      const h = Math.abs(coords.y - dragStart.y);
      setDrawCurrent({ x, y, w, h });
    } else if (dragMode === "move" && selectedPanelId) {
      setPanels((prev) =>
        prev.map((p) => {
          if (p.id === selectedPanelId) {
            return {
              ...p,
              x: Math.max(0, initialBox.x + dx),
              y: Math.max(0, initialBox.y + dy),
            };
          }
          return p;
        })
      );
    } else if (dragMode === "resize" && selectedPanelId && activeHandle) {
      setPanels((prev) =>
        prev.map((p) => {
          if (p.id === selectedPanelId) {
            let newX = initialBox.x;
            let newY = initialBox.y;
            let newW = initialBox.w;
            let newH = initialBox.h;

            if (activeHandle.includes("e")) newW = Math.max(30, initialBox.w + dx);
            if (activeHandle.includes("s")) newH = Math.max(30, initialBox.h + dy);
            if (activeHandle.includes("w")) {
              const proposedW = initialBox.w - dx;
              if (proposedW > 30) {
                newX = initialBox.x + dx;
                newW = proposedW;
              }
            }
            if (activeHandle.includes("n")) {
              const proposedH = initialBox.h - dy;
              if (proposedH > 30) {
                newY = initialBox.y + dy;
                newH = proposedH;
              }
            }

            return { ...p, x: newX, y: newY, width: newW, height: newH };
          }
          return p;
        })
      );
    }
  };

  const handleSvgMouseUp = async () => {
    if (dragMode === "draw" && drawCurrent && activePage) {
      if (drawCurrent.w > 20 && drawCurrent.h > 20) {
        try {
          pushUndo(panels);
          const newP = await api.addPanel(
            project.id,
            activePage.id,
            drawCurrent.x,
            drawCurrent.y,
            drawCurrent.w,
            drawCurrent.h
          );
          setPanels((prev) => [...prev, newP]);
          setSelectedPanelId(newP.id);
          setCacheBuster(Date.now());
        } catch (err: any) {
          alert(`Failed to add panel: ${err.message}`);
        }
      }
      setIsDrawMode(false);
      setDrawCurrent(null);
    } else if ((dragMode === "move" || dragMode === "resize") && selectedPanel) {
      try {
        pushUndo(panels);
        await api.updatePanel(
          project.id,
          selectedPanel.id,
          selectedPanel.x,
          selectedPanel.y,
          selectedPanel.width,
          selectedPanel.height
        );
        setCacheBuster(Date.now());
      } catch (err: any) {
        console.error("Failed to commit panel position update", err);
      }
    }

    setDragMode("none");
    setActiveHandle(null);
  };

  return (
    <div className="space-y-5 max-w-7xl mx-auto pb-16 select-none">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <Icons.ArrowLeft className="w-4 h-4 mr-1" />
            Back
          </Button>
          <div>
            <h2 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
              Panel Review & Sequence Studio
            </h2>
            <p className="text-xs text-zinc-400">
              Interactive bounding boxes, split/merge tools, and reading-order timeline.
            </p>
          </div>
        </div>

        {/* Global Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {undoStack.length > 0 && (
            <Button variant="ghost" size="sm" onClick={handleUndo} title="Undo (Ctrl+Z)">
              <Icons.Rotate className="w-3.5 h-3.5 mr-1" />
              Undo
            </Button>
          )}

          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-1 text-xs">
            <button
              onClick={() => setReadingDirection("ltr")}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${
                readingDirection === "ltr" ? "bg-indigo-600 text-white" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              LTR
            </button>
            <button
              onClick={() => setReadingDirection("rtl")}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${
                readingDirection === "rtl" ? "bg-indigo-600 text-white" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              RTL
            </button>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleNormalize}
            loading={normalizing}
            title="Non-destructively standardize resolution & color space"
          >
            Normalize All
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleAutoDetect}
            loading={detecting}
            title="Run auto-detection across whole project"
          >
            <Icons.Rotate className="w-3.5 h-3.5 mr-1" />
            Auto-Detect All
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleConfirm}
            loading={confirming}
            disabled={panels.length === 0}
            className="bg-emerald-600/20 text-emerald-300 border-emerald-800 hover:bg-emerald-600/30"
          >
            <Icons.CheckCircle className="w-4 h-4 text-emerald-400 mr-1" />
            Approve Panels ({panels.length})
          </Button>

          {onProceedToOCR && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onProceedToOCR(project)}
              disabled={panels.length === 0}
            >
              Proceed to OCR →
            </Button>
          )}
        </div>
      </div>

      {/* Page Navigation Strip */}
      {pages.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-2 border-b border-zinc-900">
          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mr-1 flex-shrink-0">
            Pages:
          </span>
          {pages.map((p, idx) => {
            const count = panels.filter((pan) => pan.page_id === p.id).length;
            const isSelected = idx === selectedPageIndex;
            return (
              <button
                key={p.id}
                onClick={() => {
                  setSelectedPageIndex(idx);
                  setSelectedPanelId(null);
                  setSelectedForMerge([]);
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 flex-shrink-0 transition-all ${
                  isSelected
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800 border border-zinc-800"
                }`}
              >
                <span>Page #{p.sequence}</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${isSelected ? "bg-indigo-800" : "bg-zinc-800"}`}>
                  {count} panels
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Main Workspace Layout (Canvas + Inspector Sidebar) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Left / Center: Interactive Visual Page Canvas */}
        <div className="lg:col-span-2 space-y-3">
          {/* Canvas Toolbar */}
          <div className="flex items-center justify-between bg-zinc-900/80 border border-zinc-800 px-4 py-2 rounded-lg text-xs">
            <div className="flex items-center gap-2">
              <span className="text-zinc-400 font-medium">Page #{activePage?.sequence || 1}</span>
              <span className="text-zinc-600">|</span>
              <Button
                variant={isDrawMode ? "primary" : "ghost"}
                size="sm"
                onClick={() => setIsDrawMode(!isDrawMode)}
              >
                <Icons.Plus className="w-3.5 h-3.5 mr-1" />
                {isDrawMode ? "Drawing Active (Drag to draw)" : "Draw Panel"}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleDetectSinglePage}
                title="Detect panels on this page only"
              >
                <Icons.Rotate className="w-3 h-3 mr-1" />
                Redetect Page
              </Button>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowBoxes(!showBoxes)}
                className={`text-xs px-2 py-1 rounded transition-colors ${
                  showBoxes ? "text-indigo-400 bg-indigo-950/40" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {showBoxes ? "Boxes Visible" : "Boxes Hidden"}
              </button>
              <div className="flex items-center gap-1 text-zinc-400">
                <button
                  onClick={() => setZoomLevel((z) => Math.max(50, z - 25))}
                  className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700"
                >
                  -
                </button>
                <span className="font-mono text-[11px] w-12 text-center">{zoomLevel}%</span>
                <button
                  onClick={() => setZoomLevel((z) => Math.min(200, z + 25))}
                  className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700"
                >
                  +
                </button>
                <button
                  onClick={() => setZoomLevel(100)}
                  className="px-1.5 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px]"
                >
                  Fit
                </button>
              </div>
            </div>
          </div>

          {/* Canvas Viewport */}
          <Card className="p-4 bg-zinc-950 flex flex-col items-center justify-center min-h-[520px] overflow-auto">
            {activePage ? (
              <div
                className="relative inline-block max-w-full overflow-hidden rounded-lg shadow-2xl border border-zinc-800 transition-transform duration-150"
                style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "top center" }}
              >
                <img
                  src={`${api.getNormalizedPageImageUrl(project.id, activePage.id)}?t=${cacheBuster}`}
                  alt={`Page ${activePage.sequence}`}
                  className="max-h-[75vh] w-auto object-contain block pointer-events-none"
                />

                {/* SVG Overlay of detected panel bounding boxes */}
                {showBoxes && (
                  <svg
                    ref={svgRef}
                    className={`absolute inset-0 w-full h-full ${
                      isDrawMode ? "cursor-crosshair" : "cursor-default"
                    }`}
                    viewBox={`0 0 ${activePage.width || 1200} ${activePage.height || 1800}`}
                    preserveAspectRatio="none"
                    onMouseDown={handleSvgMouseDown}
                    onMouseMove={handleSvgMouseMove}
                    onMouseUp={handleSvgMouseUp}
                  >
                    {pagePanels.map((panel) => {
                      const isSelected = panel.id === selectedPanelId;
                      const isMergeSelected = selectedForMerge.includes(panel.id);
                      return (
                        <g
                          key={panel.id}
                          className="cursor-move"
                          onMouseDown={(e) => handleBoxMouseDown(e, panel)}
                        >
                          <rect
                            x={panel.x}
                            y={panel.y}
                            width={panel.width}
                            height={panel.height}
                            fill={
                              isSelected
                                ? "rgba(99, 102, 241, 0.28)"
                                : isMergeSelected
                                ? "rgba(234, 179, 8, 0.25)"
                                : "rgba(56, 189, 248, 0.12)"
                            }
                            stroke={isSelected ? "#818cf8" : isMergeSelected ? "#eab308" : "#38bdf8"}
                            strokeWidth={isSelected ? 6 : 3}
                            rx={4}
                            className="transition-all hover:fill-indigo-500/25"
                          />

                          {/* Sequence Badge Tag */}
                          <rect
                            x={panel.x}
                            y={Math.max(0, panel.y - 32)}
                            width={116}
                            height={30}
                            fill={isSelected ? "#4f46e5" : isMergeSelected ? "#ca8a04" : "#0284c7"}
                            rx={4}
                          />
                          <text
                            x={panel.x + 8}
                            y={Math.max(0, panel.y - 12)}
                            fill="#ffffff"
                            fontSize="17"
                            fontWeight="bold"
                            fontFamily="sans-serif"
                          >
                            #{panel.page_sequence} ({panel.sequence})
                          </text>

                          {/* 8 Resize Handles on Selected Panel */}
                          {isSelected && (
                            <>
                              <circle
                                cx={panel.x}
                                cy={panel.y}
                                r={8}
                                fill="#ffffff"
                                stroke="#4f46e5"
                                strokeWidth={3}
                                className="cursor-nwse-resize"
                                onMouseDown={(e) => handleResizeMouseDown(e, "nw", panel)}
                              />
                              <circle
                                cx={panel.x + panel.width}
                                cy={panel.y}
                                r={8}
                                fill="#ffffff"
                                stroke="#4f46e5"
                                strokeWidth={3}
                                className="cursor-nesw-resize"
                                onMouseDown={(e) => handleResizeMouseDown(e, "ne", panel)}
                              />
                              <circle
                                cx={panel.x + panel.width}
                                cy={panel.y + panel.height}
                                r={8}
                                fill="#ffffff"
                                stroke="#4f46e5"
                                strokeWidth={3}
                                className="cursor-nwse-resize"
                                onMouseDown={(e) => handleResizeMouseDown(e, "se", panel)}
                              />
                              <circle
                                cx={panel.x}
                                cy={panel.y + panel.height}
                                r={8}
                                fill="#ffffff"
                                stroke="#4f46e5"
                                strokeWidth={3}
                                className="cursor-nesw-resize"
                                onMouseDown={(e) => handleResizeMouseDown(e, "sw", panel)}
                              />
                            </>
                          )}
                        </g>
                      );
                    })}

                    {/* Temporary Drag-to-Draw Rectangle Preview */}
                    {dragMode === "draw" && drawCurrent && (
                      <rect
                        x={drawCurrent.x}
                        y={drawCurrent.y}
                        width={drawCurrent.w}
                        height={drawCurrent.h}
                        fill="rgba(99, 102, 241, 0.3)"
                        stroke="#6366f1"
                        strokeWidth={3}
                        strokeDasharray="6 4"
                      />
                    )}
                  </svg>
                )}
              </div>
            ) : (
              <div className="text-zinc-500 text-sm">No page selected</div>
            )}
          </Card>

          {/* Reading Order Timeline Bar */}
          {pagePanels.length > 0 && (
            <Card className="p-3 bg-zinc-900/60 border border-zinc-800">
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800 text-xs">
                <span className="font-semibold text-zinc-300 uppercase tracking-wider">
                  Reading Order Timeline (Page #{activePage?.sequence})
                </span>
                <span className="text-zinc-500 font-mono">{pagePanels.length} Panels</span>
              </div>
              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                {pagePanels.map((p, idx) => {
                  const isSelected = p.id === selectedPanelId;
                  return (
                    <div key={p.id} className="flex items-center gap-1.5 flex-shrink-0">
                      <button
                        onClick={() => setSelectedPanelId(p.id)}
                        className={`px-3 py-1.5 rounded text-xs font-bold transition-all flex items-center gap-1.5 ${
                          isSelected
                            ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30 ring-1 ring-white"
                            : "bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
                        }`}
                      >
                        <span>P-{p.page_sequence}</span>
                        <span className="text-[10px] font-normal opacity-75">#{p.sequence}</span>
                      </button>
                      {idx < pagePanels.length - 1 && (
                        <Icons.ArrowRight className="w-3 h-3 text-zinc-600 flex-shrink-0" />
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </div>

        {/* Right Sidebar: Panel Inspector & Actions */}
        <div className="space-y-4">
          {selectedPanel ? (
            <Card className="p-4 space-y-4 border-indigo-500/50 bg-indigo-950/10">
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                <div>
                  <h3 className="font-bold text-zinc-100 text-base">
                    Panel #{selectedPanel.page_sequence}
                  </h3>
                  <span className="text-xs text-zinc-400 font-mono">
                    Global sequence: #{selectedPanel.sequence}
                  </span>
                </div>
                <Badge variant={selectedPanel.status === "MANUAL" ? "accent" : "success"}>
                  {selectedPanel.status}
                </Badge>
              </div>

              {/* Crop Preview */}
              <div className="w-full h-36 bg-zinc-950 rounded-lg border border-zinc-800 flex items-center justify-center overflow-hidden">
                <img
                  src={`${api.getPanelImageUrl(project.id, selectedPanel.id)}?t=${cacheBuster}`}
                  alt={`Panel ${selectedPanel.sequence}`}
                  className="w-full h-full object-contain"
                />
              </div>

              {/* Coordinates Grid */}
              <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-zinc-900/60 p-2.5 rounded border border-zinc-800/80">
                <div>X: <span className="text-zinc-200">{selectedPanel.x}</span></div>
                <div>Y: <span className="text-zinc-200">{selectedPanel.y}</span></div>
                <div>Width: <span className="text-zinc-200">{selectedPanel.width}px</span></div>
                <div>Height: <span className="text-zinc-200">{selectedPanel.height}px</span></div>
                <div className="col-span-2 text-[10px] text-zinc-400 pt-1 border-t border-zinc-800">
                  Normalized: [{selectedPanel.normalized_x ?? 0}, {selectedPanel.normalized_y ?? 0}]
                </div>
              </div>

              {/* Split & Merge Operations */}
              <div className="space-y-2 pt-2 border-t border-zinc-800">
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400 block">
                  Actions
                </span>
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="outline" size="sm" onClick={() => handleSplit("horizontal")}>
                    Split Horizontal
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleSplit("vertical")}>
                    Split Vertical
                  </Button>
                </div>
                <Button variant="secondary" size="sm" className="w-full" onClick={handleMarkFullPage}>
                  Mark as Full Page
                </Button>
                {selectedForMerge.length >= 2 && (
                  <Button variant="primary" size="sm" className="w-full" onClick={handleMerge}>
                    Merge Selected ({selectedForMerge.length})
                  </Button>
                )}
              </div>

              {/* Delete Button */}
              <Button
                variant="destructive"
                size="sm"
                className="w-full"
                onClick={() => handleDeletePanel(selectedPanel.id)}
              >
                <Icons.Trash className="w-3.5 h-3.5 mr-1" />
                Delete Panel
              </Button>
            </Card>
          ) : (
            <Card className="p-6 text-center text-zinc-500 text-xs border-dashed space-y-2">
              <p>No panel selected.</p>
              <p className="text-zinc-400">Click a bounding box on the canvas or click &quot;Draw Panel&quot; to create one.</p>
            </Card>
          )}

          {/* Page Panels List & Reorder */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
                Page Panels ({pagePanels.length})
              </h3>
              <Button variant="outline" size="sm" onClick={() => setIsAddModalOpen(true)}>
                <Icons.Plus className="w-3 h-3 mr-1" />
                Add Coordinates
              </Button>
            </div>

            <div className="space-y-2 max-h-[46vh] overflow-y-auto pr-1">
              {pagePanels.map((panel, idx) => {
                const isSelected = panel.id === selectedPanelId;
                return (
                  <div
                    key={panel.id}
                    className={`p-2.5 rounded-lg border flex items-center justify-between transition-all cursor-pointer ${
                      isSelected
                        ? "border-indigo-500 bg-indigo-950/20"
                        : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-700"
                    }`}
                    onClick={() => setSelectedPanelId(panel.id)}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className="w-6 h-6 rounded bg-zinc-800 flex items-center justify-center font-bold text-xs text-zinc-300 flex-shrink-0">
                        {panel.page_sequence}
                      </span>
                      <div className="truncate text-xs">
                        <div className="font-medium text-zinc-200">
                          Panel #{panel.page_sequence}
                        </div>
                        <div className="text-[10px] text-zinc-500 font-mono">
                          {panel.width}x{panel.height} px
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={idx === 0}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleReorder(idx, "up");
                        }}
                        title="Move Earlier"
                      >
                        <Icons.ArrowLeft className="w-3 h-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={idx === pagePanels.length - 1}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleReorder(idx, "down");
                        }}
                        title="Move Later"
                      >
                        <Icons.ArrowRight className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Manual Add Panel Modal */}
      {isAddModalOpen && (
        <Modal
          isOpen={isAddModalOpen}
          onClose={() => setIsAddModalOpen(false)}
          title={`Add Panel Coordinates (Page #${activePage?.sequence || 1})`}
        >
          <form onSubmit={handleAddManualPanel} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="X Coordinate"
                type="number"
                value={manualX}
                onChange={(e) => setManualX(Number(e.target.value))}
                required
              />
              <Input
                label="Y Coordinate"
                type="number"
                value={manualY}
                onChange={(e) => setManualY(Number(e.target.value))}
                required
              />
              <Input
                label="Width (px)"
                type="number"
                value={manualW}
                onChange={(e) => setManualW(Number(e.target.value))}
                required
              />
              <Input
                label="Height (px)"
                type="number"
                value={manualH}
                onChange={(e) => setManualH(Number(e.target.value))}
                required
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setIsAddModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary">
                Add Panel Box
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};
