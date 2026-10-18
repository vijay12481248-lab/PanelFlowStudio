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
import { useError } from "../context/ErrorContext";

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
  const { reportError, inspectError } = useError();
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

  // Vertical Panel Navigation & Deletion State
  const [isVerticalPanelsOpen, setIsVerticalPanelsOpen] = useState<boolean>(true);
  const [panelSearchQuery, setPanelSearchQuery] = useState<string>("");
  const [panelFilter, setPanelFilter] = useState<"all" | "flagged" | "ready" | "empty">("all");
  const [deletingPanel, setDeletingPanel] = useState<boolean>(false);
  const [deleteConfirmPanel, setDeleteConfirmPanel] = useState<Panel | null>(null);
  const panelItemRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // In-Preview Zoom & Pan Controls
  const [zoomLevel, setZoomLevel] = useState<number>(1.0);
  const [panOffset, setPanOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const panStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const [copiedRawText, setCopiedRawText] = useState<boolean>(false);

  // Non-blocking Inline Toast Notifications
  const [toastMessage, setToastMessage] = useState<{ text: string; type?: "info" | "success" | "warn" } | null>(null);
  const toastTimeoutRef = useRef<any>(null);

  const showToast = useCallback((text: string, type: "info" | "success" | "warn" = "info") => {
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    setToastMessage({ text, type });
    toastTimeoutRef.current = setTimeout(() => {
      setToastMessage(null);
    }, 2800);
  }, []);

  // Undo / Redo history stack for Text Regions
  const [undoStack, setUndoStack] = useState<TextRegion[][]>([]);
  const [redoStack, setRedoStack] = useState<TextRegion[][]>([]);

  // Blur & Redaction State
  const [blurringRegion, setBlurringRegion] = useState<boolean>(false);
  const [blurringPanel, setBlurringPanel] = useState<boolean>(false);
  const [resettingPanel, setResettingPanel] = useState<boolean>(false);
  const [panelBlurStatus, setPanelBlurStatus] = useState<{ is_blurred: boolean; has_backup: boolean; blurred_regions_count: number } | null>(null);
  const [isCustomBlurOpen, setIsCustomBlurOpen] = useState<boolean>(false);
  const [customBlurBox, setCustomBlurBox] = useState<{ x: number; y: number; width: number; height: number; blur_radius: number }>({
    x: 0,
    y: 0,
    width: 250,
    height: 100,
    blur_radius: 24,
  });

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
      reportError({
        title: "Failed to Load OCR Data",
        message: err.message || "Failed to load OCR data from project workspace.",
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
  }, [selectedRegion]);

  // Sync active panel blur status
  useEffect(() => {
    if (activePanel) {
      api.getPanelBlurStatus(project.id, activePanel.id)
        .then(setPanelBlurStatus)
        .catch(() => setPanelBlurStatus(null));
    } else {
      setPanelBlurStatus(null);
    }
  }, [activePanel?.id, project.id, cacheBuster]);

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
    } catch (err: any) {
      reportError({
        title: "Text Region Detection Failed",
        message: err.message || "Could not detect speech/narration text bubbles.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        jobType: "OCR_EXTRACTION",
        rawDetails: err,
      });
    } finally {
      setDetectingRegions(false);
    }
  };

  const handleRunProjectOCR = async () => {
    const activeEng = engines.find((e) => e.engine_id === selectedEngine);
    if (activeEng && !activeEng.is_available) {
      reportError({
        title: "OCR Engine Unavailable",
        message: `Cannot run OCR with ${activeEng.display_name}: ${activeEng.diagnostic_message || "Configuration required."}`,
        severity: "warning",
        source: "system",
        projectId: project.id,
        rawDetails: activeEng,
      });
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
    } catch (err: any) {
      reportError({
        title: "OCR Extraction Failed",
        message: err.message || "Text extraction across panels failed.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        jobType: "OCR_EXTRACTION",
        rawDetails: err,
      });
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

  const handleBlurRegion = async (regionId: string) => {
    setBlurringRegion(true);
    try {
      pushUndo(textRegions);
      const updated = await api.blurTextRegion(project.id, regionId);
      setTextRegions((prev) => prev.map((tr) => (tr.id === regionId ? updated : tr)));
      setEditForm((prev) => ({
        ...prev,
        corrected_text: updated.corrected_text || "",
        region_type: updated.region_type,
        status: updated.status,
      }));
      setCacheBuster(Date.now());
      if (activePanel) {
        const st = await api.getPanelBlurStatus(project.id, activePanel.id);
        setPanelBlurStatus(st);
      }
    } catch (err: any) {
      alert(`Failed to blur text region: ${err.message}`);
    } finally {
      setBlurringRegion(false);
    }
  };

  const handleBlurAllPanelText = async () => {
    if (!activePanel) return;
    setBlurringPanel(true);
    try {
      pushUndo(textRegions);
      const res = await api.blurPanelText(project.id, activePanel.id);
      const updated = await api.listTextRegions(project.id);
      setTextRegions(updated);
      setCacheBuster(Date.now());
      const st = await api.getPanelBlurStatus(project.id, activePanel.id);
      setPanelBlurStatus(st);
      alert(`Blurred ${res.blurred_count} text region(s) on Panel #${activePanel.sequence}.`);
    } catch (err: any) {
      alert(`Failed to blur panel text: ${err.message}`);
    } finally {
      setBlurringPanel(false);
    }
  };

  const handleBlurEntirePanel = async () => {
    if (!activePanel) return;
    if (!confirm(`Are you sure you want to blur the entire visual content of Panel #${activePanel.sequence}? (Recommended for ad/credit/splash panels)`)) return;
    setBlurringPanel(true);
    try {
      pushUndo(textRegions);
      await api.blurEntirePanel(project.id, activePanel.id);
      const updated = await api.listTextRegions(project.id);
      setTextRegions(updated);
      setCacheBuster(Date.now());
      const st = await api.getPanelBlurStatus(project.id, activePanel.id);
      setPanelBlurStatus(st);
      alert(`Entire Panel #${activePanel.sequence} has been blurred.`);
    } catch (err: any) {
      alert(`Failed to blur panel: ${err.message}`);
    } finally {
      setBlurringPanel(false);
    }
  };

  const handleBlurCustomBox = async () => {
    if (!activePanel) return;
    setBlurringPanel(true);
    try {
      await api.blurPanelRegion(project.id, activePanel.id, customBlurBox);
      setCacheBuster(Date.now());
      setIsCustomBlurOpen(false);
      const st = await api.getPanelBlurStatus(project.id, activePanel.id);
      setPanelBlurStatus(st);
    } catch (err: any) {
      alert(`Failed to blur custom area: ${err.message}`);
    } finally {
      setBlurringPanel(false);
    }
  };

  const handleResetPanelImage = async () => {
    if (!activePanel) return;
    if (!confirm(`Restore original unblurred image for Panel #${activePanel.sequence}?`)) return;
    setResettingPanel(true);
    try {
      pushUndo(textRegions);
      await api.resetPanelImage(project.id, activePanel.id);
      const updated = await api.listTextRegions(project.id);
      setTextRegions(updated);
      setCacheBuster(Date.now());
      const st = await api.getPanelBlurStatus(project.id, activePanel.id);
      setPanelBlurStatus(st);
      alert(`Restored original unblurred panel image.`);
    } catch (err: any) {
      alert(`Failed to reset panel image: ${err.message}`);
    } finally {
      setResettingPanel(false);
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
    } catch (err: any) {
      reportError({
        title: "Failed to Confirm Regions",
        message: err.message || "Error bulk-confirming text regions.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setConfirming(false);
    }
  };

  const handleConfirmAll = async () => {
    setConfirming(true);
    try {
      await api.confirmOCR(project.id);
      const updatedProj = await api.getProject(project.id);
      onOCRApproved(updatedProj);
    } catch (err: any) {
      reportError({
        title: "Strict Approval Gate Blocked",
        message: err.message || "OCR approval gate conditions were not satisfied.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setConfirming(false);
    }
  };

  const handleNavigatePanel = useCallback(
    (newIndex: number) => {
      if (newIndex < 0 || newIndex >= panels.length) return;
      setSelectedPanelIndex(newIndex);
      setPanOffset({ x: 0, y: 0 }); // Reset pan position on panel navigation
      const targetPanel = panels[newIndex];
      if (targetPanel) {
        const firstInPanel = textRegions.find((tr) => tr.panel_id === targetPanel.id);
        if (firstInPanel) {
          setSelectedRegionId(firstInPanel.id);
        }
      }
    },
    [panels, textRegions]
  );

  const handleZoomIn = () => setZoomLevel((z) => Math.min(3.0, +(z + 0.25).toFixed(2)));
  const handleZoomOut = () => setZoomLevel((z) => Math.max(0.5, +(z - 0.25).toFixed(2)));
  const handleZoomReset = () => {
    setZoomLevel(1.0);
    setPanOffset({ x: 0, y: 0 });
  };

  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.15 : -0.15;
      setZoomLevel((z) => Math.min(3.0, Math.max(0.5, +(z + delta).toFixed(2))));
    }
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (zoomLevel > 1.0 && (e.button === 0 || e.button === 1)) {
      setIsPanning(true);
      panStartRef.current = { x: e.clientX - panOffset.x, y: e.clientY - panOffset.y };
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isPanning) {
      setPanOffset({
        x: e.clientX - panStartRef.current.x,
        y: e.clientY - panStartRef.current.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsPanning(false);
  };

  const handleSaveAndNextRegion = async () => {
    if (!selectedRegion) return;
    setSavingRegion(true);
    try {
      pushUndo(textRegions);
      const updated = await api.updateTextRegion(project.id, selectedRegion.id, {
        region_type: editForm.region_type,
        status: "CONFIRMED",
        corrected_text: editForm.corrected_text,
        corrected_by: "HUMAN",
        correction_status: "EDITED",
        speaker_character_id: editForm.speaker_character_id.trim() || undefined,
        speaker_assignment_method: editForm.speaker_assignment_method,
      });

      setTextRegions((prev) => prev.map((tr) => (tr.id === updated.id ? updated : tr)));
      showToast(`Region #${selectedRegion.sequence_in_panel} confirmed!`, "success");

      // Auto-advance to next region in panel or next panel
      const currentIdx = panelRegions.findIndex((r) => r.id === selectedRegion.id);
      if (currentIdx >= 0 && currentIdx < panelRegions.length - 1) {
        setSelectedRegionId(panelRegions[currentIdx + 1].id);
      } else if (selectedPanelIndex < panels.length - 1) {
        handleNavigatePanel(selectedPanelIndex + 1);
      }
    } catch (err: any) {
      reportError({
        title: "Failed to Save Region",
        message: err.message || "Error saving text region updates.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setSavingRegion(false);
    }
  };

  const handleDeletePanel = async (panelId: string) => {
    setDeletingPanel(true);
    try {
      await api.deletePanel(project.id, panelId);

      // Re-fetch canonical panels and text regions from backend
      const [updatedPanels, updatedRegions] = await Promise.all([
        api.listPanels(project.id),
        api.listTextRegions(project.id),
      ]);

      setPanels(updatedPanels);
      setTextRegions(updatedRegions);
      setCacheBuster(Date.now());

      // If we deleted the active panel or last panel, adjust selectedPanelIndex
      setSelectedPanelIndex((prevIdx) => {
        if (updatedPanels.length === 0) return 0;
        return Math.min(prevIdx, updatedPanels.length - 1);
      });

      // Update selectedRegionId to first region of the newly active panel
      const targetIdx = Math.min(selectedPanelIndex, Math.max(0, updatedPanels.length - 1));
      const newActivePanel = updatedPanels[targetIdx];
      if (newActivePanel) {
        const firstRegion = updatedRegions.find((tr) => tr.panel_id === newActivePanel.id);
        setSelectedRegionId(firstRegion ? firstRegion.id : null);
      } else {
        setSelectedRegionId(null);
      }

      setDeleteConfirmPanel(null);
      showToast("Panel deleted successfully", "success");
    } catch (err: any) {
      alert(`Failed to delete panel: ${err.message}`);
    } finally {
      setDeletingPanel(false);
    }
  };

  // Auto-scroll active panel into view in vertical strip
  useEffect(() => {
    if (activePanel && panelItemRefs.current[activePanel.id]) {
      panelItemRefs.current[activePanel.id]?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [selectedPanelIndex, activePanel?.id]);

  // Global keyboard shortcuts (Left/Right arrow keys navigate panels when not typing)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable ||
        deleteConfirmPanel
      ) {
        return;
      }

      if (e.key === "ArrowLeft") {
        if (selectedPanelIndex > 0) {
          e.preventDefault();
          handleNavigatePanel(selectedPanelIndex - 1);
        }
      } else if (e.key === "ArrowRight") {
        if (selectedPanelIndex < panels.length - 1) {
          e.preventDefault();
          handleNavigatePanel(selectedPanelIndex + 1);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedPanelIndex, panels.length, deleteConfirmPanel, handleNavigatePanel]);

  const getRegionBorderColor = (type: string, status: string) => {
    if (status === "BLURRED" || type === "REDACTED") return "#f97316"; // Orange for blurred/redacted
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

      {/* Top Review Toolbar / Status Bar */}
      {panels.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 bg-zinc-900/60 border border-zinc-800/80 rounded-xl">
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsVerticalPanelsOpen((v) => !v)}
              className="text-xs flex items-center gap-1.5 text-zinc-300 border-zinc-700 hover:bg-zinc-800"
              title={isVerticalPanelsOpen ? "Hide vertical panel list" : "Show vertical panel list"}
            >
              <Icons.Layout className="w-4 h-4 text-indigo-400" />
              <span>{isVerticalPanelsOpen ? "Hide Panel List" : `Show Panels (${panels.length})`}</span>
            </Button>

            {activePanel && (
              <div className="flex items-center gap-2 text-xs">
                <span className="font-semibold text-zinc-200">
                  Panel #{activePanel.sequence}
                </span>
                <span className="text-zinc-500">
                  ({selectedPanelIndex + 1} of {panels.length})
                </span>
                <span className="text-zinc-600 hidden sm:inline">·</span>
                <span className="text-zinc-400 text-[11px] hidden sm:inline">
                  {activePanel.width} × {activePanel.height}px
                </span>
                <span className="text-zinc-600 hidden sm:inline">·</span>
                <span className="text-zinc-400 text-[11px] hidden sm:inline">
                  {panelRegions.length} text {panelRegions.length === 1 ? "region" : "regions"}
                </span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] text-zinc-500 hidden md:inline">
              Use <kbd className="px-1.5 py-0.5 bg-zinc-800 border border-zinc-700 rounded text-zinc-300 font-mono">←</kbd> / <kbd className="px-1.5 py-0.5 bg-zinc-800 border border-zinc-700 rounded text-zinc-300 font-mono">→</kbd> keys or preview edge arrows to navigate
            </span>

            {activePanel && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDeleteConfirmPanel(activePanel)}
                disabled={deletingPanel}
                className="text-rose-400 hover:text-rose-200 hover:bg-rose-950/60 border border-rose-900/50 text-xs flex items-center gap-1.5 transition-colors"
                title={`Delete Panel #${activePanel.sequence}`}
              >
                <Icons.Trash className="w-3.5 h-3.5" />
                <span>Delete Panel #{activePanel.sequence}</span>
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Main Review Workspace Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Column 1: Vertical Panels Strip (When Open) */}
        {isVerticalPanelsOpen && panels.length > 0 && (
          <div className="lg:col-span-3 xl:col-span-2 space-y-2.5">
            <Card className="p-3 bg-zinc-950 border-zinc-800 flex flex-col max-h-[82vh]">
              {/* Vertical Header */}
              <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 mb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-zinc-200 flex items-center gap-1.5">
                  <Icons.Film className="w-4 h-4 text-indigo-400" />
                  Panels ({panels.length})
                </span>
                <Badge variant={needsReviewCount > 0 ? "warning" : "success"} className="text-[10px]">
                  {needsReviewCount > 0 ? `${needsReviewCount} flagged` : "All clear"}
                </Badge>
              </div>

              {/* Category Filter Pills */}
              <div className="grid grid-cols-4 gap-1 p-0.5 bg-zinc-900 border border-zinc-800/80 rounded-lg text-[10px] font-medium mb-2">
                <button
                  type="button"
                  onClick={() => setPanelFilter("all")}
                  className={`py-1 rounded text-center transition-colors ${
                    panelFilter === "all"
                      ? "bg-zinc-800 text-zinc-100 font-semibold shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  All ({panels.length})
                </button>
                <button
                  type="button"
                  onClick={() => setPanelFilter("flagged")}
                  className={`py-1 rounded text-center transition-colors ${
                    panelFilter === "flagged"
                      ? "bg-amber-950/80 text-amber-200 font-semibold border border-amber-800"
                      : "text-zinc-400 hover:text-amber-300"
                  }`}
                  title="Panels with flagged regions needing review"
                >
                  ⚠️ Flagged ({panels.filter((p) => textRegions.some((tr) => tr.panel_id === p.id && tr.status === "NEEDS_REVIEW")).length})
                </button>
                <button
                  type="button"
                  onClick={() => setPanelFilter("ready")}
                  className={`py-1 rounded text-center transition-colors ${
                    panelFilter === "ready"
                      ? "bg-emerald-950/80 text-emerald-200 font-semibold border border-emerald-800"
                      : "text-zinc-400 hover:text-emerald-300"
                  }`}
                  title="Panels with all text regions confirmed"
                >
                  ✓ Ready
                </button>
                <button
                  type="button"
                  onClick={() => setPanelFilter("empty")}
                  className={`py-1 rounded text-center transition-colors ${
                    panelFilter === "empty"
                      ? "bg-zinc-800 text-zinc-200 font-semibold"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title="Panels with no detected text regions"
                >
                  No Text
                </button>
              </div>

              {/* Jump to panel input with clear button */}
              <div className="relative mb-2">
                <input
                  type="text"
                  placeholder="Filter or jump #..."
                  value={panelSearchQuery}
                  onChange={(e) => setPanelSearchQuery(e.target.value)}
                  className="w-full px-2.5 py-1.5 pr-6 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
                />
                {panelSearchQuery && (
                  <button
                    type="button"
                    onClick={() => setPanelSearchQuery("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200 text-xs"
                    title="Clear filter"
                  >
                    ✕
                  </button>
                )}
              </div>

              {/* Scrollable vertical panel list */}
              <div className="overflow-y-auto space-y-2 pr-1 flex-1 custom-scrollbar">
                {panels
                  .filter((p) => {
                    const count = textRegions.filter((tr) => tr.panel_id === p.id).length;
                    const hasNeedsReview = textRegions.some(
                      (tr) => tr.panel_id === p.id && tr.status === "NEEDS_REVIEW"
                    );

                    // Category filter
                    if (panelFilter === "flagged" && !hasNeedsReview) return false;
                    if (panelFilter === "ready" && (count === 0 || hasNeedsReview)) return false;
                    if (panelFilter === "empty" && count > 0) return false;

                    // Query search
                    if (!panelSearchQuery.trim()) return true;
                    const q = panelSearchQuery.trim().toLowerCase();
                    if (q === "flagged" || q === "review") return hasNeedsReview;
                    return String(p.sequence).includes(q) || p.id.toLowerCase().includes(q);
                  })
                  .map((p) => {
                    const idx = panels.findIndex((item) => item.id === p.id);
                    const count = textRegions.filter((tr) => tr.panel_id === p.id).length;
                    const hasNeedsReview = textRegions.some(
                      (tr) => tr.panel_id === p.id && tr.status === "NEEDS_REVIEW"
                    );
                    const isSelected = idx === selectedPanelIndex;

                    return (
                      <div
                        key={p.id}
                        ref={(el) => {
                          panelItemRefs.current[p.id] = el;
                        }}
                        onClick={() => handleNavigatePanel(idx)}
                        className={`group relative p-2 rounded-lg border text-left cursor-pointer transition-all ${
                          isSelected
                            ? "bg-gradient-to-r from-indigo-950/80 via-zinc-900/90 to-zinc-900 border-indigo-500 border-l-4 shadow-xl ring-1 ring-indigo-500/40"
                            : "bg-zinc-900/70 hover:bg-zinc-800/80 border-zinc-800/90 hover:border-zinc-700"
                        }`}
                      >
                        {/* Panel Top Row: Sequence + Delete Button */}
                        <div className="flex items-center justify-between mb-1.5">
                          <span
                            className={`text-xs ${
                              isSelected ? "text-indigo-200 font-bold" : "text-zinc-300 font-medium"
                            }`}
                          >
                            Panel #{p.sequence}
                          </span>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleteConfirmPanel(p);
                            }}
                            className="p-1 rounded text-zinc-500 hover:text-rose-400 hover:bg-rose-950/60 opacity-0 group-hover:opacity-100 transition-opacity"
                            title={`Delete Panel #${p.sequence}`}
                            aria-label={`Delete Panel #${p.sequence}`}
                          >
                            <Icons.Trash className="w-3.5 h-3.5" />
                          </button>
                        </div>

                        {/* Panel Thumbnail */}
                        <div className="relative w-full h-24 rounded overflow-hidden bg-zinc-950 border border-zinc-800/80 mb-1.5 flex items-center justify-center">
                          <img
                            src={`${api.getPanelImageUrl(project.id, p.id)}?t=${cacheBuster}`}
                            alt={`Panel ${p.sequence}`}
                            className="w-full h-full object-contain"
                            loading="lazy"
                          />
                          {hasNeedsReview && (
                            <span className="absolute top-1 right-1 px-1.5 py-0.5 rounded bg-amber-900/90 text-amber-200 text-[9px] font-bold border border-amber-700 flex items-center gap-0.5 shadow">
                              ⚠️
                            </span>
                          )}
                        </div>

                        {/* Panel Footer: Region Count & Status */}
                        <div className="flex items-center justify-between text-[10px]">
                          <span className="text-zinc-400 font-mono">
                            {count} {count === 1 ? "region" : "regions"}
                          </span>
                          {hasNeedsReview ? (
                            <span className="text-amber-400 font-medium">Needs Review</span>
                          ) : count > 0 ? (
                            <span className="text-emerald-400 font-medium">✓ Ready</span>
                          ) : (
                            <span className="text-zinc-500 italic">No text</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
              </div>
            </Card>
          </div>
        )}

        {/* Column 2: Visual Panel Crop with SVG TextRegion Overlays & In-Preview Edge Nav */}
        <div
          className={`${
            isVerticalPanelsOpen && panels.length > 0
              ? "lg:col-span-5 xl:col-span-6"
              : "lg:col-span-7"
          } space-y-3`}
        >
          <Card className="p-4 bg-zinc-950 flex flex-col items-center justify-center min-h-[520px]">
            {activePanel ? (
              <div
                onWheel={handleWheel}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                className={`relative inline-block max-w-full overflow-hidden rounded-lg shadow-2xl border border-zinc-800 group/preview select-none ${
                  zoomLevel > 1.0 ? (isPanning ? "cursor-grabbing" : "cursor-grab") : "cursor-default"
                }`}
              >
                {/* Scaled/Panned Content (Image and SVG Overlays in perfect sync) */}
                <div
                  style={{
                    transform: `scale(${zoomLevel}) translate(${panOffset.x / zoomLevel}px, ${panOffset.y / zoomLevel}px)`,
                    transformOrigin: "center center",
                    transition: isPanning ? "none" : "transform 0.12s ease-out",
                  }}
                  className="relative inline-block max-w-full"
                >
                  <img
                    src={`${api.getPanelImageUrl(project.id, activePanel.id)}?t=${cacheBuster}`}
                    alt={`Panel ${activePanel.sequence}`}
                    className="max-h-[68vh] w-auto object-contain block pointer-events-none"
                    draggable={false}
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

                {/* Left Edge Navigation Button: Previous Panel (Vertically Centered) */}
                {selectedPanelIndex > 0 ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleNavigatePanel(selectedPanelIndex - 1);
                    }}
                    className="absolute left-3 top-1/2 -translate-y-1/2 z-30 flex items-center justify-center w-11 h-11 rounded-full bg-zinc-950/85 hover:bg-indigo-600 text-zinc-100 hover:text-white border border-zinc-700 hover:border-indigo-400 shadow-2xl backdrop-blur-md transition-all duration-150 transform hover:scale-110 active:scale-95 focus:outline-none focus:ring-2 focus:ring-indigo-400 cursor-pointer group"
                    title={`Previous Panel (Panel #${panels[selectedPanelIndex - 1]?.sequence}) — Left Arrow key`}
                    aria-label="Previous Panel"
                  >
                    <Icons.ArrowLeft className="w-5 h-5 transition-transform group-hover:-translate-x-0.5" />
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled
                    className="absolute left-3 top-1/2 -translate-y-1/2 z-30 flex items-center justify-center w-11 h-11 rounded-full bg-zinc-950/35 text-zinc-600 border border-zinc-800/50 shadow opacity-30 cursor-not-allowed"
                    title="First panel"
                    aria-label="First panel"
                  >
                    <Icons.ArrowLeft className="w-5 h-5" />
                  </button>
                )}

                {/* Right Edge Navigation Button: Next Panel (Vertically Centered) */}
                {selectedPanelIndex < panels.length - 1 ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleNavigatePanel(selectedPanelIndex + 1);
                    }}
                    className="absolute right-3 top-1/2 -translate-y-1/2 z-30 flex items-center justify-center w-11 h-11 rounded-full bg-zinc-950/85 hover:bg-indigo-600 text-zinc-100 hover:text-white border border-zinc-700 hover:border-indigo-400 shadow-2xl backdrop-blur-md transition-all duration-150 transform hover:scale-110 active:scale-95 focus:outline-none focus:ring-2 focus:ring-indigo-400 cursor-pointer group"
                    title={`Next Panel (Panel #${panels[selectedPanelIndex + 1]?.sequence}) — Right Arrow key`}
                    aria-label="Next Panel"
                  >
                    <Icons.ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-0.5" />
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled
                    className="absolute right-3 top-1/2 -translate-y-1/2 z-30 flex items-center justify-center w-11 h-11 rounded-full bg-zinc-950/35 text-zinc-600 border border-zinc-800/50 shadow opacity-30 cursor-not-allowed"
                    title="Last panel"
                    aria-label="Last panel"
                  >
                    <Icons.ArrowRight className="w-5 h-5" />
                  </button>
                )}

                {/* In-Preview Floating Header Overlay: Indicator & Direct Panel Actions */}
                <div className="absolute top-3 inset-x-3 z-20 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
                  <div className="px-2.5 py-1 rounded-md bg-zinc-950/85 border border-zinc-700/80 backdrop-blur-md text-xs font-semibold text-zinc-200 shadow-lg pointer-events-auto flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></span>
                    <span>Panel #{activePanel.sequence}</span>
                    <span className="text-zinc-500 text-[11px]">
                      ({selectedPanelIndex + 1} / {panels.length})
                    </span>
                    {panelBlurStatus?.is_blurred && (
                      <span className="ml-1 px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 text-[10px] font-bold">
                        BLURRED
                      </span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 pointer-events-auto">
                    {panelBlurStatus?.has_backup && (
                      <button
                        type="button"
                        onClick={handleResetPanelImage}
                        disabled={resettingPanel}
                        className="px-2.5 py-1 rounded-md bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-xs font-medium text-zinc-300 hover:text-white shadow-lg backdrop-blur-md flex items-center gap-1 transition-all cursor-pointer"
                        title="Restore original unblurred image for this panel"
                      >
                        <Icons.Rotate className="w-3.5 h-3.5 text-zinc-400" />
                        <span>Reset Blur</span>
                      </button>
                    )}

                    {panelRegions.length > 0 && (
                      <button
                        type="button"
                        onClick={handleBlurAllPanelText}
                        disabled={blurringPanel}
                        className="px-2.5 py-1 rounded-md bg-amber-950/85 hover:bg-amber-900 border border-amber-800/80 text-xs font-medium text-amber-300 hover:text-amber-100 shadow-lg backdrop-blur-md flex items-center gap-1 transition-all cursor-pointer"
                        title="Blur all detected text regions/watermarks on this panel and in video"
                      >
                        <Icons.EyeOff className="w-3.5 h-3.5" />
                        <span>Blur All Text</span>
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => {
                        if (activePanel) {
                          setCustomBlurBox({
                            x: 0,
                            y: 0,
                            width: Math.min(activePanel.width, 300),
                            height: Math.min(activePanel.height, 100),
                            blur_radius: 24,
                          });
                        }
                        setIsCustomBlurOpen(true);
                      }}
                      className="px-2.5 py-1 rounded-md bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-xs font-medium text-zinc-300 hover:text-white shadow-lg backdrop-blur-md flex items-center gap-1 transition-all cursor-pointer"
                      title="Blur a custom area, banner, or watermark box"
                    >
                      <span>Blur Box...</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleBlurEntirePanel}
                      disabled={blurringPanel}
                      className="px-2.5 py-1 rounded-md bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-xs font-medium text-zinc-300 hover:text-white shadow-lg backdrop-blur-md flex items-center gap-1 transition-all cursor-pointer"
                      title="Blur entire panel image (recommended for ad/recommendation panels)"
                    >
                      <span>Blur Panel</span>
                    </button>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteConfirmPanel(activePanel);
                      }}
                      disabled={deletingPanel}
                      className="px-2.5 py-1 rounded-md bg-rose-950/85 hover:bg-rose-900 border border-rose-800/80 text-xs font-medium text-rose-200 hover:text-white shadow-lg backdrop-blur-md flex items-center gap-1 transition-all hover:scale-105 active:scale-95 cursor-pointer"
                      title={`Delete Panel #${activePanel.sequence}`}
                    >
                      <Icons.Trash className="w-3.5 h-3.5" />
                      <span>Delete</span>
                    </button>
                  </div>
                </div>

                {/* Floating Zoom & Pan Controls (Bottom Right) */}
                <div className="absolute bottom-3 right-3 z-30 flex items-center gap-1 bg-zinc-950/90 backdrop-blur-md border border-zinc-700/80 rounded-lg p-1 shadow-2xl text-zinc-300">
                  <button
                    type="button"
                    onClick={handleZoomOut}
                    disabled={zoomLevel <= 0.5}
                    className="p-1.5 hover:bg-zinc-800 disabled:opacity-40 rounded text-zinc-300 hover:text-white transition-colors"
                    title="Zoom Out (or Ctrl + Wheel Down)"
                  >
                    <Icons.ZoomOut className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={handleZoomReset}
                    className="px-2 py-1 hover:bg-zinc-800 rounded font-mono text-[11px] font-semibold text-zinc-200 hover:text-white transition-colors min-w-[3.5rem] text-center"
                    title="Reset Zoom to 100%"
                  >
                    {Math.round(zoomLevel * 100)}%
                  </button>
                  <button
                    type="button"
                    onClick={handleZoomIn}
                    disabled={zoomLevel >= 3.0}
                    className="p-1.5 hover:bg-zinc-800 disabled:opacity-40 rounded text-zinc-300 hover:text-white transition-colors"
                    title="Zoom In (or Ctrl + Wheel Up)"
                  >
                    <Icons.ZoomIn className="w-4 h-4" />
                  </button>
                  {zoomLevel !== 1.0 && (
                    <button
                      type="button"
                      onClick={handleZoomReset}
                      className="p-1.5 hover:bg-zinc-800 rounded text-indigo-400 hover:text-indigo-300 transition-colors border-l border-zinc-800 ml-0.5"
                      title="Reset Pan & Zoom"
                    >
                      <Icons.Rotate className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-zinc-500 text-sm py-16 flex flex-col items-center gap-2">
                <Icons.AlertTriangle className="w-8 h-8 text-zinc-600" />
                <span>No panels available in this project.</span>
              </div>
            )}
          </Card>

          {/* Panel Quick Scrubber & Navigation Track */}
          {panels.length > 0 && (
            <div className="flex items-center justify-between gap-3 px-4 py-2 bg-zinc-900/60 border border-zinc-800/80 rounded-xl text-xs">
              <div className="flex items-center gap-2 text-zinc-400 font-medium flex-shrink-0">
                <Icons.Film className="w-3.5 h-3.5 text-indigo-400" />
                <span className="text-zinc-200 font-mono font-bold">
                  Panel {selectedPanelIndex + 1}
                </span>
                <span className="text-zinc-500 font-mono">/ {panels.length}</span>
              </div>

              <div className="flex-1 max-w-md mx-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleNavigatePanel(selectedPanelIndex - 1)}
                  disabled={selectedPanelIndex <= 0}
                  className="p-1 hover:bg-zinc-800 disabled:opacity-30 rounded text-zinc-400 hover:text-white transition-colors"
                  title="Previous Panel (←)"
                >
                  <Icons.ArrowLeft className="w-3.5 h-3.5" />
                </button>
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, panels.length - 1)}
                  value={selectedPanelIndex}
                  onChange={(e) => handleNavigatePanel(Number(e.target.value))}
                  className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-zinc-800 rounded-lg appearance-none"
                  title="Scrub across panels"
                />
                <button
                  type="button"
                  onClick={() => handleNavigatePanel(selectedPanelIndex + 1)}
                  disabled={selectedPanelIndex >= panels.length - 1}
                  className="p-1 hover:bg-zinc-800 disabled:opacity-30 rounded text-zinc-400 hover:text-white transition-colors"
                  title="Next Panel (→)"
                >
                  <Icons.ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                {needsReviewCount > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const firstFlagged = textRegions.find((tr) => tr.status === "NEEDS_REVIEW");
                      if (firstFlagged) {
                        const targetIdx = panels.findIndex((p) => p.id === firstFlagged.panel_id);
                        if (targetIdx >= 0) handleNavigatePanel(targetIdx);
                        setSelectedRegionId(firstFlagged.id);
                        showToast(`Jumped to flagged region in Panel #${panels[targetIdx]?.sequence}`, "warn");
                      }
                    }}
                    className="text-[11px] h-7 text-amber-300 hover:bg-amber-950/60 border border-amber-800/60 flex items-center gap-1.5"
                  >
                    <Icons.AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                    <span>Next Flagged</span>
                    <span className="px-1.5 py-0.2 rounded-full bg-amber-900 text-[10px] font-bold text-amber-200">
                      {needsReviewCount}
                    </span>
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right (5 cols): 3-Layer Region Editor & Region List */}
        <div
          className={`${
            isVerticalPanelsOpen && panels.length > 0
              ? "lg:col-span-4 xl:col-span-4"
              : "lg:col-span-5"
          } space-y-4`}
        >
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
                    variant="secondary"
                    size="sm"
                    onClick={() => handleBlurRegion(selectedRegion.id)}
                    loading={blurringRegion}
                    className={`text-xs ${
                      selectedRegion.status === "BLURRED" || selectedRegion.region_type === "REDACTED"
                        ? "bg-amber-950/70 text-amber-300 border-amber-800"
                        : "text-amber-400 hover:text-amber-300 hover:bg-amber-950/40 border-amber-800/60"
                    }`}
                    title="Blur this text directly on the panel crop and in the video (redacts watermarks, site credits, subscribe notes)"
                  >
                    <Icons.EyeOff className="w-3.5 h-3.5 mr-1" />
                    {selectedRegion.status === "BLURRED" || selectedRegion.region_type === "REDACTED" ? "Re-blur" : "Blur Text"}
                  </Button>
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
                    Layer 1: Machine OCR
                  </span>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                        (selectedRegion.raw_confidence || 0) >= 0.85
                          ? "bg-emerald-950/80 text-emerald-300 border-emerald-800"
                          : (selectedRegion.raw_confidence || 0) >= 0.6
                          ? "bg-amber-950/80 text-amber-300 border-amber-800"
                          : "bg-rose-950/80 text-rose-300 border-rose-800"
                      }`}
                    >
                      Confidence:{" "}
                      {selectedRegion.raw_confidence != null
                        ? `${(selectedRegion.raw_confidence * 100).toFixed(0)}%`
                        : "Unextracted"}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        if (selectedRegion.raw_text) {
                          navigator.clipboard?.writeText(selectedRegion.raw_text);
                          setCopiedRawText(true);
                          setTimeout(() => setCopiedRawText(false), 1500);
                          showToast("Raw machine text copied to clipboard", "success");
                        }
                      }}
                      disabled={!selectedRegion.raw_text}
                      className="px-2 py-0.5 rounded bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 hover:text-white border border-zinc-700 text-[10px] flex items-center gap-1 transition-colors disabled:opacity-40"
                      title="Copy raw machine OCR text"
                    >
                      {copiedRawText ? (
                        <>
                          <Icons.Check className="w-3 h-3 text-emerald-400" />
                          <span className="text-emerald-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <Icons.Copy className="w-3 h-3" />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
                <div className="bg-zinc-950 p-2.5 rounded border border-zinc-800/80">
                  <p className="text-xs font-mono text-zinc-300 select-all min-h-[2.5rem] leading-relaxed">
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
                  rows={4}
                  value={editForm.corrected_text}
                  onChange={(e) => setEditForm({ ...editForm, corrected_text: e.target.value })}
                  onKeyDown={(e) => {
                    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                      e.preventDefault();
                      handleSaveAndNextRegion();
                    }
                  }}
                  disabled={extracting}
                  placeholder="Enter or correct dialogue text... (Press Ctrl + Enter to confirm and advance)"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500 resize-none font-sans leading-relaxed"
                />

                {/* Quick Formatting Chips */}
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <button
                    type="button"
                    onClick={() => {
                      const trimmed = editForm.corrected_text.replace(/\s+/g, " ").trim();
                      setEditForm((prev) => ({ ...prev, corrected_text: trimmed }));
                      showToast("Trimmed whitespace", "info");
                    }}
                    className="px-2 py-0.5 rounded bg-zinc-800/90 hover:bg-zinc-700 border border-zinc-700/60 text-[10px] text-zinc-300 transition-colors"
                    title="Collapse repeated whitespace into single space and trim edges"
                  >
                    Trim Spaces
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const cleaned = editForm.corrected_text
                        .replace(/[「『]/g, '"')
                        .replace(/[」』]/g, '"')
                        .replace(/[""]/g, '"')
                        .replace(/['']/g, "'");
                      setEditForm((prev) => ({ ...prev, corrected_text: cleaned }));
                      showToast("Standardized quotes", "info");
                    }}
                    className="px-2 py-0.5 rounded bg-zinc-800/90 hover:bg-zinc-700 border border-zinc-700/60 text-[10px] text-zinc-300 transition-colors"
                    title="Convert Japanese brackets 「」 and curved quotes to standard quotes"
                  >
                    Fix Quotes
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const sentence = editForm.corrected_text.replace(
                        /(^\s*\w|[.!?]\s*\w)/g,
                        (c) => c.toUpperCase()
                      );
                      setEditForm((prev) => ({ ...prev, corrected_text: sentence }));
                      showToast("Sentence capitalized", "info");
                    }}
                    className="px-2 py-0.5 rounded bg-zinc-800/90 hover:bg-zinc-700 border border-zinc-700/60 text-[10px] text-zinc-300 transition-colors"
                    title="Capitalize first letter of each sentence"
                  >
                    Sentence Case
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEditForm((prev) => ({ ...prev, corrected_text: "" }));
                      showToast("Text cleared", "warn");
                    }}
                    className="px-2 py-0.5 rounded bg-zinc-800/90 hover:bg-zinc-700 border border-zinc-700/60 text-[10px] text-zinc-400 hover:text-zinc-200 transition-colors ml-auto"
                    title="Clear text"
                  >
                    Clear
                  </button>
                </div>
              </div>

              {/* Classification & Status Controls */}
              <div className="space-y-2 pt-1 border-t border-zinc-800/80">
                <label className="text-[10px] text-zinc-400 font-semibold uppercase tracking-wider block">
                  Region Classification:
                </label>
                <div className="grid grid-cols-5 gap-1.5">
                  {[
                    { id: "SPEECH", label: "Speech", color: "#0ea5e9" },
                    { id: "NARRATION", label: "Narration", color: "#eab308" },
                    { id: "THOUGHT", label: "Thought", color: "#a855f7" },
                    { id: "SFX", label: "SFX", color: "#ec4899" },
                    { id: "CAPTION", label: "Caption", color: "#14b8a6" },
                  ].map((cat) => {
                    const isSelected = editForm.region_type === cat.id;
                    return (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => setEditForm((prev) => ({ ...prev, region_type: cat.id }))}
                        disabled={extracting}
                        className={`py-1 rounded text-center text-[10px] font-semibold transition-all border ${
                          isSelected
                            ? "bg-zinc-950 text-white shadow-md ring-2"
                            : "bg-zinc-950/60 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 border-zinc-800"
                        }`}
                        style={{
                          borderColor: isSelected ? cat.color : undefined,
                          boxShadow: isSelected ? `0 0 10px ${cat.color}33` : undefined,
                        }}
                      >
                        {cat.label}
                      </button>
                    );
                  })}
                </div>

                <div className="grid grid-cols-2 gap-2.5 pt-1">
                  <div>
                    <label className="text-[10px] text-zinc-400 font-medium block mb-1">
                      More Types:
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
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-zinc-800">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleApproveRegion(selectedRegion.id)}
                  disabled={extracting || savingRegion}
                  className="text-xs bg-emerald-950/40 text-emerald-300 border-emerald-800/80 hover:bg-emerald-900/60"
                >
                  <Icons.Check className="w-3.5 h-3.5 mr-1" />
                  Mark Confirmed
                </Button>

                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleSaveRegion}
                    disabled={extracting}
                    loading={savingRegion}
                    className="text-xs text-zinc-300 hover:text-white"
                  >
                    Save
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleSaveAndNextRegion}
                    disabled={extracting}
                    loading={savingRegion}
                    className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-1 shadow-lg shadow-indigo-950/50"
                    title="Confirm this region and auto-advance to next (Ctrl + Enter)"
                  >
                    <span>Approve & Next</span>
                    <span className="text-[10px] opacity-75 font-mono">↵</span>
                  </Button>
                </div>
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

      {/* Delete Panel Confirmation Modal */}
      {deleteConfirmPanel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fadeIn">
          <Card className="max-w-md w-full p-6 bg-zinc-900 border-zinc-700 shadow-2xl space-y-4">
            <div className="flex items-start gap-3.5">
              <div className="p-3 rounded-full bg-rose-950 border border-rose-800 text-rose-400 flex-shrink-0">
                <Icons.Trash className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h3 className="text-base font-semibold text-zinc-100">
                  Delete Panel #{deleteConfirmPanel.sequence}?
                </h3>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Are you sure you want to delete this panel crop from the project? This operation cannot be undone.
                </p>
                {textRegions.filter((tr) => tr.panel_id === deleteConfirmPanel.id).length > 0 && (
                  <div className="mt-2.5 p-2.5 rounded bg-amber-950/40 border border-amber-800/60 text-xs text-amber-300 flex items-center gap-2">
                    <Icons.AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                    <span>
                      <strong>Warning:</strong> {textRegions.filter((tr) => tr.panel_id === deleteConfirmPanel.id).length} detected text region(s) inside this panel will also be removed.
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-2.5 pt-3 border-t border-zinc-800">
              <Button
                variant="ghost"
                size="sm"
                disabled={deletingPanel}
                onClick={() => setDeleteConfirmPanel(null)}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                loading={deletingPanel}
                onClick={() => handleDeletePanel(deleteConfirmPanel.id)}
                className="bg-rose-600 hover:bg-rose-500 text-white"
              >
                Yes, Delete Panel
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Custom Blur Area Modal */}
      {isCustomBlurOpen && activePanel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <Card className="max-w-md w-full p-5 bg-zinc-900 border-zinc-800 space-y-4 shadow-2xl">
            <div className="flex items-start justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-amber-950 border border-amber-800 text-amber-400">
                  <Icons.EyeOff className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-zinc-100">
                    Blur Custom Area on Panel #{activePanel.sequence}
                  </h3>
                  <p className="text-xs text-zinc-400">
                    Blur site names, recommendations, subscribe notes, or logos.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsCustomBlurOpen(false)}
                className="text-zinc-500 hover:text-zinc-300"
              >
                ✕
              </button>
            </div>

            {/* Quick Presets */}
            <div className="space-y-1.5">
              <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                Quick Placement Presets
              </span>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setCustomBlurBox({
                      x: 0,
                      y: 0,
                      width: activePanel.width,
                      height: Math.min(activePanel.height, 90),
                      blur_radius: 24,
                    })
                  }
                  className="text-xs text-zinc-300 border-zinc-700 hover:bg-zinc-800"
                >
                  Top Watermark Banner
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setCustomBlurBox({
                      x: 0,
                      y: Math.max(0, activePanel.height - 110),
                      width: activePanel.width,
                      height: 110,
                      blur_radius: 24,
                    })
                  }
                  className="text-xs text-zinc-300 border-zinc-700 hover:bg-zinc-800"
                >
                  Bottom Subscribe Note
                </Button>
              </div>
            </div>

            {/* Coordinate inputs */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="text-[10px] text-zinc-400 block mb-1">X Offset (px):</label>
                <input
                  type="number"
                  value={customBlurBox.x}
                  min={0}
                  max={activePanel.width}
                  onChange={(e) =>
                    setCustomBlurBox({ ...customBlurBox, x: parseInt(e.target.value) || 0 })
                  }
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-zinc-100 font-mono"
                />
              </div>
              <div>
                <label className="text-[10px] text-zinc-400 block mb-1">Y Offset (px):</label>
                <input
                  type="number"
                  value={customBlurBox.y}
                  min={0}
                  max={activePanel.height}
                  onChange={(e) =>
                    setCustomBlurBox({ ...customBlurBox, y: parseInt(e.target.value) || 0 })
                  }
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-zinc-100 font-mono"
                />
              </div>
              <div>
                <label className="text-[10px] text-zinc-400 block mb-1">Width (px):</label>
                <input
                  type="number"
                  value={customBlurBox.width}
                  min={10}
                  max={activePanel.width}
                  onChange={(e) =>
                    setCustomBlurBox({ ...customBlurBox, width: parseInt(e.target.value) || 10 })
                  }
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-zinc-100 font-mono"
                />
              </div>
              <div>
                <label className="text-[10px] text-zinc-400 block mb-1">Height (px):</label>
                <input
                  type="number"
                  value={customBlurBox.height}
                  min={10}
                  max={activePanel.height}
                  onChange={(e) =>
                    setCustomBlurBox({ ...customBlurBox, height: parseInt(e.target.value) || 10 })
                  }
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-zinc-100 font-mono"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2.5 pt-3 border-t border-zinc-800">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsCustomBlurOpen(false)}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                loading={blurringPanel}
                onClick={handleBlurCustomBox}
                className="bg-amber-600 hover:bg-amber-500 text-white font-medium"
              >
                <Icons.EyeOff className="w-4 h-4 mr-1.5" />
                Apply Blur
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Non-blocking Floating Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-zinc-900/95 border border-zinc-700 text-zinc-100 rounded-full shadow-2xl flex items-center gap-2 text-xs backdrop-blur-md pointer-events-none transition-all animate-fadeIn">
          {toastMessage.type === "success" && <Icons.CheckCircle className="w-4 h-4 text-emerald-400" />}
          {toastMessage.type === "warn" && <Icons.AlertTriangle className="w-4 h-4 text-amber-400" />}
          {toastMessage.type === "info" && <Icons.Info className="w-4 h-4 text-indigo-400" />}
          <span className="font-medium">{toastMessage.text}</span>
        </div>
      )}
    </div>
  );
};
