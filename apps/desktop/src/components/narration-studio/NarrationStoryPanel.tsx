import React, { useMemo, useState } from "react";
import { Icons, Badge } from "@panelflow/ui";
import { api } from "@panelflow/api-client";
import type {
  NarrationChapter,
  NarrationSegment,
  NarrationFilterState,
  ReviewStatus,
  SpeakerType,
} from "./NarrationStudio.types";

interface NarrationStoryPanelProps {
  chapter: NarrationChapter;
  selectedSegmentId: string | null;
  filter: NarrationFilterState;
  onSelectSegment: (id: string) => void;
  onFilterChange: (updates: Partial<NarrationFilterState>) => void;
  onReorderSegment: (segmentId: string, direction: "up" | "down") => void;
  onAddSegment: (speakerType: SpeakerType) => void;
  onDuplicateSegment: (segmentId: string) => void;
  onDeleteSegment: (segmentId: string) => void;
  onOpenPageScript?: (pageId: string, pageNumber: number) => void;
  className?: string;
}

export const NarrationStoryPanel: React.FC<NarrationStoryPanelProps> = ({
  chapter,
  selectedSegmentId,
  filter,
  onSelectSegment,
  onFilterChange,
  onReorderSegment,
  onAddSegment,
  onDuplicateSegment,
  onDeleteSegment,
  onOpenPageScript,
  className = "",
}) => {
  // Page collapse toggles: track collapsed page numbers
  const [collapsedPages, setCollapsedPages] = useState<Record<number, boolean>>({});

  const togglePageCollapse = (pageNum: number) => {
    setCollapsedPages((prev) => ({ ...prev, [pageNum]: !prev[pageNum] }));
  };

  // Compute chapter-level metrics
  const totalWords = useMemo(() => {
    return chapter.segments.reduce((acc, s) => {
      const words = s.narration_text.trim().split(/\s+/).filter(Boolean).length;
      return acc + words;
    }, 0);
  }, [chapter.segments]);

  const totalEstDuration = useMemo(() => {
    return chapter.segments.reduce((acc, s) => acc + (s.estimated_duration_sec || 0), 0);
  }, [chapter.segments]);

  const approvedCount = useMemo(() => {
    return chapter.segments.filter((s) => s.review_status === "APPROVED").length;
  }, [chapter.segments]);

  // Filtered segments
  const filteredSegments = useMemo(() => {
    return chapter.segments.filter((seg) => {
      // Search filter
      if (filter.search_query.trim()) {
        const query = filter.search_query.toLowerCase();
        const matchesText = seg.narration_text.toLowerCase().includes(query);
        const matchesSpeaker = seg.speaker_name.toLowerCase().includes(query);
        const matchesOcr = seg.source_context.raw_ocr_dialogue.toLowerCase().includes(query);
        const matchesVisual = seg.source_context.visual_description.toLowerCase().includes(query);
        if (!matchesText && !matchesSpeaker && !matchesOcr && !matchesVisual) {
          return false;
        }
      }

      // Character filter
      if (filter.selected_character_id && seg.speaker_id !== filter.selected_character_id) {
        return false;
      }

      // Review status filter
      if (filter.selected_status !== "ALL" && seg.review_status !== filter.selected_status) {
        return false;
      }

      // Speaker type filter
      if (filter.selected_speaker_type !== "ALL" && seg.speaker_type !== filter.selected_speaker_type) {
        return false;
      }

      return true;
    });
  }, [chapter.segments, filter]);

  // Group filtered segments by Page
  const groupedByPage = useMemo(() => {
    const groups: Record<number, { pageNumber: number; pageId: string; segments: NarrationSegment[] }> = {};
    for (const seg of filteredSegments) {
      const pageNum = seg.source_context.page_number || 1;
      const pageId = seg.source_context.page_id || `page_${pageNum}`;
      if (!groups[pageNum]) {
        groups[pageNum] = { pageNumber: pageNum, pageId, segments: [] };
      }
      groups[pageNum].segments.push(seg);
    }
    return Object.values(groups).sort((a, b) => a.pageNumber - b.pageNumber);
  }, [filteredSegments]);

  // Helper to get status badge variant
  const getStatusBadge = (status: ReviewStatus, genStatus: string) => {
    if (genStatus === "OUTDATED") {
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-400 bg-amber-950/70 border border-amber-800/80 px-2 py-0.5 rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          Outdated
        </span>
      );
    }
    switch (status) {
      case "APPROVED":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-400 bg-emerald-950/70 border border-emerald-800/80 px-2 py-0.5 rounded-full">
            <Icons.Check className="w-2.5 h-2.5 text-emerald-400" />
            Approved
          </span>
        );
      case "NEEDS_REVIEW":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-400 bg-amber-950/70 border border-amber-800/80 px-2 py-0.5 rounded-full">
            <Icons.AlertTriangle className="w-2.5 h-2.5 text-amber-400" />
            Needs Review
          </span>
        );
      case "DRAFT":
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-zinc-400 bg-zinc-800/80 border border-zinc-700/80 px-2 py-0.5 rounded-full">
            <Icons.Clock className="w-2.5 h-2.5 text-zinc-400" />
            Draft
          </span>
        );
    }
  };

  return (
    <aside
      className={`flex flex-col bg-zinc-950 border-r border-zinc-800/90 h-full select-none overflow-hidden ${className}`}
      aria-label="Story and Source Context"
    >
      {/* Top Section: Chapter Title & Storytelling Statistics */}
      <div className="p-3.5 border-b border-zinc-800/80 bg-zinc-900/40 shrink-0 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 bg-indigo-950/80 border border-indigo-800/60 px-2 py-0.5 rounded">
              Chapter {chapter.chapter_number}
            </span>
            <span className="text-xs font-semibold text-zinc-300 truncate max-w-[170px]" title={chapter.chapter_title}>
              {chapter.chapter_title}
            </span>
          </div>
          <span className="text-[11px] font-mono text-zinc-400 font-semibold">
            {approvedCount}/{chapter.segments.length} Approved
          </span>
        </div>

        {/* Storytelling Metric Tiles */}
        <div className="grid grid-cols-3 gap-1.5 text-center text-xs">
          <div className="p-1.5 rounded-lg bg-zinc-950 border border-zinc-800/80">
            <span className="text-[9px] uppercase tracking-wider text-zinc-500 font-bold block">
              Pages
            </span>
            <span className="font-mono font-bold text-zinc-200">
              {groupedByPage.length}
            </span>
          </div>

          <div className="p-1.5 rounded-lg bg-zinc-950 border border-zinc-800/80">
            <span className="text-[9px] uppercase tracking-wider text-zinc-500 font-bold block">
              Panels
            </span>
            <span className="font-mono font-bold text-zinc-200">
              {chapter.segments.length}
            </span>
          </div>

          <div className="p-1.5 rounded-lg bg-zinc-950 border border-zinc-800/80">
            <span className="text-[9px] uppercase tracking-wider text-zinc-500 font-bold block">
              Est. Audio
            </span>
            <span className="font-mono font-bold text-indigo-400">
              {Math.round(totalEstDuration)}s
            </span>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-2.5 border-b border-zinc-800/80 bg-zinc-900/20 shrink-0 space-y-2">
        {/* Search Input */}
        <div className="relative">
          <Icons.Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
          <input
            type="text"
            value={filter.search_query}
            onChange={(e) => onFilterChange({ search_query: e.target.value })}
            placeholder="Search dialogue, OCR or notes..."
            className="w-full pl-8 pr-7 py-1 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 font-sans"
          />
          {filter.search_query && (
            <button
              type="button"
              onClick={() => onFilterChange({ search_query: "" })}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
            >
              <Icons.X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Status Filter Tabs */}
        <div className="flex items-center bg-zinc-950 p-0.5 rounded-lg border border-zinc-800/80 text-[10px] font-medium text-zinc-400">
          {(["ALL", "DRAFT", "NEEDS_REVIEW", "APPROVED"] as const).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => onFilterChange({ selected_status: st })}
              className={`flex-1 py-1 rounded transition-colors text-center ${
                filter.selected_status === st
                  ? "bg-indigo-600 text-white font-bold shadow-sm"
                  : "hover:text-zinc-200"
              }`}
            >
              {st === "ALL"
                ? "All"
                : st === "NEEDS_REVIEW"
                ? "Review"
                : st === "DRAFT"
                ? "Draft"
                : "Approved"}
            </button>
          ))}
        </div>
      </div>

      {/* Grouped Page-by-Page Story Segments List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-3 focus:outline-none" tabIndex={0}>
        {groupedByPage.length === 0 ? (
          <div className="p-8 text-center text-zinc-500 text-xs space-y-2">
            <div className="w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400 mx-auto mb-2 shadow-inner">
              <Icons.BookOpen className="w-5 h-5" />
            </div>
            <p className="font-semibold text-zinc-400">No story segments found</p>
            <p className="text-[11px]">Try adjusting your search query or status filter.</p>
          </div>
        ) : (
          groupedByPage.map((pageGroup) => {
            const isCollapsed = !!collapsedPages[pageGroup.pageNumber];
            const pageScript = chapter.page_scripts?.[pageGroup.pageId] || chapter.page_scripts?.[String(pageGroup.pageNumber)];
            const hasPageStory = !!(pageScript && pageScript.lines && pageScript.lines.length >= 3);
            const pageDuration = pageGroup.segments.reduce((acc, s) => acc + (s.estimated_duration_sec || 0), 0);

            return (
              <div key={pageGroup.pageNumber} className="rounded-xl border border-zinc-800/80 bg-zinc-950/60 overflow-hidden shadow-sm">
                {/* Page Group Header */}
                <div
                  className="p-2.5 bg-zinc-900/60 border-b border-zinc-800/60 flex items-center justify-between cursor-pointer hover:bg-zinc-900 transition-colors"
                  onClick={() => togglePageCollapse(pageGroup.pageNumber)}
                >
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="text-zinc-400 hover:text-zinc-200"
                      title={isCollapsed ? "Expand page" : "Collapse page"}
                    >
                      {isCollapsed ? (
                        <Icons.ArrowRight className="w-3.5 h-3.5" />
                      ) : (
                        <Icons.ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <span className="text-xs font-bold text-zinc-100">
                      Page {pageGroup.pageNumber}
                    </span>
                    <span className="text-[10px] text-zinc-500 font-mono">
                      ({pageGroup.segments.length} {pageGroup.segments.length === 1 ? "panel" : "panels"})
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {hasPageStory ? (
                      <span className="text-[9px] font-semibold text-amber-300 bg-amber-950/80 border border-amber-800/80 px-1.5 py-0.5 rounded-full flex items-center gap-1" title="5-10 line witty human script generated">
                        <Icons.Sparkles className="w-2.5 h-2.5 text-amber-400" />
                        <span>Story Ready</span>
                      </span>
                    ) : (
                      <span className="text-[9px] text-zinc-500 italic">
                        No Page Story
                      </span>
                    )}

                    <span className="text-[10px] text-zinc-400 font-mono">
                      ~{Math.round(pageDuration)}s
                    </span>
                  </div>
                </div>

                {/* Page Panels List */}
                {!isCollapsed && (
                  <div className="p-1.5 space-y-1.5">
                    {pageGroup.segments.map((seg, sIdx) => {
                      const isSelected = seg.id === selectedSegmentId;
                      const character = chapter.characters.find((c) => c.id === seg.speaker_id);
                      const accentColor = character?.color_accent || "#6366f1";
                      const primaryPanelId = seg.source_context.panel_ids?.[0];
                      const primaryPageId = seg.source_context.page_id;
                      const rawUrl = seg.source_context.panel_preview_url || seg.source_context.image_url;

                      let resolvedUrl = "";
                      if (chapter.project_id && primaryPanelId) {
                        resolvedUrl = api.getPanelImageUrl(chapter.project_id, primaryPanelId);
                      } else if (rawUrl) {
                        resolvedUrl = rawUrl.startsWith("http") || rawUrl.startsWith("data:")
                          ? rawUrl
                          : `http://127.0.0.1:8765${rawUrl.startsWith("/") ? "" : "/"}${rawUrl}`;
                      } else if (chapter.project_id && primaryPageId) {
                        resolvedUrl = api.getPageImageUrl(chapter.project_id, primaryPageId);
                      }

                      return (
                        <div
                          key={seg.id}
                          role="button"
                          tabIndex={0}
                          onClick={() => onSelectSegment(seg.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              onSelectSegment(seg.id);
                            }
                          }}
                          className={`rounded-lg border p-2 transition-all text-left cursor-pointer ${
                            isSelected
                              ? "bg-zinc-900 border-indigo-500 ring-1 ring-indigo-500/40 shadow-md shadow-indigo-950/40"
                              : "bg-zinc-900/40 border-zinc-800/70 hover:border-zinc-700 hover:bg-zinc-900"
                          }`}
                        >
                          {/* Header row */}
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <div className="flex items-center gap-1.5">
                              <span
                                className={`w-4 h-4 rounded flex items-center justify-center font-mono text-[9px] font-bold ${
                                  isSelected ? "bg-indigo-600 text-white" : "bg-zinc-800 text-zinc-300"
                                }`}
                              >
                                {seg.sequence}
                              </span>

                              <div className="flex items-center gap-1 bg-zinc-950 px-1.5 py-0.5 rounded border border-zinc-800">
                                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: accentColor }} />
                                <span className="text-[10px] font-semibold text-zinc-200 truncate max-w-[90px]">
                                  {seg.speaker_name}
                                </span>
                              </div>

                              <span className="text-[9px] text-zinc-500 font-mono">
                                Panel #{sIdx + 1}
                              </span>
                            </div>

                            <div>{getStatusBadge(seg.review_status, seg.generation_status)}</div>
                          </div>

                          {/* Thumbnail & Dialogue Preview */}
                          <div className="flex items-center gap-2 mb-1.5">
                            <div className="w-14 h-10 rounded overflow-hidden shrink-0 bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                              {resolvedUrl ? (
                                <img
                                  src={resolvedUrl}
                                  alt="Panel preview"
                                  className="w-full h-full object-cover"
                                  loading="lazy"
                                  onError={(e) => {
                                    const target = e.target as HTMLImageElement;
                                    if (chapter.project_id && primaryPageId && !target.src.includes("/pages/")) {
                                      target.src = api.getPageImageUrl(chapter.project_id, primaryPageId);
                                    } else {
                                      target.style.display = "none";
                                    }
                                  }}
                                />
                              ) : (
                                <Icons.Image className="w-3.5 h-3.5 text-zinc-600" />
                              )}
                            </div>

                            <p className="text-[11px] text-zinc-300 line-clamp-2 leading-relaxed flex-1">
                              {seg.narration_text}
                            </p>
                          </div>

                          {/* Footer: Emotion, words & duration */}
                          <div className="flex items-center justify-between text-[9px] text-zinc-500 border-t border-zinc-800/40 pt-1">
                            <div className="flex items-center gap-1.5">
                              <span className="text-zinc-400 font-medium">
                                {seg.delivery.emotion}
                              </span>
                              <span>•</span>
                              <span className="font-mono text-indigo-400">
                                ~{seg.estimated_duration_sec}s ({seg.narration_text.split(" ").filter(Boolean).length}w)
                              </span>
                            </div>

                            {seg.audio_asset_uri && (
                              <span className="text-emerald-400 flex items-center gap-0.5 font-semibold">
                                <Icons.Volume className="w-2.5 h-2.5" />
                                Voice
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Bottom Bar: Add Segment */}
      <div className="p-2 border-t border-zinc-800/80 bg-zinc-900/30 flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          onClick={() => onAddSegment("NARRATOR")}
          className="flex-1 py-1.5 rounded-lg bg-indigo-600/90 hover:bg-indigo-600 text-white font-semibold text-xs flex items-center justify-center gap-1.5 shadow-sm transition-colors"
        >
          <Icons.Plus className="w-3.5 h-3.5" />
          <span>+ Add Narration</span>
        </button>

        <button
          type="button"
          onClick={() => onAddSegment("CHARACTER")}
          className="flex-1 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-semibold text-xs flex items-center justify-center gap-1.5 border border-zinc-700 transition-colors"
        >
          <Icons.MessageSquare className="w-3.5 h-3.5 text-emerald-400" />
          <span>+ Add Dialogue</span>
        </button>
      </div>
    </aside>
  );
};
