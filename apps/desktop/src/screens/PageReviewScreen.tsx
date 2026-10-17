import React, { useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { Project, Page, AcquisitionManifest } from "@panelflow/shared-types";
import { Button, Card, Badge, Modal, Icons } from "@panelflow/ui";

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
  const [pages, setPages] = useState<Page[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [confirming, setConfirming] = useState<boolean>(false);
  const [inspectPage, setInspectPage] = useState<Page | null>(null);
  const [manifest, setManifest] = useState<AcquisitionManifest | null>(null);
  const [showManifestModal, setShowManifestModal] = useState<boolean>(false);
  const [cacheBuster, setCacheBuster] = useState<number>(Date.now());

  const loadPages = async () => {
    try {
      setLoading(true);
      const data = await api.listPages(project.id);
      setPages(data);
    } catch (err: any) {
      alert(`Failed to load pages: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPages();
  }, [project.id]);

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
      alert(`Reordering failed: ${err.message}`);
      loadPages();
    }
  };

  const handleRotate = async (page: Page) => {
    try {
      const updated = await api.rotatePage(project.id, page.id, 90);
      setPages((prev) =>
        prev.map((p) => (p.id === page.id ? updated : p))
      );
      setCacheBuster(Date.now());
    } catch (err: any) {
      alert(`Rotate failed: ${err.message}`);
    }
  };

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

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      const updated = await api.confirmAcquisition(project.id);
      alert("Acquisition confirmed! Canonical manifest written and stage set to ACQUIRED.");
      onAcquisitionConfirmed(updated);
    } catch (err: any) {
      alert(`Confirmation failed: ${err.message}`);
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
      alert(`Could not fetch manifest: ${err.message}`);
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
                  onClick={() => !isFailed && setInspectPage(p)}
                >
                  {isFailed ? (
                    <div className="p-4 text-center space-y-2">
                      <Icons.AlertTriangle className="w-8 h-8 text-rose-500 mx-auto" />
                      <p className="text-xs text-rose-300 font-semibold">Image Failed</p>
                      <p className="text-[10px] text-zinc-400 line-clamp-3">{p.error_message}</p>
                    </div>
                  ) : (
                    <>
                      <img
                        src={`${api.getPageImageUrl(project.id, p.id)}?t=${cacheBuster}`}
                        alt={`Page ${p.sequence}`}
                        className="w-full h-full object-contain"
                        loading="lazy"
                      />
                      <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <span className="text-xs bg-zinc-900/90 text-zinc-200 px-3 py-1.5 rounded-full border border-zinc-700">
                          Click to inspect
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
                  {/* Sequence reorder buttons */}
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleMove(idx, "left")}
                      disabled={isFirst}
                      title="Move earlier"
                    >
                      <Icons.ArrowLeft className="w-3.5 h-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleMove(idx, "right")}
                      disabled={isLast}
                      title="Move later"
                    >
                      <Icons.ArrowRight className="w-3.5 h-3.5" />
                    </Button>
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
          title={`Page #${inspectPage.sequence} Details`}
        >
          <div className="space-y-4">
            <div className="max-h-[60vh] bg-zinc-950 rounded-lg overflow-auto flex items-center justify-center p-2 border border-zinc-800">
              <img
                src={`${api.getPageImageUrl(project.id, inspectPage.id)}?t=${cacheBuster}`}
                alt={`Page ${inspectPage.sequence}`}
                className="max-h-[55vh] object-contain"
              />
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs font-mono bg-zinc-950 p-3 rounded-lg border border-zinc-800">
              <div>
                <span className="text-zinc-500 block">Filename:</span>
                <span className="text-zinc-200">{inspectPage.filename}</span>
              </div>
              <div>
                <span className="text-zinc-500 block">Resolution:</span>
                <span className="text-zinc-200">{inspectPage.width} x {inspectPage.height}</span>
              </div>
              <div className="col-span-2">
                <span className="text-zinc-500 block">SHA-256 Digest:</span>
                <span className="text-zinc-200 text-[10px] break-all">{inspectPage.sha256}</span>
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
