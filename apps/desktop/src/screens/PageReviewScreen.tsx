import React, { useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { Project, Page, AcquisitionManifest } from "@panelflow/shared-types";
import { Button, Card, Badge, Modal, Icons } from "@panelflow/ui";
import { useError } from "../context/ErrorContext";

interface PageReviewScreenProps {
  project: Project;
  onBack: () => void;
  onAcquisitionConfirmed: (updatedProject: Project) => void;
  onProceedToPanels?: (project: Project) => void;
}

export const PageReviewScreen: React.FC<PageReviewScreenProps> = ({
  project,
  onBack,
  onAcquisitionConfirmed,
  onProceedToPanels,
}) => {
  const { reportError, inspectError } = useError();
  const [pages, setPages] = useState<Page[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [confirming, setConfirming] = useState<boolean>(false);
  const [inspectPage, setInspectPage] = useState<Page | null>(null);
  const [draggedPageIndex, setDraggedPageIndex] = useState<number | null>(null);
  const [dragOverPageIndex, setDragOverPageIndex] = useState<number | null>(null);
  const [manifest, setManifest] = useState<AcquisitionManifest | null>(null);
  const [showManifestModal, setShowManifestModal] = useState<boolean>(false);
  const [cacheBuster, setCacheBuster] = useState<number>(Date.now());

  const loadPages = async () => {
    try {
      setLoading(true);
      const data = await api.listPages(project.id);
      setPages(data);
    } catch (err: any) {
      reportError({
        title: "Failed to Load Pages",
        message: err.message || "Failed to load project pages.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPages();
  }, [project.id]);

  const handlePageDragStart = (e: React.DragEvent, index: number) => {
    e.dataTransfer.setData("application/panelflow-page-reorder", JSON.stringify({ fromIndex: index }));
    e.dataTransfer.effectAllowed = "move";
    setDraggedPageIndex(index);
  };

  const handlePageDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (index !== draggedPageIndex) setDragOverPageIndex(index);
  };

  const handlePageDragLeave = (e: React.DragEvent, index: number) => {
    if (dragOverPageIndex === index) setDragOverPageIndex(null);
  };

  const handlePageDrop = async (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    setDragOverPageIndex(null);
    setDraggedPageIndex(null);
    try {
      const reorderData = e.dataTransfer.getData("application/panelflow-page-reorder");
      if (!reorderData) return;
      const { fromIndex } = JSON.parse(reorderData);
      if (fromIndex === targetIndex) return;

      const newPages = [...pages];
      const [moved] = newPages.splice(fromIndex, 1);
      newPages.splice(targetIndex, 0, moved);

      const pageIds = newPages.map((p) => p.id);
      const updated = await api.reorderPages(project.id, pageIds);
      setPages(updated);
    } catch (err: any) {
      reportError({
        title: "Page Reordering Failed",
        message: err.message || "Failed to reorder pages.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
      loadPages();
    }
  };

  const handleMove = async (index: number, direction: "left" | "right") => {
    const targetIndex = direction === "left" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= pages.length) return;

    const newPages = [...pages];
    const [moved] = newPages.splice(index, 1);
    newPages.splice(targetIndex, 0, moved);

    // Optimistic UI update
    setPages(newPages);

    try {
      const pageIds = newPages.map((p) => p.id);
      const updated = await api.reorderPages(project.id, pageIds);
      setPages(updated);
    } catch (err: any) {
      reportError({
        title: "Page Reorder Failed",
        message: err.message || "Failed to save reordered pages.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
      loadPages();
    }
  };

  const handleRotate = async (page: Page) => {
    try {
      const updated = await api.rotatePage(project.id, page.id, 90);
      setPages((prev) =>
        prev.map((p) => (p.id === page.id ? updated : p))
      );
      if (inspectPage && inspectPage.id === page.id) {
        setInspectPage(updated);
      }
      setCacheBuster(Date.now());
    } catch (err: any) {
      reportError({
        title: "Page Rotation Failed",
        message: err.message || `Failed to rotate page ${page.sequence}.`,
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: { pageId: page.id, error: err },
      });
    }
  };

  const [viewMode, setViewMode] = useState<"fit-width" | "fit-page" | "original">("fit-width");
  const [zoomScale, setZoomScale] = useState<number>(100);

  const openInspectModal = (page: Page) => {
    setInspectPage(page);
    if (page.height > page.width * 1.8) {
      setViewMode("fit-width");
    } else {
      setViewMode("fit-page");
    }
    setZoomScale(100);
  };

  const currentInspectIndex = inspectPage ? pages.findIndex((p) => p.id === inspectPage.id) : -1;

  const handlePrevInspect = () => {
    if (currentInspectIndex > 0) {
      const prev = pages[currentInspectIndex - 1];
      setInspectPage(prev);
      if (prev.height > prev.width * 1.8) {
        setViewMode("fit-width");
      } else {
        setViewMode("fit-page");
      }
      setZoomScale(100);
    }
  };

  const handleNextInspect = () => {
    if (currentInspectIndex >= 0 && currentInspectIndex < pages.length - 1) {
      const next = pages[currentInspectIndex + 1];
      setInspectPage(next);
      if (next.height > next.width * 1.8) {
        setViewMode("fit-width");
      } else {
        setViewMode("fit-page");
      }
      setZoomScale(100);
    }
  };

  useEffect(() => {
    if (!inspectPage) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        handlePrevInspect();
      } else if (e.key === "ArrowRight") {
        handleNextInspect();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [inspectPage, currentInspectIndex, pages]);

  const handleDelete = async (page: Page) => {
    if (!window.confirm(`Delete page #${page.sequence}? This will resequence remaining pages.`)) {
      return;
    }
    try {
      await api.deletePage(project.id, page.id);
      await loadPages();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const [retrying, setRetrying] = useState<boolean>(false);

  const handleRetryFailed = async () => {
    setRetrying(true);
    try {
      const res = await api.retryFailedPages(project.id);
      if (res.job_id) {
        for (let i = 0; i < 45; i++) {
          await new Promise((r) => setTimeout(r, 1000));
          const job = await api.getJob(res.job_id);
          if (job.status === "SUCCEEDED" || job.status === "FAILED") {
            break;
          }
        }
      }
      await loadPages();
      setCacheBuster(Date.now());
    } catch (err: any) {
      reportError({
        title: "Page Download Retry Failed",
        message: err.message || "Failed to retry downloading failed pages.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        jobType: "ACQUISITION",
        rawDetails: err,
      });
    } finally {
      setRetrying(false);
    }
  };

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      const updated = await api.confirmAcquisition(project.id);
      onAcquisitionConfirmed(updated);
    } catch (err: any) {
      reportError({
        title: "Acquisition Confirmation Failed",
        message: err.message || "Could not confirm page acquisition manifest.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setConfirming(false);
    }
  };

  const handleViewManifest = async () => {
    try {
      const m = await api.getManifest(project.id);
      setManifest(m);
      setShowManifestModal(true);
    } catch (err: any) {
      reportError({
        title: "Could Not Fetch Manifest",
        message: err.message || "Failed to load acquisition manifest.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    }
  };

  const readyPages = pages.filter((p) => p.status === "READY");

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-16">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <Icons.ArrowLeft className="w-4 h-4" />
            Back
          </Button>
          <div>
            <h2 className="text-xl font-bold text-zinc-100">Page Review & Sequencing</h2>
            <p className="text-xs text-zinc-400">
              Confirm deterministic order, rotate misoriented scans, or remove blank pages.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {pages.some((p) => p.status === "FAILED") && (
            <Button
              variant="destructive"
              size="md"
              onClick={handleRetryFailed}
              loading={retrying}
            >
              <Icons.Refresh className={`w-4 h-4 mr-1 ${retrying ? "animate-spin" : ""}`} />
              Retry Failed Pages ({pages.filter((p) => p.status === "FAILED").length})
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={handleViewManifest}>
            Inspect Manifest
          </Button>
          <Button
            variant="secondary"
            size="md"
            onClick={handleConfirm}
            loading={confirming}
            disabled={readyPages.length === 0}
          >
            <Icons.CheckCircle className="w-4 h-4 text-emerald-400" />
            Confirm Acquisition ({readyPages.length} Pages)
          </Button>
          {onProceedToPanels && (
            <Button
              variant="primary"
              size="md"
              onClick={() => onProceedToPanels(project)}
              disabled={readyPages.length === 0}
            >
              Detect Panels →
            </Button>
          )}
        </div>
      </div>

      {/* Pages Grid */}
      {loading ? (
        <div className="py-24 text-center text-zinc-400">Loading pages...</div>
      ) : pages.length === 0 ? (
        <Card className="text-center py-16 text-zinc-400 border-dashed">
          No pages found in this project.
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
          {pages.map((p, idx) => {
            const isFirst = idx === 0;
            const isLast = idx === pages.length - 1;
            const isFailed = p.status === "FAILED";

            return (
              <Card
                key={p.id}
                className={`p-3 space-y-3 flex flex-col justify-between transition-all ${
                  isFailed ? "border-rose-800 bg-rose-950/20" : "border-zinc-800 hover:border-zinc-700"
                }`}
              >
                {/* Image Container */}
                <div
                  className="aspect-[3/4] w-full bg-zinc-950 rounded-lg overflow-hidden relative cursor-pointer group flex items-center justify-center"
                  onClick={() => !isFailed && openInspectModal(p)}
                >
                  {isFailed ? (
                    <div className="p-4 text-center space-y-2">
                      <Icons.AlertTriangle className="w-8 h-8 text-rose-500 mx-auto" />
                      <p className="text-xs text-rose-300 font-semibold">Image Failed</p>
                      <p className="text-[10px] text-zinc-400 line-clamp-3">{p.error_message}</p>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRetryFailed();
                        }}
                        loading={retrying}
                        className="mt-2 text-xs"
                      >
                        <Icons.Refresh className={`w-3 h-3 mr-1 ${retrying ? "animate-spin" : ""}`} />
                        Retry
                      </Button>
                    </div>
                  ) : (
                    <>
                      <img
                        src={`${api.getPageImageUrl(project.id, p.id)}?t=${cacheBuster}`}
                        alt={`Page ${p.sequence}`}
                        className={`w-full h-full ${
                          p.height > p.width * 2 ? "object-cover object-top" : "object-contain"
                        }`}
                        loading="lazy"
                      />
                      {p.height > p.width * 2 && (
                        <>
                          <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-black/80 to-transparent pointer-events-none" />
                          <span className="absolute top-2 right-2 bg-indigo-950/80 text-indigo-300 border border-indigo-700/60 px-1.5 py-0.5 rounded text-[10px] font-semibold">
                            Strip
                          </span>
                        </>
                      )}
                      <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <span className="text-xs bg-zinc-900/90 text-zinc-200 px-3 py-1.5 rounded-full border border-zinc-700">
                          {p.height > p.width * 2 ? "Click to view full strip" : "Click to inspect"}
                        </span>
                      </div>
                    </>
                  )}

                  <div className="absolute top-2 left-2 bg-zinc-900/90 backdrop-blur-md px-2 py-0.5 rounded text-xs font-bold text-zinc-100 border border-zinc-700">
                    #{p.sequence}
                  </div>
                </div>

                {/* Metadata */}
                <div className="text-[11px] text-zinc-400 space-y-0.5">
                  <div className="flex justify-between font-mono">
                    <span className="text-zinc-500">Dimensions:</span>
                    <span>{p.width > 0 ? `${p.width}x${p.height} px` : "N/A"}</span>
                  </div>
                  <div className="flex justify-between font-mono">
                    <span className="text-zinc-500">File size:</span>
                    <span>{(p.byte_size / 1024).toFixed(1)} KB</span>
                  </div>
                </div>

                {/* Card Controls */}
                <div className="pt-2 border-t border-zinc-800/80 flex items-center justify-between">
                  {/* Drag handle for reorder */}
                  <div className="flex items-center gap-1">
                    <div
                      draggable
                      onDragStart={(e) => handlePageDragStart(e, idx)}
                      onDragOver={(e) => handlePageDragOver(e, idx)}
                      onDragLeave={(e) => handlePageDragLeave(e, idx)}
                      onDrop={(e) => handlePageDrop(e, idx)}
                      className="flex items-center gap-1"
                    >
                      <div
                        className={`w-6 h-6 flex items-center justify-center cursor-grab active:cursor-grabbing rounded $\{
                          draggedPageIndex === idx
                            ? 'bg-indigo-900/50 border-indigo-400'
                            : dragOverPageIndex === idx
                            ? 'bg-indigo-900/30 border-indigo-400'
                            : 'bg-zinc-800 border-zinc-700 hover:bg-zinc-700'
                        \}`}
                        title="Drag to reorder"
                      >
                        <Icons.GripVertical className="w-3.5 h-3.5 text-zinc-400" />
                      </div>
                    </div>
                  </div>

                  {/* Rotate and Delete */}
                  <div className="flex items-center gap-1">
                    {!isFailed && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRotate(p)}
                        title="Rotate 90 degrees clockwise"
                      >
                        <Icons.Rotate className="w-3.5 h-3.5" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-rose-400 hover:text-rose-300"
                      onClick={() => handleDelete(p)}
                      title="Remove page"
                    >
                      <Icons.Trash className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Page Inspection Modal */}
      {inspectPage && (
        <Modal
          isOpen={!!inspectPage}
          onClose={() => setInspectPage(null)}
          title={`Page #${inspectPage.sequence} of ${pages.length} — Inspection`}
          size="5xl"
        >
          <div className="space-y-3">
            {/* Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-950/80 p-2.5 rounded-lg border border-zinc-800 text-xs">
              {/* Navigation */}
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handlePrevInspect}
                  disabled={currentInspectIndex <= 0}
                  title="Previous Page (Left Arrow)"
                >
                  <Icons.ArrowLeft className="w-3.5 h-3.5 mr-1" />
                  Prev
                </Button>
                <span className="px-2 font-mono font-medium text-zinc-300">
                  {currentInspectIndex + 1} / {pages.length}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleNextInspect}
                  disabled={currentInspectIndex >= pages.length - 1}
                  title="Next Page (Right Arrow)"
                >
                  Next
                  <Icons.ArrowRight className="w-3.5 h-3.5 ml-1" />
                </Button>
              </div>

              {/* View Mode Switcher */}
              <div className="flex items-center bg-zinc-900 rounded-lg p-0.5 border border-zinc-800">
                <button
                  type="button"
                  onClick={() => {
                    setViewMode("fit-width");
                    setZoomScale(100);
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    viewMode === "fit-width"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title="Fit Width — scroll vertically through full strip"
                >
                  Fit Width
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setViewMode("fit-page");
                    setZoomScale(100);
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    viewMode === "fit-page"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title="Fit Height — view entire sheet in window"
                >
                  Fit Height
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setViewMode("original");
                    setZoomScale(100);
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    viewMode === "original"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title="1:1 Native Resolution"
                >
                  100%
                </button>
              </div>

              {/* Zoom & Action Controls */}
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setZoomScale((s) => Math.max(25, s - 25))}
                  title="Zoom Out"
                >
                  <Icons.ZoomOut className="w-3.5 h-3.5" />
                </Button>
                <button
                  type="button"
                  onClick={() => setZoomScale(100)}
                  className="px-2 font-mono text-zinc-300 hover:text-white transition-colors text-xs"
                  title="Reset to 100%"
                >
                  {zoomScale}%
                </button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setZoomScale((s) => Math.min(300, s + 25))}
                  title="Zoom In"
                >
                  <Icons.ZoomIn className="w-3.5 h-3.5" />
                </Button>

                <div className="h-4 w-px bg-zinc-800 mx-1" />

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleRotate(inspectPage)}
                  title="Rotate 90 degrees clockwise"
                >
                  <Icons.Rotate className="w-3.5 h-3.5 mr-1" />
                  Rotate
                </Button>
              </div>
            </div>

            {/* Scrollable Canvas Viewport */}
            <div className="h-[65vh] bg-zinc-950 rounded-lg overflow-auto border border-zinc-800 p-4 relative flex justify-center items-start">
              {viewMode === "fit-width" ? (
                <div
                  className="transition-all duration-150 mx-auto"
                  style={{ width: `${zoomScale}%`, maxWidth: "none" }}
                >
                  <img
                    src={`${api.getPageImageUrl(project.id, inspectPage.id)}?t=${cacheBuster}`}
                    alt={`Page ${inspectPage.sequence}`}
                    className="w-full h-auto block rounded shadow-2xl"
                  />
                </div>
              ) : viewMode === "fit-page" ? (
                <div className="flex items-center justify-center min-h-full w-full">
                  <img
                    src={`${api.getPageImageUrl(project.id, inspectPage.id)}?t=${cacheBuster}`}
                    alt={`Page ${inspectPage.sequence}`}
                    style={{
                      maxHeight: `${Math.round(58 * (zoomScale / 100))}vh`,
                      maxWidth: `${zoomScale}%`,
                    }}
                    className="w-auto h-auto object-contain block rounded shadow-2xl"
                  />
                </div>
              ) : (
                <div
                  className="transition-all duration-150 mx-auto"
                  style={{
                    width: `${Math.round(inspectPage.width * (zoomScale / 100))}px`,
                    maxWidth: "none",
                  }}
                >
                  <img
                    src={`${api.getPageImageUrl(project.id, inspectPage.id)}?t=${cacheBuster}`}
                    alt={`Page ${inspectPage.sequence}`}
                    className="w-full h-auto block rounded shadow-2xl"
                  />
                </div>
              )}
            </div>

            {/* Metadata Footer */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono bg-zinc-950/80 p-3 rounded-lg border border-zinc-800">
              <div>
                <span className="text-zinc-500 block text-[10px]">Filename:</span>
                <span className="text-zinc-200 truncate block" title={inspectPage.filename}>
                  {inspectPage.filename}
                </span>
              </div>
              <div>
                <span className="text-zinc-500 block text-[10px]">Resolution:</span>
                <span className="text-zinc-200">
                  {inspectPage.width} × {inspectPage.height} px
                </span>
              </div>
              <div>
                <span className="text-zinc-500 block text-[10px]">Aspect Ratio:</span>
                <span className="text-zinc-200">
                  1:{(inspectPage.height / (inspectPage.width || 1)).toFixed(1)}{" "}
                  <span className="text-zinc-400 font-sans text-[10px]">
                    {inspectPage.height > inspectPage.width * 2 ? "(Webtoon Strip)" : "(Standard)"}
                  </span>
                </span>
              </div>
              <div>
                <span className="text-zinc-500 block text-[10px]">File Size:</span>
                <span className="text-zinc-200">
                  {(inspectPage.byte_size / (1024 * 1024)).toFixed(2)} MB
                </span>
              </div>
            </div>
          </div>
        </Modal>
      )}

      {/* Manifest Modal */}
      {showManifestModal && manifest && (
        <Modal
          isOpen={showManifestModal}
          onClose={() => setShowManifestModal(false)}
          title="Acquisition Manifest (manifest.json)"
        >
          <div className="space-y-3">
            <p className="text-xs text-zinc-400">
              Machine-readable JSON manifest stored at <code>projects/{project.id}/manifest.json</code>.
            </p>
            <pre className="bg-zinc-950 border border-zinc-800 p-4 rounded-lg text-xs font-mono text-zinc-300 max-h-[60vh] overflow-auto">
              {JSON.stringify(manifest, null, 2)}
            </pre>
          </div>
        </Modal>
      )}
    </div>
  );
};
