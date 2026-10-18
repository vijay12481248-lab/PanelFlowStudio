import React, { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@panelflow/api-client";
import type {
  Project,
  Panel,
  OCRRecord,
  OCREngineInfo,
  TextRegion,
  TextRegionType,
  TextRegionStatus,
} from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons } from "@panelflow/ui";

interface OCRReviewScreenProps {
  project: Project;
  onBack: () => void;
  onOCRApproved: (updatedProject: Project) => void;
  onProceedToStory?: (project: Project) => void;
  onOpenStoryEditor?: (project: Project) => void;
}

export const OCRReviewScreen: React.FC<OCRReviewScreenProps> = ({
  project,
  onBack,
  onOCRApproved,
  onProceedToStory,
  onOpenStoryEditor,
}) => {
  const [panels, setPanels] = useState<Panel[]>([]);
  const [selectedPanelIndex, setSelectedPanelIndex] = useState<number>(0);
  const [ocrRecords, setOcrRecords] = useState<Record<string, OCRRecord>>({});
  const [textRegions, setTextRegions] = useState<TextRegion[]>([]);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [reviewFlagged, setReviewFlagged] = useState(false);

  const [engines, setEngines] = useState<OCREngineInfo[]>([]);
  const [selectedEngine, setSelectedEngine] = useState<string>("mock_ocr");

  const [loading, setLoading] = useState<boolean>(true);
  const [extracting, setExtracting] = useState<boolean>(false);
  const [detectingRegions, setDetectingRegions] = useState<boolean>(false);
  const [confirming, setConfirming] = useState<boolean>(false);
  const [singleOcrLoading, setSingleOcrLoading] = useState<boolean>(false);

  const [ocrProgress, setOcrProgress] = useState<number>(0);
  const [progressMsg, setProgressMsg] = useState<string>("");
  const [cacheBuster, setCacheBuster] = useState<number>(Date.now());

  // Undo / Redo history stack for Text Regions
  const [undoStack, setUndoStack] = useState<TextRegion[][]>([]);
  const [redoStack, setRedoStack] = useState<TextRegion[][]>([]);

  // Selected Region Form State
  const [editForm, setEditForm] = useState<{
    corrected_text: string;
    region_type: string;
    speaker_character_id: string;
    speaker_assignment_method: string;
    status: string;
  }>({
    corrected_text: "",
    region_type: "SPEECH",
    speaker_character_id: "",
    speaker_assignment_method: "MANUAL",
    status: "CONFIRMED",
  });
  const [savingRegion, setSavingRegion] = useState<boolean>(false);

  const activePanel = panels[selectedPanelIndex] || null;
  const activeOCR = activePanel ? ocrRecords[activePanel.id] : null;

  const panelRegions = activePanel
    ? textRegions
        .filter((tr) => tr.panel_id === activePanel.id)
        .sort((a, b) => a.sequence_in_panel - b.sequence_in_panel)
    : [];

  const selectedRegion = textRegions.find((tr) => tr.id === selectedRegionId) || null;
  const needsReviewCount = textRegions.filter((tr) => tr.status === "NEEDS_REVIEW").length;

  const pushUndo = useCallback((currentRegions: TextRegion[]) => {
    setUndoStack((prev) => [...prev.slice(-25), currentRegions]);
    setRedoStack([]);
  }, []);

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return;
    const previous = undoStack[undoStack.length - 1];
    setUndoStack((prev) => prev.slice(0, -1));
    setRedoStack((prev) => [...prev, textRegions]);
    setTextRegions(previous);
  }, [undoStack, textRegions]);

  const handleRedo = useCallback(() => {
    if (redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    setRedoStack((prev) => prev.slice(0, -1));
    setUndoStack((prev) => [...prev, textRegions]);
    setTextRegions(next);
  }, [redoStack, textRegions]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [panelList, engineList, ocrList, regionsList] = await Promise.all([
        api.listPanels(project.id),
        api.listOCREngines(),
        api.listProjectOCR(project.id),
        api.listTextRegions(project.id),
      ]);

      setPanels(panelList);
      setEngines(engineList);
      if (engineList.length > 0) {
        const preferred = engineList.find((e) => e.engine_id === "windows_media" && e.is_available)
          || engineList.find((e) => e.is_available)
          || engineList[0];
        if (preferred) {
          setSelectedEngine(preferred.engine_id);
        }
      }
      setTextRegions(regionsList);

      const ocrMap: Record<string, OCRRecord> = {};
      ocrList.forEach((r) => {
        ocrMap[r.panel_id] = r;
      });
      setOcrRecords(ocrMap);

      if (regionsList.length > 0 && !selectedRegionId) {
        setSelectedRegionId(regionsList[0].id);
      }
    } catch (err: any) {
      alert(`Failed to load OCR data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [project.id]);

  // Sync selected region with edit form
  useEffect(() => {
    if (selectedRegion) {
      setEditForm({
        corrected_text: selectedRegion.corrected_text || selectedRegion.raw_text || "",
        region_type: selectedRegion.region_type || "SPEECH",
        speaker_character_id: selectedRegion.speaker_character_id || "",
        speaker_assignment_method: selectedRegion.speaker_assignment_method || "MANUAL",
        status: selectedRegion.status || "CONFIRMED",
      });
    }
  }, [selectedRegion?.id]);

  // Keyboard navigation & Shortcuts (Ctrl+Z / Ctrl+Shift+Z / Bracket navigation)
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
      } else if (e.key === "[" || (e.shiftKey && e.key === "Tab")) {
        e.preventDefault();
        if (panelRegions.length > 0) {
          const currIdx = panelRegions.findIndex((r) => r.id === selectedRegionId);
          const prevIdx = currIdx > 0 ? currIdx - 1 : panelRegions.length - 1;
          setSelectedRegionId(panelRegions[prevIdx].id);
        }
      } else if (e.key === "]" || (!e.shiftKey && e.key === "Tab")) {
        e.preventDefault();
        if (panelRegions.length > 0) {
          const currIdx = panelRegions.findIndex((r) => r.id === selectedRegionId);
          const nextIdx = currIdx >= 0 && currIdx < panelRegions.length - 1 ? currIdx + 1 : 0;
          setSelectedRegionId(panelRegions[nextIdx].id);
        }
      } else if (e.key === "Escape") {
        setSelectedRegionId(null);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [panelRegions, selectedRegionId, handleUndo, handleRedo]);

  const handleDetectRegions = async () => {
    setDetectingRegions(true);
    try {
      pushUndo(textRegions);
      const created = await api.detectTextRegions(project.id);
      setTextRegions(created);
      if (created.length > 0) {
        setSelectedRegionId(created[0].id);
      }
      setCacheBuster(Date.now());
      alert(`Detected ${created.length} text regions across all panels.`);
    } catch (err: any) {
      alert(`Text region detection failed: ${err.message}`);
    } finally {
      setDetectingRegions(false);
    }
  };

  const handleRunProjectOCR = async () => {
    const activeEng = engines.find((e) => e.engine_id === selectedEngine);
    if (activeEng && !activeEng.is_available) {
      alert(`Cannot run OCR with ${activeEng.display_name}: ${activeEng.diagnostic_message || "Configuration required."}`);
      return;
    }

    setExtracting(true);
    setOcrProgress(0);
    setProgressMsg("Queuing OCR extraction job...");

    try {
      const res = await api.extractOCR(project.id, selectedEngine, "en");
      const jobId = res.job_id;

      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 600));
        const job = await api.getJob(jobId);
        setOcrProgress(job.progress);
        setProgressMsg(job.message || "Extracting text...");

        if (job.status === "SUCCEEDED" || job.status === "FAILED") {
          if (job.status === "FAILED") {
            throw new Error(job.error || "OCR extraction failed.");
          }
          break;
        }
      }

      await loadData();
      setCacheBuster(Date.now());
      alert("Project OCR extraction complete!");
    } catch (err: any) {
      alert(`OCR failed: ${err.message}`);
    } finally {
      setExtracting(false);
      setOcrProgress(0);
      setProgressMsg("");
    }
  };

  const handleOCRRegion = async (regionId: string) => {
    setSingleOcrLoading(true);
    try {
      pushUndo(textRegions);
      const updated = await api.ocrSingleRegion(project.id, regionId, selectedEngine, "en");
      setTextRegions((prev) => prev.map((tr) => (tr.id === regionId ? updated : tr)));
      setEditForm((prev) => ({
        ...prev,
        corrected_text: updated.corrected_text || updated.raw_text || "",
      }));
      setCacheBuster(Date.now());
    } catch (err: any) {
      alert(`Failed to extract OCR for region: ${err.message}`);
    } finally {
      setSingleOcrLoading(false);
    }
  };

  const handleSaveRegion = async () => {
    if (!selectedRegion) return;
    setSavingRegion(true);
    try {
      pushUndo(textRegions);
      const updated = await api.updateTextRegion(project.id, selectedRegion.id, {
        region_type: editForm.region_type,
        status: editForm.status,
        corrected_text: editForm.corrected_text,
        corrected_by: "HUMAN",
        correction_status: "EDITED",
        speaker_character_id: editForm.speaker_character_id.trim() || undefined,
        speaker_assignment_method: editForm.speaker_assignment_method,
      });

      setTextRegions((prev) => prev.map((tr) => (tr.id === updated.id ? updated : tr)));
    } catch (err: any) {
      alert(`Failed to save region updates: ${err.message}`);
    } finally {
      setSavingRegion(false);
    }
  };

  const handleApproveRegion = async (regionId: string) => {
    try {
      pushUndo(textRegions);
      const updated = await api.updateTextRegion(project.id, regionId, {
        status: "CONFIRMED",
      });
      setTextRegions((prev) => prev.map((tr) => (tr.id === updated.id ? updated : tr)));
      if (selectedRegionId === regionId) {
        setEditForm((prev) => ({ ...prev, status: "CONFIRMED" }));
      }
    } catch (err: any) {
      alert(`Failed to approve region: ${err.message}`);
    }
  };

  const handleRejectRegion = async (regionId: string) => {
    try {
      const updated = await api.updateTextRegion(project.id, regionId, { status: "REJECTED" });
      setTextRegions((prev) => prev.map((tr) => tr.id === updated.id ? updated : tr));
    } catch (err: any) {
      alert(`Could not ignore region: ${err.message}`);
    }
  };

  const handleDeleteRegion = async (regionId: string) => {
    if (!confirm("Are you sure you want to delete this text region?")) return;
    try {
      pushUndo(textRegions);
      await api.deleteTextRegion(project.id, regionId);
      setTextRegions((prev) => prev.filter((tr) => tr.id !== regionId));
      if (selectedRegionId === regionId) {
        setSelectedRegionId(null);
      }
    } catch (err: any) {
      alert(`Failed to delete region: ${err.message}`);
    }
  };

  const handleConfirmAllPending = async () => {
    setConfirming(true);
    try {
      const pending = textRegions.filter((tr) => tr.status === "NEEDS_REVIEW");
      await Promise.all(
        pending.map((tr) =>
          api.updateTextRegion(project.id, tr.id, {
            status: "CONFIRMED",
            corrected_text: tr.corrected_text || tr.raw_text || "...",
          })
        )
      );
      await loadData();
      alert(`All ${pending.length} pending text regions confirmed!`);
    } catch (err: any) {
      alert(`Failed to confirm pending regions: ${err.message}`);
    } finally {
      setConfirming(false);
    }
  };

  const handleConfirmAll = async () => {
    setConfirming(true);
    try {
      await api.confirmOCR(project.id);
      const updatedProj = await api.getProject(project.id);
      alert("OCR approval successful! Project advanced to OCR_APPROVED.");
      onOCRApproved(updatedProj);
    } catch (err: any) {
      alert(`Strict Approval Gate Blocked: ${err.message}`);
    } finally {
      setConfirming(false);
    }
  };

  const getRegionBorderColor = (type: string, status: string) => {
    if (status === "NEEDS_REVIEW") return "#f59e0b"; // Amber warning
    if (status === "REJECTED") return "#71717a"; // Muted gray
    switch (type) {
      case "SPEECH":
        return "#0ea5e9"; // Sky blue
      case "NARRATION":
        return "#eab308"; // Gold
      case "THOUGHT":
        return "#a855f7"; // Purple
      case "SFX":
        return "#ec4899"; // Pink
      case "CAPTION":
        return "#14b8a6"; // Teal
      default:
        return "#6366f1"; // Indigo
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <Icons.ArrowLeft className="w-4 h-4" />
            Back
          </Button>
          <div>
            <h2 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
              Text Region Detection & OCR Review
            </h2>
            <p className="text-xs text-zinc-400">
              Detect speech balloons, transcribe text via OCR cache, and verify human corrections.
            </p>
          </div>
        </div>

        {/* Engine Controls & Actions */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-400">Engine:</span>
            <select
              value={selectedEngine}
              onChange={(e) => setSelectedEngine(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
            >
              {engines.map((e) => (
                <option key={e.engine_id} value={e.engine_id}>
                  {e.display_name} [{e.status_label || (e.is_available ? "Available" : "Configuration required")}]
                </option>
              ))}
            </select>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleDetectRegions}
            loading={detectingRegions}
          >
            <Icons.Layers className="w-4 h-4" />
            Detect Bubbles
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleRunProjectOCR}
            loading={extracting}
          >
            <Icons.Rotate className="w-4 h-4" />
            OCR All Panels
          </Button>

          {needsReviewCount > 0 && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleConfirmAllPending}
              loading={confirming}
              className="bg-amber-600/20 text-amber-300 border-amber-800 hover:bg-amber-600/30"
              title="Confirm all pending text regions for gate approval"
            >
              <Icons.Check className="w-4 h-4 mr-1" />
              Confirm All ({needsReviewCount})
            </Button>
          )}

          <Button
            variant="secondary"
            size="sm"
            onClick={handleConfirmAll}
            loading={confirming}
            className={`border ${
              needsReviewCount > 0
                ? "bg-amber-950/40 text-amber-300 border-amber-800/80 hover:bg-amber-950/60"
                : "bg-emerald-600/20 text-emerald-300 border-emerald-800 hover:bg-emerald-600/30"
            }`}
          >
            <Icons.CheckCircle className="w-4 h-4 mr-1" />
            Approve OCR ({needsReviewCount > 0 ? `${needsReviewCount} Pending` : "Ready"})
          </Button>

          {onProceedToStory && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onProceedToStory(project)}
              disabled={needsReviewCount > 0 && project.current_stage !== "OCR_APPROVED"}
            >
              Proceed to Story →
            </Button>
          )}

          {onOpenStoryEditor && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onOpenStoryEditor(project)}
              className="bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow-md shadow-indigo-600/30"
              title="Open the unified Video-First Story Editor"
            >
              <Icons.Film className="w-3.5 h-3.5 mr-1 text-white" />
              Open in Story Editor →
            </Button>
          )}
        </div>
      </div>

      <Button variant="secondary" size="sm" onClick={() => setReviewFlagged(!reviewFlagged)}>
        {reviewFlagged ? "Return to panel editor" : `Review flagged crops (${needsReviewCount})`}
      </Button>
      {!reviewFlagged && panelRegions.length > 0 && (
        <Button variant="ghost" size="sm" loading={savingRegion} onClick={async () => {
          const reviewed = [...panelRegions];
          setSavingRegion(true);
          try { for (const tr of reviewed) await handleRejectRegion(tr.id); }
          finally { setSavingRegion(false); }
        }}>Exclude text in panel #{activePanel?.sequence}</Button>
      )}
      {reviewFlagged && (
        <section className="space-y-3" aria-label="Flagged OCR crops">
          <p className="text-sm text-zinc-300">Inspect each crop. Ignore artwork without text; open unreadable dialogue in the editor to correct it.</p>
          <Button size="sm" variant="secondary" loading={savingRegion}
            disabled={textRegions.filter((tr) => tr.status === "NEEDS_REVIEW").slice(0, 6).some((tr) => !!(tr.corrected_text || tr.raw_text || "").trim())}
            onClick={async () => {
              const reviewed = textRegions.filter((tr) => tr.status === "NEEDS_REVIEW").slice(0, 6);
              if (reviewed.some((tr) => !!(tr.corrected_text || tr.raw_text || "").trim())) return;
              setSavingRegion(true);
              try { for (const tr of reviewed) await handleRejectRegion(tr.id); }
              finally { setSavingRegion(false); }
            }}>
            Ignore shown empty artwork
          </Button>
          <p className="text-xs text-zinc-500">Use only after checking every displayed crop contains no text.</p>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            {textRegions.filter((tr) => tr.status === "NEEDS_REVIEW").slice(0, 6).map((tr) => (
              <Card key={tr.id} className="space-y-2">
                <p className="text-xs text-zinc-400">Panel #{panels.find((p) => p.id === tr.panel_id)?.sequence} · Region #{tr.sequence_in_panel}</p>
                <div className="h-48 overflow-auto bg-white rounded">
                  <img src={api.getTextRegionImageUrl(project.id, tr.id)} alt={`Flagged region ${tr.sequence_global}`} className="w-full h-full object-contain" loading="lazy" />
                </div>
                <p className="text-xs text-zinc-300 break-words">{tr.corrected_text || tr.raw_text || "No text recognized"}</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => handleRejectRegion(tr.id)}>Ignore artwork</Button>
                  <Button size="sm" variant="primary" onClick={() => {
                    setSelectedPanelIndex(panels.findIndex((p) => p.id === tr.panel_id));
                    setSelectedRegionId(tr.id);
                    setReviewFlagged(false);
                    window.scrollTo({ top: 0 });
                  }}>Open in editor</Button>
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* Engine Status Diagnostic Banner */}
      {(() => {
        const activeEng = engines.find((e) => e.engine_id === selectedEngine);
        if (activeEng && !activeEng.is_available) {
          return (
            <div className="p-3 bg-zinc-900/90 border border-amber-800/60 rounded-xl flex items-center justify-between gap-3 text-amber-300 text-xs">
              <div className="flex items-center gap-2">
                <Icons.AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                <span>
                  <strong>{activeEng.display_name} — Configuration required:</strong>{" "}
                  {activeEng.diagnostic_message || "Required dependencies or model weights are missing."}
                </span>
              </div>
              <span className="bg-amber-950/80 border border-amber-800 text-amber-400 px-2 py-0.5 rounded text-[11px] font-mono">
                {activeEng.status_label || "Configuration required"}
              </span>
            </div>
          );
        }
        return null;
      })()}

      {/* Milestone 3 Completion & Downstream Contract Export Banner */}
      {project.current_stage === "OCR_APPROVED" && (
        <div className="p-4 bg-emerald-950/30 border border-emerald-800/80 rounded-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-3">
            <Icons.CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <div>
              <p className="font-semibold text-emerald-200">
                Milestone 3 Production Gate Passed: OCR Approved
              </p>
              <p className="text-zinc-400">
                Source truth established across Layer 1 (Machine OCR), Layer 2 (Human Corrections), and Layer 3 (Speaker Attribution).
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  const contract = await api.getCanonicalExportContract(project.id);
                  const blob = new Blob([JSON.stringify(contract, null, 2)], { type: "application/json" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `canonical_contract_${project.id.slice(0, 8)}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                } catch (err: any) {
                  alert(`Failed to export contract: ${err.message}`);
                }
              }}
              className="text-emerald-300 border-emerald-700/60 hover:bg-emerald-950/50"
            >
              Export Downstream Contract
            </Button>
            {onProceedToStory && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onProceedToStory(project)}
                className="text-zinc-400 hover:text-zinc-200 text-xs"
                title="Experimental Milestone 4 Story Understanding preview"
              >
                M4 Story Preview <Icons.ArrowRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Strict Gate Banner Warning */}
      {needsReviewCount > 0 && (
        <div className="p-3.5 bg-amber-950/40 border border-amber-800/80 rounded-xl flex items-center justify-between gap-3 text-amber-200 text-xs">
          <div className="flex items-center gap-2.5">
            <Icons.AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
            <span>
              <strong>Strict Approval Gate:</strong> {needsReviewCount} text region(s) are flagged as{" "}
              <code className="bg-amber-900/60 px-1 py-0.5 rounded font-mono font-bold">NEEDS_REVIEW</code>.
              Inspect and confirm low-confidence or untranscribed regions before downstream pipeline approval.
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-amber-300 hover:bg-amber-900/40 text-xs"
            onClick={() => {
              const firstFlagged = textRegions.find((tr) => tr.status === "NEEDS_REVIEW");
              if (firstFlagged) {
                const targetPanelIdx = panels.findIndex((p) => p.id === firstFlagged.panel_id);
                if (targetPanelIdx >= 0) setSelectedPanelIndex(targetPanelIdx);
                setSelectedRegionId(firstFlagged.id);
              }
            }}
          >
            Jump to Next Flagged
          </Button>
        </div>
      )}

      {/* Progress Bar when running */}
      {extracting && (
        <Card className="p-4 bg-indigo-950/30 border-indigo-900 space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-indigo-300 font-medium">{progressMsg}</span>
            <span className="text-indigo-400 font-mono">{(ocrProgress * 100).toFixed(0)}%</span>
          </div>
          <p className="text-[11px] text-indigo-300/80">
            Region edits are locked until OCR finishes so the completion refresh cannot overwrite unsaved changes.
          </p>
          <ProgressBar progress={ocrProgress * 100} />
        </Card>
      )}

      {/* Panel Navigation Strip */}
      {panels.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-2 border-b border-zinc-900">
          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mr-2 flex-shrink-0">
            Panels:
          </span>
          {panels.map((p, idx) => {
            const count = textRegions.filter((tr) => tr.panel_id === p.id).length;
            const hasNeedsReview = textRegions.some(
              (tr) => tr.panel_id === p.id && tr.status === "NEEDS_REVIEW"
            );
            const isSelected = idx === selectedPanelIndex;
            return (
              <button
                key={p.id}
                onClick={() => {
                  setSelectedPanelIndex(idx);
                  const firstInPanel = textRegions.find((tr) => tr.panel_id === p.id);
                  if (firstInPanel) setSelectedRegionId(firstInPanel.id);
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 flex-shrink-0 transition-all ${
                  isSelected
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800 border border-zinc-800"
                }`}
              >
                <span>Panel #{p.sequence}</span>
                <span
                  className={`text-[9px] px-1.5 py-0.2 rounded-full ${
                    hasNeedsReview
                      ? "bg-amber-900 text-amber-200"
                      : count > 0
                      ? "bg-emerald-900/80 text-emerald-300"
                      : "bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {count} regions {hasNeedsReview ? "⚠️" : ""}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Main Review Workspace Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left (7 cols): Visual Panel Crop with SVG TextRegion Overlays */}
        <div className="lg:col-span-7 space-y-3">
          <Card className="p-4 bg-zinc-950 flex flex-col items-center justify-center min-h-[500px]">
            {activePanel ? (
              <div className="relative inline-block max-w-full overflow-hidden rounded-lg shadow-xl border border-zinc-800">
                <img
                  src={`${api.getPanelImageUrl(project.id, activePanel.id)}?t=${cacheBuster}`}
                  alt={`Panel ${activePanel.sequence}`}
                  className="max-h-[68vh] w-auto object-contain block"
                />

                {/* SVG Overlay of detected Text Regions */}
                <svg
                  className="absolute inset-0 w-full h-full pointer-events-auto"
                  viewBox={`0 0 ${activePanel.width} ${activePanel.height}`}
                  preserveAspectRatio="none"
                >
                  {panelRegions.map((tr) => {
                    const isSelected = tr.id === selectedRegionId;
                    const stroke = getRegionBorderColor(tr.region_type, tr.status);

                    return (
                      <g
                        key={tr.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedRegionId(tr.id);
                        }}
                        className="cursor-pointer group"
                      >
                        <rect
                          x={tr.x}
                          y={tr.y}
                          width={tr.width}
                          height={tr.height}
                          fill={isSelected ? "rgba(99, 102, 241, 0.28)" : "rgba(15, 23, 42, 0.22)"}
                          stroke={isSelected ? "#818cf8" : stroke}
                          strokeWidth={isSelected ? 3 : 2}
                          strokeDasharray={tr.status === "NEEDS_REVIEW" ? "6,3" : undefined}
                          rx={4}
                        />

                        {/* Region Order & Type Label */}
                        <rect
                          x={tr.x}
                          y={Math.max(0, tr.y - 18)}
                          width={85}
                          height={16}
                          fill={stroke}
                          rx={3}
                        />
                        <text
                          x={tr.x + 4}
                          y={Math.max(0, tr.y - 6)}
                          fill="#ffffff"
                          fontSize="10"
                          fontWeight="bold"
                          fontFamily="sans-serif"
                        >
                          #{tr.sequence_in_panel} {tr.region_type}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
            ) : (
              <div className="text-zinc-500 text-sm">No panel selected</div>
            )}
          </Card>
        </div>

        {/* Right (5 cols): 3-Layer Region Editor & Region List */}
        <div className="lg:col-span-5 space-y-4">
          {selectedRegion ? (
            <Card className="p-4 space-y-4 bg-zinc-900 border-zinc-800">
              {/* Region Header */}
              <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
                <div className="flex items-center gap-2">
                  <Badge variant="accent">
                    Region #{selectedRegion.sequence_in_panel} (Global #{selectedRegion.sequence_global})
                  </Badge>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                      selectedRegion.status === "CONFIRMED"
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        : selectedRegion.status === "NEEDS_REVIEW"
                        ? "bg-amber-950 text-amber-300 border border-amber-800"
                        : "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {selectedRegion.status}
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleOCRRegion(selectedRegion.id)}
                    loading={singleOcrLoading}
                    className="text-xs"
                    title="Extract OCR for this region only"
                  >
                    <Icons.Rotate className="w-3.5 h-3.5 mr-1" />
                    OCR
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDeleteRegion(selectedRegion.id)}
                    className="text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 text-xs p-1"
                    title="Delete Region"
                  >
                    <Icons.Trash className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              {/* Layer 1: Machine OCR (Immutable Provenance) */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                    Layer 1: Immutable Machine OCR
                  </span>
                  <span className="text-[10px] font-mono text-zinc-500">
                    Confidence:{" "}
                    {selectedRegion.raw_confidence != null
                      ? `${(selectedRegion.raw_confidence * 100).toFixed(0)}%`
                      : "Unextracted"}
                  </span>
                </div>
                <div className="bg-zinc-950 p-2.5 rounded border border-zinc-800/80">
                  <p className="text-xs font-mono text-zinc-300 select-all min-h-[2.5rem]">
                    {selectedRegion.raw_text || (
                      <span className="text-zinc-600 italic">No machine text extracted yet.</span>
                    )}
                  </p>
                </div>
              </div>

              {/* Layer 2: Human Correction (Canonical Reading Text) */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                    Layer 2: Human Correction / Verified Script
                  </label>
                  <span className="text-[10px] text-zinc-500 font-mono">
                    {selectedRegion.correction_status || "UNEDITED"}
                  </span>
                </div>
                <textarea
                  rows={3}
                  value={editForm.corrected_text}
                  onChange={(e) => setEditForm({ ...editForm, corrected_text: e.target.value })}
                  disabled={extracting}
                  placeholder="Enter or correct dialogue text..."
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500 resize-none font-sans"
                />
              </div>

              {/* Classification & Status Controls */}
              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="text-[10px] text-zinc-400 font-medium block mb-1">
                    Region Type:
                  </label>
                  <select
                    value={editForm.region_type}
                    onChange={(e) => setEditForm({ ...editForm, region_type: e.target.value })}
                    disabled={extracting}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="SPEECH">Speech Bubble</option>
                    <option value="NARRATION">Narration Box</option>
                    <option value="THOUGHT">Thought Bubble</option>
                    <option value="SFX">Sound Effect (SFX)</option>
                    <option value="CAPTION">Caption</option>
                    <option value="UNKNOWN">Unknown / Ambiguous</option>
                  </select>
                </div>

                <div>
                  <label className="text-[10px] text-zinc-400 font-medium block mb-1">
                    Review Status:
                  </label>
                  <select
                    value={editForm.status}
                    onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                    disabled={extracting}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="DETECTED">DETECTED (Not reviewed)</option>
                    <option value="CONFIRMED">CONFIRMED (Approved)</option>
                    <option value="NEEDS_REVIEW">NEEDS_REVIEW (Flagged)</option>
                    <option value="REJECTED">REJECTED (Ignore)</option>
                  </select>
                </div>
              </div>

              {/* Layer 3: Speaker Attribution Preparation */}
              <div className="pt-2 border-t border-zinc-800/80 space-y-2">
                <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider block">
                  Layer 3: Speaker Attribution (Milestone 4 Ready)
                </span>
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-1">Speaker Tag / ID:</label>
                    <input
                      type="text"
                      placeholder="e.g. char_protagonist_01"
                      value={editForm.speaker_character_id}
                      onChange={(e) =>
                        setEditForm({ ...editForm, speaker_character_id: e.target.value })
                      }
                      disabled={extracting}
                      className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-1">Method:</label>
                    <select
                      value={editForm.speaker_assignment_method}
                      onChange={(e) =>
                        setEditForm({ ...editForm, speaker_assignment_method: e.target.value })
                      }
                      disabled={extracting}
                      className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                    >
                      <option value="MANUAL">Manual Review</option>
                      <option value="RULE_TAIL">Balloon Tail Trace</option>
                      <option value="PROXIMITY">Proximity Heuristic</option>
                      <option value="LLM_INFERRED">LLM Inferred</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Save & Approve Actions */}
              <div className="flex items-center justify-between pt-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleApproveRegion(selectedRegion.id)}
                  disabled={extracting || savingRegion}
                  className="text-xs bg-emerald-950/40 text-emerald-300 border-emerald-800/80"
                >
                  <Icons.Check className="w-3.5 h-3.5 mr-1" />
                  Mark Confirmed
                </Button>

                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleSaveRegion}
                  disabled={extracting}
                  loading={savingRegion}
                  className="text-xs"
                >
                  Save Region Changes
                </Button>
              </div>
            </Card>
          ) : (
            <Card className="text-center py-16 text-zinc-500 text-xs border-dashed">
              No text region selected. Click a region box in the panel preview or click &quot;Detect Bubbles&quot;.
            </Card>
          )}

          {/* Region List in Active Panel */}
          <div className="space-y-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Panel #{activePanel?.sequence || 1} Regions ({panelRegions.length})
            </span>
            <div className="space-y-1.5 max-h-[36vh] overflow-y-auto pr-1">
              {panelRegions.map((tr) => {
                const isSelected = tr.id === selectedRegionId;
                return (
                  <button
                    key={tr.id}
                    onClick={() => setSelectedRegionId(tr.id)}
                    className={`w-full p-2.5 rounded-lg text-left transition-all border flex items-center justify-between ${
                      isSelected
                        ? "bg-indigo-950/60 border-indigo-700 text-white"
                        : "bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800/60"
                    }`}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      <span className="text-xs font-bold text-indigo-400 flex-shrink-0">
                        #{tr.sequence_in_panel}
                      </span>
                      <span className="text-xs truncate font-mono">
                        {tr.corrected_text || tr.raw_text || "(empty)"}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <Badge
                        variant={tr.status === "NEEDS_REVIEW" ? "danger" : "neutral"}
                        className="text-[9px] uppercase font-bold"
                      >
                        {tr.status}
                      </Badge>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
