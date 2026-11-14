import React, { useState, useMemo } from "react";
import { Icons, Button, Badge } from "@panelflow/ui";
import { api } from "@panelflow/api-client";
import {
  type NarrationSegment,
  type CharacterProfile,
  type ReviewStatus,
  type ContinuityCheckResult,
  type PageScriptRecord,
  computeContentHash,
} from "./NarrationStudio.types";

interface NarrationSegmentEditorProps {
  segment: NarrationSegment | null;
  previousSegment: NarrationSegment | null;
  nextSegment: NarrationSegment | null;
  characters: CharacterProfile[];
  projectId?: string;
  pageScript?: PageScriptRecord | null;
  allPageScripts?: Record<string, PageScriptRecord>;
  onUpdateSegment: (updates: Partial<NarrationSegment>) => void;
  onUpdatePageScript?: (pageId: string, updates: Partial<PageScriptRecord>) => void;
  onDuplicateSegment: (segmentId: string) => void;
  onDeleteSegment: (segmentId: string) => void;
  onSplitSegment: (segmentId: string, splitIndex: number) => void;
  onSynthesizeSceneVoice?: (segment: NarrationSegment) => void;
  onAddToTimeline?: (segment: NarrationSegment) => void;
  onHarmonizeSegment?: (segment: NarrationSegment) => void;
  isSynthesizing?: boolean;
  className?: string;
}

export type ScriptEditorTab = "final" | "page" | "panel" | "compare";

export const NarrationSegmentEditor: React.FC<NarrationSegmentEditorProps> = ({
  segment,
  previousSegment,
  nextSegment,
  characters,
  projectId = "",
  pageScript,
  allPageScripts,
  onUpdateSegment,
  onUpdatePageScript,
  onDuplicateSegment,
  onDeleteSegment,
  onSplitSegment,
  onSynthesizeSceneVoice,
  onAddToTimeline,
  onHarmonizeSegment,
  isSynthesizing = false,
  className = "",
}) => {
  // Active script view tab: "final" | "page" | "panel" | "compare"
  const [activeTab, setActiveTab] = useState<ScriptEditorTab>("final");

  // Visual image mode toggle: "panel" (cropped panel) or "page" (full page image)
  const [imageMode, setImageMode] = useState<"panel" | "page">("panel");

  // Typography presentation settings
  const [fontFamily, setFontFamily] = useState<"sans" | "serif">("serif");
  const [fontSize, setFontSize] = useState<"sm" | "base" | "lg">("base");
  const [showContinuityDetails, setShowContinuityDetails] = useState<boolean>(false);
  const [isAnalyzingVision, setIsAnalyzingVision] = useState<boolean>(false);
  const [isLightboxOpen, setIsLightboxOpen] = useState<boolean>(false);

  // Character mapping
  const currentCharacter = useMemo(() => {
    if (!segment) return null;
    return characters.find((c) => c.id === segment.speaker_id) || null;
  }, [segment, characters]);

  // Resolve active page script record
  const resolvedPageScript = useMemo(() => {
    if (pageScript) return pageScript;
    if (!segment || !allPageScripts) return null;
    const pageId = segment.source_context.page_id;
    const pageSeq = String(segment.source_context.page_number || 1);
    return allPageScripts[pageId] || allPageScripts[pageSeq] || null;
  }, [pageScript, segment, allPageScripts]);

  // Live calculation of word count and reading duration
  const wordCount = useMemo(() => {
    if (!segment) return 0;
    return segment.narration_text.trim().split(/\s+/).filter(Boolean).length;
  }, [segment?.narration_text]);

  const estimatedDuration = useMemo(() => {
    if (!segment) return 0;
    const baseWps = 2.33;
    const speed = segment.delivery.speech_speed || 1.0;
    const effectiveWps = baseWps * speed;
    const pauseBonus = (segment.delivery.pause?.duration_ms || 0) / 1000;
    const calculated = (wordCount / (effectiveWps || 1)) + pauseBonus;
    return Math.max(1.2, Math.round(calculated * 10) / 10);
  }, [wordCount, segment?.delivery.speech_speed, segment?.delivery.pause]);

  // Target panel time budget (e.g. 5.0 to 9.0 sec per panel)
  const targetPanelBudgetSec = useMemo(() => {
    if (segment?.source_context.panel_duration_budget_sec) {
      return segment.source_context.panel_duration_budget_sec;
    }
    return 7.0; // standard default video panel display window
  }, [segment?.source_context.panel_duration_budget_sec]);

  // Pacing sync status
  const syncStatus = useMemo(() => {
    if (!segment) return { status: "good", label: "Ready", diff: 0 };
    const diff = estimatedDuration - targetPanelBudgetSec;
    if (Math.abs(diff) <= 1.8) {
      return { status: "perfect", label: "🟢 Synced with Panel", diff };
    }
    if (diff > 1.8) {
      return { status: "long", label: `🟡 Long (+${diff.toFixed(1)}s)`, diff };
    }
    return { status: "short", label: `🟡 Short (${diff.toFixed(1)}s)`, diff };
  }, [estimatedDuration, targetPanelBudgetSec, segment]);

  // Auto-fit speech speed to match target panel window
  const handleAutoFitSpeed = () => {
    if (!segment || wordCount === 0) return;
    const baseWps = 2.33;
    const pauseBonus = (segment.delivery.pause?.duration_ms || 0) / 1000;
    const neededSpeechSec = Math.max(1.5, targetPanelBudgetSec - pauseBonus);
    const targetWps = wordCount / neededSpeechSec;
    const targetSpeed = Math.min(1.35, Math.max(0.85, Math.round((targetWps / baseWps) * 100) / 100));

    onUpdateSegment({
      delivery: {
        ...segment.delivery,
        speech_speed: targetSpeed,
      },
      updated_at: new Date().toISOString(),
    });
  };

  // Continuity analysis check between adjacent segments
  const continuityAlert: ContinuityCheckResult | null = useMemo(() => {
    if (!segment) return null;

    if (previousSegment) {
      const prevEmo = previousSegment.delivery.emotion;
      const curEmo = segment.delivery.emotion;
      if (
        (prevEmo === "Happy" && curEmo === "Fearful") ||
        (prevEmo === "Whispering" && curEmo === "Excited") ||
        (prevEmo === "Fearful" && curEmo === "Happy")
      ) {
        return {
          has_issue: true,
          severity: "warning",
          message: `Sharp tone transition from ${previousSegment.speaker_name}'s "${prevEmo}" to "${curEmo}".`,
          suggested_action: "Consider smoothing the transition or adding a pause.",
          previous_speaker: previousSegment.speaker_name,
          previous_emotion: prevEmo,
        };
      }

      const prevStart = previousSegment.narration_text.trim().split(/\s+/)[0]?.toLowerCase();
      const curStart = segment.narration_text.trim().split(/\s+/)[0]?.toLowerCase();
      if (prevStart && curStart && prevStart === curStart && prevStart.length > 3) {
        return {
          has_issue: true,
          severity: "info",
          message: `Consecutive segments start with the same word ("${curStart}").`,
          suggested_action: "Vary the sentence structure for better storytelling flow.",
          previous_speaker: previousSegment.speaker_name,
        };
      }
    }

    if (wordCount > 38 && (!segment.delivery.pause || segment.delivery.pause.preset === "none")) {
      return {
        has_issue: true,
        severity: "info",
        message: "Long narration segment without designated pauses.",
        suggested_action: "Add an intentional breath pause to improve TTS pacing.",
      };
    }

    return null;
  }, [segment, previousSegment, wordCount]);

  // Handle text edit
  const handleTextChange = (newText: string) => {
    if (!segment) return;
    const newRevision = (segment.text_revision || 1) + 1;
    const newHash = computeContentHash(
      newText,
      segment.delivery.emotion,
      segment.delivery.speech_speed,
      segment.delivery.pause?.preset
    );

    onUpdateSegment({
      narration_text: newText,
      text_revision: newRevision,
      content_hash: newHash,
      estimated_duration_sec: estimatedDuration,
      generation_status:
        segment.generation_status === "READY" ? "OUTDATED" : segment.generation_status,
      previous_audio_asset_uri:
        segment.audio_asset_uri || segment.previous_audio_asset_uri || null,
      audio_asset_uri: null,
      updated_at: new Date().toISOString(),
    });
  };

  if (!segment) {
    return (
      <div className={`flex flex-col items-center justify-center p-12 text-center text-fg-faint bg-ink ${className}`}>
        <div className="w-12 h-12 rounded-2xl bg-navy border border-edge flex items-center justify-center text-fg-dim mb-3 shadow-inner">
          <Icons.FileText className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-semibold text-fg-dim mb-1">No Story Beat Selected</h3>
        <p className="text-xs max-w-sm text-fg-faint">
          Select a story beat from the left panel to edit its script, review the 5-10 line page story, or align audio timing.
        </p>
      </div>
    );
  }

  // Visual Image Resolution
  const primaryPanelId = segment.source_context.panel_ids?.[0];
  const primaryPageId = segment.source_context.page_id;
  const rawUrl = segment.source_context.panel_preview_url || segment.source_context.image_url;

  let activeImgUrl = "";
  if (imageMode === "page" && projectId && primaryPageId) {
    activeImgUrl = api.getPageImageUrl(projectId, primaryPageId);
  } else if (projectId && primaryPanelId) {
    activeImgUrl = api.getPanelImageUrl(projectId, primaryPanelId);
  } else if (rawUrl) {
    activeImgUrl = rawUrl.startsWith("http") || rawUrl.startsWith("data:")
      ? rawUrl
      : `http://127.0.0.1:8765${rawUrl.startsWith("/") ? "" : "/"}${rawUrl}`;
  } else if (projectId && primaryPageId) {
    activeImgUrl = api.getPageImageUrl(projectId, primaryPageId);
  }

  const handleReanalyzeVision = async () => {
    if (!projectId || !primaryPanelId) return;
    setIsAnalyzingVision(true);
    try {
      const res = await api.analyzePanelVision(projectId, primaryPanelId);
      if (res?.visual_description) {
        onUpdateSegment({
          source_context: {
            ...segment.source_context,
            visual_description: res.visual_description,
          },
        });
      }
    } catch (err: any) {
      console.warn("Vision analysis failed:", err);
    } finally {
      setIsAnalyzingVision(false);
    }
  };

  // 5-10 line page script lines
  const pageLines = resolvedPageScript?.lines || (
    segment.page_narration_text ? segment.page_narration_text.split(/\n+/).filter(Boolean) : []
  );

  return (
    <div className={`flex flex-col bg-ink overflow-y-auto ${className}`}>
      {/* Top Header: Scene, Speaker & Status */}
      <div className="p-4 border-b border-edge/80 bg-navy/30 space-y-3 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-6 h-6 rounded-md bg-accent text-white font-mono text-xs font-bold flex items-center justify-center shadow-sm">
              #{segment.sequence}
            </span>
            <div>
              <h3 className="text-sm font-bold text-fg flex items-center gap-2">
                <span>{segment.scene_title || `Scene ${segment.sequence}`}</span>
                <span className="text-xs text-fg-faint font-normal">
                  — {segment.source_context.panel_labels?.[0] || `Panel #${segment.sequence}`}
                </span>
              </h3>
              <p className="text-[11px] text-fg-dim">
                Speaker: <span className="text-info font-semibold">{segment.speaker_name}</span>{" "}
                <span className="text-fg-faint font-mono text-[10px]">({segment.speaker_type})</span>
              </p>
            </div>
          </div>

          {/* Review Status Selector */}
          <div className="flex items-center bg-ink p-0.5 rounded-lg border border-edge text-xs">
            {(["DRAFT", "NEEDS_REVIEW", "APPROVED"] as ReviewStatus[]).map((status) => {
              const isActive = segment.review_status === status;
              return (
                <button
                  key={status}
                  type="button"
                  onClick={() => onUpdateSegment({ review_status: status })}
                  className={`px-3 py-1 rounded text-xs font-semibold transition-all flex items-center gap-1.5 ${
                    isActive
                      ? status === "APPROVED"
                        ? "bg-ok text-white shadow-sm"
                        : status === "NEEDS_REVIEW"
                        ? "bg-warn text-white shadow-sm"
                        : "bg-glass-hi text-white shadow-sm"
                      : "text-fg-dim hover:text-fg hover:bg-navy"
                  }`}
                >
                  {status === "APPROVED" ? (
                    <>
                      <Icons.Check className="w-3.5 h-3.5" />
                      <span>Approved</span>
                    </>
                  ) : status === "NEEDS_REVIEW" ? (
                    <>
                      <Icons.AlertTriangle className="w-3.5 h-3.5" />
                      <span>Needs Review</span>
                    </>
                  ) : (
                    "Draft"
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Scene Binding & Pacing Offset */}
        <div className="flex items-center justify-between p-2 rounded-lg bg-ink/80 border border-edge text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-info">
              Scene Binding:
            </span>
            <button
              type="button"
              onClick={() => onUpdateSegment({ linked_to_scene: !segment.linked_to_scene })}
              className={`px-2.5 py-1 rounded text-[11px] font-semibold border transition-colors flex items-center gap-1.5 ${
                segment.linked_to_scene
                  ? "bg-accent/20 text-info border-accent/40 shadow-sm"
                  : "bg-navy text-fg-dim border-edge"
              }`}
            >
              {segment.linked_to_scene ? (
                <>
                  <Icons.Link className="w-3 h-3 text-info" />
                  <span>Linked to Scene Start</span>
                </>
              ) : (
                <>
                  <Icons.Unlink className="w-3 h-3 text-fg-dim" />
                  <span>Unlinked (Floating)</span>
                </>
              )}
            </button>
          </div>

          <div className="flex items-center gap-1.5 text-fg-dim text-[11px]">
            <span>Scene Offset:</span>
            <input
              type="number"
              step="0.1"
              min="-10"
              max="60"
              value={segment.scene_offset_sec ?? 0}
              onChange={(e) => onUpdateSegment({ scene_offset_sec: parseFloat(e.target.value) || 0 })}
              className="w-14 bg-navy border border-edge rounded px-1.5 py-0.5 font-mono text-fg text-center focus:outline-none focus:border-accent"
            />
            <span className="text-fg-faint font-mono text-[10px]">sec</span>
          </div>
        </div>

        {/* Continuity Alert Banner */}
        {continuityAlert && (
          <div
            className={`flex items-start justify-between p-2.5 rounded-lg border text-xs ${
              continuityAlert.severity === "warning"
                ? "bg-warn/40 border-warn/80 text-warn"
                : "bg-accent/40 border-accent/80 text-info"
            }`}
          >
            <div className="flex items-start gap-2">
              <span className="shrink-0 mt-0.5">
                {continuityAlert.severity === "warning" ? (
                  <Icons.AlertTriangle className="w-4 h-4 text-warn" />
                ) : (
                  <Icons.Sparkles className="w-4 h-4 text-info" />
                )}
              </span>
              <div>
                <p className="font-semibold">{continuityAlert.message}</p>
                {continuityAlert.suggested_action && (
                  <p className="text-[11px] opacity-80 mt-0.5">
                    Suggestion: {continuityAlert.suggested_action}
                  </p>
                )}
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowContinuityDetails((v) => !v)}
              className="text-[10px] underline font-semibold opacity-75 hover:opacity-100 shrink-0 ml-2"
            >
              {showContinuityDetails ? "Hide Flow" : "Flow Context"}
            </button>
          </div>
        )}
      </div>

      {/* Main Working Area */}
      <div className="p-4 space-y-4 flex-1">
        {/* Visual Evidence Card with Panel/Page Toggle */}
        <div className="rounded-xl border border-edge bg-navy/70 p-3.5 space-y-3 shadow-md">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-accent/20 border border-accent/40 flex items-center justify-center text-info">
                <Icons.Image className="w-3.5 h-3.5" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-fg flex items-center gap-1.5">
                  <span>Visual Source</span>
                  <span className="text-fg-faint">•</span>
                  <span className="text-fg-dim font-normal">
                    Page {segment.source_context.page_number} ({segment.source_context.panel_labels?.[0] || `Panel #${segment.sequence}`})
                  </span>
                </h4>
                <span className="text-[10px] text-fg-faint font-mono">
                  Grounded visual evidence for page & panel narration
                </span>
              </div>
            </div>

            {/* Toggle Panel Crop vs Full Page */}
            <div className="flex items-center gap-2">
              <div className="flex items-center bg-ink p-0.5 rounded-lg border border-edge text-[11px]">
                <button
                  type="button"
                  onClick={() => setImageMode("panel")}
                  className={`px-2 py-0.5 rounded transition-all font-semibold ${
                    imageMode === "panel"
                      ? "bg-accent text-white"
                      : "text-fg-dim hover:text-fg"
                  }`}
                >
                  Cropped Panel
                </button>
                <button
                  type="button"
                  onClick={() => setImageMode("page")}
                  className={`px-2 py-0.5 rounded transition-all font-semibold ${
                    imageMode === "page"
                      ? "bg-accent text-white"
                      : "text-fg-dim hover:text-fg"
                  }`}
                >
                  Full Page
                </button>
              </div>

              {primaryPanelId && projectId && (
                <button
                  type="button"
                  onClick={handleReanalyzeVision}
                  disabled={isAnalyzingVision}
                  className="text-[11px] px-2.5 py-1 rounded-lg bg-flat hover:bg-glass-hi text-info font-semibold border border-edge/80 flex items-center gap-1.5 transition-colors disabled:opacity-50"
                  title="Run Vision model on this specific panel"
                >
                  {isAnalyzingVision ? (
                    <>
                      <span className="w-3 h-3 border-2 border-accent/30 border-t-indigo-400 rounded-full animate-spin" />
                      <span>Analyzing...</span>
                    </>
                  ) : (
                    <>
                      <Icons.Sparkles className="w-3.5 h-3.5 text-info" />
                      <span>Re-Analyze</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {/* Visual Thumbnail & Evidence Details */}
          <div className="grid grid-cols-12 gap-3.5 items-stretch">
            {/* Image Thumbnail */}
            <div className="col-span-12 sm:col-span-4 rounded-lg overflow-hidden bg-ink border border-edge relative group flex items-center justify-center min-h-[140px] max-h-[190px]">
              {activeImgUrl ? (
                <>
                  <img
                    src={activeImgUrl}
                    alt="Manga Visual Evidence"
                    className="w-full h-full object-contain cursor-pointer transition-transform duration-200 group-hover:scale-102"
                    onClick={() => setIsLightboxOpen(true)}
                  />
                  <button
                    type="button"
                    onClick={() => setIsLightboxOpen(true)}
                    className="absolute bottom-1.5 right-1.5 p-1 rounded bg-black/70 text-fg-dim hover:text-white backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Click to view full resolution"
                  >
                    <Icons.Maximize className="w-3.5 h-3.5" />
                  </button>
                </>
              ) : (
                <div className="text-fg-faint text-xs flex flex-col items-center">
                  <Icons.Image className="w-6 h-6 mb-1 text-ink" />
                  <span>No Image Available</span>
                </div>
              )}
            </div>

            {/* Evidence details */}
            <div className="col-span-12 sm:col-span-8 flex flex-col justify-between gap-2 text-xs">
              {/* Dialogue */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-ok flex items-center gap-1">
                    <Icons.MessageSquare className="w-3 h-3" />
                    Speech Bubble Dialogue (OCR)
                  </span>
                  {segment.source_context.raw_ocr_dialogue && (
                    <button
                      type="button"
                      onClick={() => handleTextChange(segment.source_context.raw_ocr_dialogue)}
                      className="text-[10px] font-semibold text-ok hover:text-ok underline"
                      title="Copy OCR dialogue text into narration script"
                    >
                      Use as Script
                    </button>
                  )}
                </div>
                {segment.source_context.raw_ocr_dialogue ? (
                  <p className="p-2 rounded-lg bg-ink/80 border border-edge text-fg font-serif italic text-xs leading-relaxed">
                    &ldquo;{segment.source_context.raw_ocr_dialogue}&rdquo;
                  </p>
                ) : (
                  <p className="p-2 rounded-lg bg-ink/40 border border-edge text-fg-faint italic text-[11px]">
                    No dialogue bubbles detected in this panel (Visual exposition or silent beat).
                  </p>
                )}
              </div>

              {/* Visual Action */}
              <div className="space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-info flex items-center gap-1">
                  <Icons.Eye className="w-3 h-3" />
                  Panel Visual Action
                </span>
                <p className="p-2 rounded-lg bg-ink/80 border border-edge text-fg-dim font-sans text-xs leading-relaxed">
                  {segment.source_context.visual_description || "Visual framing ready for story generation."}
                </p>
              </div>

              {/* Page Story Overview Preview */}
              {resolvedPageScript && (
                <div className="space-y-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-warn flex items-center gap-1">
                    <Icons.Sparkles className="w-3 h-3 text-warn" />
                    Page Story Tone & Arc
                  </span>
                  <div className="p-1.5 rounded-lg bg-ink/80 border border-edge text-fg-dim text-[11px] leading-relaxed flex items-center justify-between">
                    <span className="text-warn font-semibold">{resolvedPageScript.tone}</span>
                    <button
                      type="button"
                      onClick={() => setActiveTab("page")}
                      className="text-[10px] text-warn hover:text-warn underline font-semibold"
                    >
                      View All {pageLines.length} Lines →
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 3-TIER SCRIPT WORKFLOW TABS */}
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 pb-1 border-b border-edge">
            {/* Tabs */}
            <div className="flex items-center gap-1 bg-ink p-1 rounded-lg border border-edge text-xs overflow-x-auto no-scrollbar shrink-0">
              <button
                type="button"
                onClick={() => setActiveTab("final")}
                className={`px-3 py-1.5 rounded-md font-semibold transition-all flex items-center gap-1.5 whitespace-nowrap shrink-0 ${
                  activeTab === "final"
                    ? "bg-accent text-white shadow-sm"
                    : "text-fg-dim hover:text-fg hover:bg-navy"
                }`}
              >
                <Icons.Sparkles className="w-3.5 h-3.5 shrink-0" />
                <span className="whitespace-nowrap">Final Synced Script</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("page")}
                className={`px-3 py-1.5 rounded-md font-semibold transition-all flex items-center gap-1.5 whitespace-nowrap shrink-0 ${
                  activeTab === "page"
                    ? "bg-warn text-white shadow-sm"
                    : "text-fg-dim hover:text-fg hover:bg-navy"
                }`}
              >
                <Icons.BookOpen className="w-3.5 h-3.5 shrink-0" />
                <span className="whitespace-nowrap">Page Story (5-10 Lines)</span>
                {pageLines.length > 0 && (
                  <span className="text-[10px] bg-black/40 text-warn px-1.5 py-0.2 rounded font-mono shrink-0">
                    {pageLines.length}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("panel")}
                className={`px-3 py-1.5 rounded-md font-semibold transition-all flex items-center gap-1.5 whitespace-nowrap shrink-0 ${
                  activeTab === "panel"
                    ? "bg-ok text-white shadow-sm"
                    : "text-fg-dim hover:text-fg hover:bg-navy"
                }`}
              >
                <Icons.Eye className="w-3.5 h-3.5 shrink-0" />
                <span className="whitespace-nowrap">Panel Micro Beat</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("compare")}
                className={`px-3 py-1.5 rounded-md font-semibold transition-all flex items-center gap-1.5 whitespace-nowrap shrink-0 ${
                  activeTab === "compare"
                    ? "bg-accent text-white shadow-sm"
                    : "text-fg-dim hover:text-fg hover:bg-navy"
                }`}
              >
                <Icons.Layout className="w-3.5 h-3.5 shrink-0" />
                <span className="whitespace-nowrap">Compare & Harmonize</span>
              </button>
            </div>

            {/* Typography Controls */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 bg-navy border border-edge rounded px-1.5 py-0.5 text-[11px]">
                <button
                  type="button"
                  onClick={() => setFontFamily("sans")}
                  className={`px-1.5 py-0.5 rounded font-sans ${
                    fontFamily === "sans" ? "bg-flat text-white font-bold" : "text-fg-dim"
                  }`}
                >
                  Sans
                </button>
                <button
                  type="button"
                  onClick={() => setFontFamily("serif")}
                  className={`px-1.5 py-0.5 rounded font-serif ${
                    fontFamily === "serif" ? "bg-flat text-white font-bold" : "text-fg-dim"
                  }`}
                >
                  Serif
                </button>
              </div>

              {/* Panel Audio Sync Status Tag */}
              <div className="flex items-center gap-1.5 text-xs font-mono">
                <span className={`px-2 py-0.5 rounded-full font-semibold border ${
                  syncStatus.status === "perfect"
                    ? "bg-ok/70 border-ok/80 text-ok"
                    : "bg-warn/70 border-warn/80 text-warn"
                }`}>
                  {syncStatus.label}
                </span>
                <span className="text-fg-dim">~{estimatedDuration}s ({wordCount}w)</span>
                {syncStatus.status !== "perfect" && (
                  <button
                    type="button"
                    onClick={handleAutoFitSpeed}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-flat hover:bg-glass-hi text-info border border-edge underline"
                    title="Automatically adjust speech speed to fit panel video duration"
                  >
                    Auto-Fit
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* TAB 1: FINAL SYNCED SCRIPT */}
          {activeTab === "final" && (
            <div className="space-y-3">
              <div className="relative group">
                <textarea
                  value={segment.narration_text}
                  onChange={(e) => handleTextChange(e.target.value)}
                  rows={4}
                  className={`w-full p-4 rounded-xl bg-navy/90 border border-edge/80 text-fg placeholder-fg-faint focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 leading-relaxed transition-all shadow-inner ${
                    fontFamily === "serif" ? "font-serif" : "font-sans"
                  } ${
                    fontSize === "sm" ? "text-sm" : fontSize === "lg" ? "text-lg" : "text-base"
                  }`}
                  placeholder="Enter or refine the final synchronized narration for this panel..."
                />
                {segment.generation_status === "OUTDATED" && (
                  <div className="absolute top-3 right-3 bg-warn/90 border border-warn/80 text-warn text-[10px] font-semibold px-2 py-0.5 rounded-full flex items-center gap-1 shadow-sm">
                    <span className="w-1.5 h-1.5 rounded-full bg-warn animate-pulse" />
                    Script modified (Audio outdated)
                  </div>
                )}
              </div>

              {/* Panel Duration & Audio Sync Card */}
              <div className="p-3 rounded-lg bg-ink/90 border border-edge flex items-center justify-between text-xs">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-lg bg-accent/20 border border-accent/80 flex items-center justify-center text-info">
                    <Icons.Clock className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="font-semibold text-fg block">
                      Video Timeline & Audio Cadence Alignment
                    </span>
                    <span className="text-[11px] text-fg-dim">
                      Target Panel Time: <strong className="text-fg">~{targetPanelBudgetSec}s</strong> • Spoken Length: <strong className="text-info">~{estimatedDuration}s</strong> (Speed: {segment.delivery.speech_speed}x)
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleAutoFitSpeed}
                    className="px-2.5 py-1 rounded bg-accent/20 hover:bg-accent/20 text-info border border-accent/40 text-[11px] font-semibold flex items-center gap-1 shadow-sm"
                  >
                    <Icons.Zap className="w-3 h-3 text-info" />
                    <span>Fit to Panel Time</span>
                  </button>

                  {onHarmonizeSegment && (
                    <button
                      type="button"
                      onClick={() => onHarmonizeSegment(segment)}
                      className="px-2.5 py-1 rounded bg-flat hover:bg-glass-hi text-fg border border-edge text-[11px] font-semibold flex items-center gap-1"
                      title="Re-harmonize this panel script using LLM"
                    >
                      <Icons.Refresh className="w-3 h-3 text-info" />
                      <span>Re-Harmonize</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: PAGE STORY (5-10 LINES) */}
          {activeTab === "page" && (
            <div className="p-4 rounded-xl bg-navy/80 border border-warn/40 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-bold text-warn flex items-center gap-1.5">
                    <Icons.BookOpen className="w-4 h-4" />
                    <span>Page {segment.source_context.page_number} Story Script (5-10 Lines)</span>
                  </h4>
                  <p className="text-[11px] text-fg-dim">
                    Witty, entertaining human-style storytelling recapping the full page across all panels.
                  </p>
                </div>
                {resolvedPageScript && (
                  <span className="text-[10px] font-semibold text-warn bg-warn/80 border border-warn/80 px-2 py-0.5 rounded-full">
                    Tone: {resolvedPageScript.tone}
                  </span>
                )}
              </div>

              {/* Lines list */}
              <div className="space-y-2">
                {pageLines.length > 0 ? (
                  pageLines.map((line, lIdx) => {
                    const isMatchedBeat = lIdx === ((segment.sequence - 1) % pageLines.length);
                    return (
                      <div
                        key={lIdx}
                        className={`p-2.5 rounded-lg border text-xs flex items-start justify-between gap-3 transition-colors ${
                          isMatchedBeat
                            ? "bg-warn/40 border-warn text-fg ring-1 ring-warn/30"
                            : "bg-ink/70 border-edge text-fg-dim hover:border-edge"
                        }`}
                      >
                        <div className="flex items-start gap-2 flex-1">
                          <span className={`w-4 h-4 rounded text-[10px] font-mono font-bold flex items-center justify-center shrink-0 mt-0.5 ${
                            isMatchedBeat ? "bg-warn text-black" : "bg-flat text-fg-dim"
                          }`}>
                            {lIdx + 1}
                          </span>
                          <p className="leading-relaxed font-sans">{line}</p>
                        </div>

                        <button
                          type="button"
                          onClick={() => {
                            handleTextChange(line);
                            setActiveTab("final");
                          }}
                          className="shrink-0 text-[10px] px-2 py-1 rounded bg-warn/20 hover:bg-warn/20 text-warn font-semibold border border-warn/80"
                          title="Copy this witty line into the Final Synced Script"
                        >
                          Use in Final →
                        </button>
                      </div>
                    );
                  })
                ) : (
                  <div className="p-6 text-center text-xs text-fg-faint space-y-2">
                    <p>No 5-10 line page script generated yet for Page {segment.source_context.page_number}.</p>
                    <p className="text-[11px] text-fg-dim">
                      Click <strong>&ldquo;Generate 3-Tier Narration&rdquo;</strong> in the top toolbar to analyze the full page image with Vision LLM.
                    </p>
                  </div>
                )}
              </div>

              {/* Comedic & emotional observations */}
              {resolvedPageScript?.humor_and_emotional_notes && (
                <div className="p-2.5 rounded-lg bg-black/40 border border-edge/80 text-[11px] text-fg-dim">
                  <strong className="text-warn block mb-0.5">Storyteller & Humor Notes:</strong>
                  {resolvedPageScript.humor_and_emotional_notes}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: PANEL MICRO BEAT */}
          {activeTab === "panel" && (
            <div className="p-4 rounded-xl bg-navy/80 border border-ok/40 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-bold text-ok flex items-center gap-1.5">
                    <Icons.Eye className="w-4 h-4" />
                    <span>Panel #{segment.sequence} Micro Breakdown</span>
                  </h4>
                  <p className="text-[11px] text-fg-dim">
                    Focused micro observation of this cropped panel, speech bubble dialogue, and immediate action.
                  </p>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-ink/80 border border-edge space-y-2 text-xs">
                <div>
                  <span className="text-[10px] uppercase font-bold text-fg-faint block mb-0.5">
                    Panel Micro Narration Draft:
                  </span>
                  <p className="text-fg italic leading-relaxed">
                    {segment.panel_narration_text || segment.source_context.visual_description || "Micro beat pending vision analysis."}
                  </p>
                </div>

                <div className="pt-2 border-t border-edge/60 flex items-center justify-between">
                  <span className="text-[11px] text-fg-dim">
                    Dialogue: &ldquo;{segment.source_context.raw_ocr_dialogue || "None"}&rdquo;
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      if (segment.panel_narration_text) {
                        handleTextChange(segment.panel_narration_text);
                        setActiveTab("final");
                      }
                    }}
                    className="text-[10px] px-2.5 py-1 rounded bg-ok/20 hover:bg-ok/20 text-ok font-semibold border border-ok/40"
                  >
                    Use as Final Script →
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: COMPARE & HARMONIZE */}
          {activeTab === "compare" && (
            <div className="p-4 rounded-xl bg-navy/80 border border-accent/40 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-bold text-info flex items-center gap-1.5">
                    <Icons.Layout className="w-4 h-4" />
                    <span>Script Comparison & Harmonization Studio</span>
                  </h4>
                  <p className="text-[11px] text-fg-dim">
                    Compare the overarching 5-10 line Page Story with the Panel Micro Beat, then merge them into the Final Synced Script.
                  </p>
                </div>
                {onHarmonizeSegment && (
                  <button
                    type="button"
                    onClick={() => onHarmonizeSegment(segment)}
                    className="px-2.5 py-1 rounded bg-accent/20 hover:bg-accent/20 text-info border border-accent/40 text-[11px] font-semibold flex items-center gap-1 shadow-sm"
                  >
                    <Icons.Sparkles className="w-3 h-3 text-info" />
                    <span>Re-Harmonize with LLM</span>
                  </button>
                )}
              </div>

              {/* Side-by-side comparison */}
              <div className="grid grid-cols-2 gap-3 text-xs">
                {/* Left: Page Story Context */}
                <div className="p-3 rounded-lg bg-ink/90 border border-warn/30 space-y-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-warn block">
                    1. Overarching Page Story (5-10 Lines)
                  </span>
                  <p className="text-fg-dim leading-relaxed max-h-[140px] overflow-y-auto font-sans pr-1">
                    {resolvedPageScript?.full_script || segment.page_narration_text || "Page narration script not generated yet."}
                  </p>
                </div>

                {/* Right: Panel Micro Action */}
                <div className="p-3 rounded-lg bg-ink/90 border border-ok/30 space-y-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-ok block">
                    2. Panel #{segment.sequence} Micro Evidence
                  </span>
                  <div className="space-y-1 text-fg-dim text-xs">
                    <p><strong>Action:</strong> {segment.source_context.visual_description || "Visual framing"}</p>
                    {segment.source_context.raw_ocr_dialogue && (
                      <p><strong>Spoken:</strong> &ldquo;{segment.source_context.raw_ocr_dialogue}&rdquo;</p>
                    )}
                    <p className="italic text-fg-dim text-[11px]">
                      {segment.panel_narration_text || "Panel micro beat"}
                    </p>
                  </div>
                </div>
              </div>

              {/* Bottom: Final Harmonized Result */}
              <div className="p-3 rounded-lg bg-accent/30 border border-accent/60 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-info">
                    3. Final Harmonized & Synced Script (Carrying Page Humor + Panel Timing)
                  </span>
                  <span className="text-[10px] text-fg-dim font-mono">
                    ~{estimatedDuration}s • {wordCount} words
                  </span>
                </div>

                <p className="p-2.5 rounded bg-ink/90 border border-edge font-serif text-sm text-fg leading-relaxed italic">
                  &ldquo;{segment.narration_text}&rdquo;
                </p>

                {segment.synthesis_notes && (
                  <p className="text-[11px] text-info/90">
                    <strong>Harmonization Rationale:</strong> {segment.synthesis_notes}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Story Continuity Notes & Character Context */}
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between text-xs font-bold text-fg-dim">
            <span className="uppercase tracking-wider">Story Continuity & Performance Notes</span>
            <span className="text-[10px] font-normal text-fg-faint">
              Preserved across narration lifecycle
            </span>
          </div>

          <textarea
            value={segment.continuity_notes || ""}
            onChange={(e) => onUpdateSegment({ continuity_notes: e.target.value })}
            rows={2}
            className="w-full p-3 rounded-lg bg-navy/60 border border-edge text-xs text-fg-dim placeholder-fg-faint focus:outline-none focus:border-accent"
            placeholder="Add storytelling notes, character motivations, or continuity reminders..."
          />
        </div>

        {/* Action Buttons: Split at cursor, Duplicate, Add to Timeline, Delete */}
        <div className="flex items-center justify-between pt-3 border-t border-edge/80 text-xs">
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onDuplicateSegment(segment.id)}
              className="text-xs h-8 border border-edge"
            >
              <Icons.Copy className="w-3.5 h-3.5 mr-1 text-fg-dim" />
              Duplicate Segment
            </Button>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                const halfway = Math.floor(segment.narration_text.length / 2);
                onSplitSegment(segment.id, halfway);
              }}
              className="text-xs h-8 border border-edge"
              title="Split this segment into two consecutive story segments"
            >
              <Icons.Scissors className="w-3.5 h-3.5 mr-1 text-fg-dim" />
              Split Segment
            </Button>

            {onAddToTimeline && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onAddToTimeline(segment)}
                className="text-xs h-8 border border-ok/80 bg-ok/60 hover:bg-ok/20 text-ok font-semibold flex items-center gap-1.5"
                title="Add this narration segment directly to the video timeline"
              >
                <Icons.Plus className="w-3.5 h-3.5 text-ok" />
                <span>Add to Timeline</span>
              </Button>
            )}
          </div>

          <button
            type="button"
            onClick={() => {
              if (confirm(`Delete Segment #${segment.sequence}? This action can be undone with Ctrl+Z.`)) {
                onDeleteSegment(segment.id);
              }
            }}
            className="flex items-center gap-1 text-xs text-fg-dim hover:text-bad px-2 py-1.5 rounded hover:bg-navy transition-colors"
          >
            <Icons.Trash className="w-3.5 h-3.5" />
            <span>Delete</span>
          </button>
        </div>
      </div>

      {/* Lightbox Modal */}
      {isLightboxOpen && activeImgUrl && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-6 cursor-zoom-out"
          onClick={() => setIsLightboxOpen(false)}
        >
          <div className="max-w-4xl max-h-[90vh] relative">
            <img
              src={activeImgUrl}
              alt="Full Resolution Preview"
              className="max-w-full max-h-[85vh] object-contain rounded-xl shadow-2xl border border-edge"
            />
            <button
              type="button"
              onClick={() => setIsLightboxOpen(false)}
              className="absolute top-2 right-2 p-1.5 rounded-full bg-navy/90 text-white hover:bg-flat"
            >
              <Icons.X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
