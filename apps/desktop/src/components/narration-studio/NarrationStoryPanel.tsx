import React, { useMemo } from "react";
import { Icons, Badge } from "@panelflow/ui";
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
  className = "",
}) => {
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
      <div className="p-3.5 border-b border-zinc-800/80 bg-zinc-900/40 shrink-0">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 bg-indigo-950/80 border border-indigo-800/60 px-2 py-0.5 rounded">
              Chapter {chapter.chapter_number}
            </span>
            <span className="text-xs font-semibold text-zinc-300 truncate max-w-[170px]" title={chapter.chapter_title}>
              {chapter.chapter_title}
            </span>
          </div>
          <span className="text-[11px] font-mono text-zinc-400 font-semibold">
            {approvedCount}/{chapter.segments.length}
          </span>
        </div>

        {/* Narrative Metrics Bar */}
        <div className="grid grid-cols-3 gap-1.5 mt-2 bg-zinc-950/70 p-2 rounded-lg border border-zinc-800/60 text-center">
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium">Segments</span>
            <span className="text-xs font-bold text-zinc-200 font-mono">{chapter.segments.length}</span>
          </div>
          <div className="flex flex-col border-x border-zinc-800/80">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium">Words</span>
            <span className="text-xs font-bold text-zinc-200 font-mono">{totalWords}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium">Est. Audio</span>
            <span className="text-xs font-bold text-indigo-400 font-mono">
              {Math.floor(totalEstDuration)}s
            </span>
          </div>
        </div>

        {/* Storytelling Progress Bar */}
        <div className="mt-2.5 space-y-1">
          <div className="flex justify-between text-[10px] font-medium text-zinc-400">
            <span>Approval Progress</span>
            <span>{Math.round((approvedCount / (chapter.segments.length || 1)) * 100)}%</span>
          </div>
          <div className="w-full bg-zinc-800/80 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-emerald-500 h-1.5 rounded-full transition-all duration-300 ease-out"
              style={{
                width: `${(approvedCount / (chapter.segments.length || 1)) * 100}%`,
              }}
            />
          </div>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="p-2.5 border-b border-zinc-800/80 bg-zinc-900/20 space-y-2 shrink-0">
        {/* Search input */}
        <div className="relative">
          <input
            type="text"
            placeholder="Search dialogue, OCR or notes..."
            value={filter.search_query}
            onChange={(e) => onFilterChange({ search_query: e.target.value })}
            className="w-full pl-7 pr-7 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500/80 transition-colors"
          />
          <span className="absolute left-2.5 top-2 text-zinc-500 text-xs">🔍</span>
          {filter.search_query && (
            <button
              type="button"
              onClick={() => onFilterChange({ search_query: "" })}
              className="absolute right-2 top-2 text-zinc-500 hover:text-zinc-300 text-xs"
              title="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        {/* Character / Speaker Filter Dropdown */}
        <div className="flex items-center gap-1.5">
          <select
            value={filter.selected_character_id || ""}
            onChange={(e) =>
              onFilterChange({
                selected_character_id: e.target.value ? e.target.value : null,
              })
            }
            className="flex-1 bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-300 rounded px-2 py-1 focus:outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="">All Characters ({chapter.segments.length})</option>
            {chapter.characters.map((char) => {
              const count = chapter.segments.filter((s) => s.speaker_id === char.id).length;
              return (
                <option key={char.id} value={char.id}>
                  {char.name} ({count})
                </option>
              );
            })}
          </select>

          {/* Speaker Type Toggle: All / Narrator / Dialogue */}
          <select
            value={filter.selected_speaker_type}
            onChange={(e) =>
              onFilterChange({
                selected_speaker_type: e.target.value as SpeakerType | "ALL",
              })
            }
            className="w-24 bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-300 rounded px-1.5 py-1 focus:outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="ALL">All Roles</option>
            <option value="NARRATOR">Narrator</option>
            <option value="CHARACTER">Dialogue</option>
          </select>
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

      {/* Ordered Story Segments List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2 focus:outline-none" tabIndex={0}>
        {filteredSegments.length === 0 ? (
          <div className="p-8 text-center text-zinc-500 text-xs space-y-2">
            <span className="text-2xl block">📖</span>
            <p className="font-semibold text-zinc-400">No story segments found</p>
            <p className="text-[11px]">Try adjusting your search query or status filter.</p>
          </div>
        ) : (
          filteredSegments.map((seg, idx) => {
            const isSelected = seg.id === selectedSegmentId;
            const character = chapter.characters.find((c) => c.id === seg.speaker_id);
            const accentColor = character?.color_accent || "#6366f1";

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
                className={`relative group rounded-xl border p-2.5 transition-all text-left cursor-pointer ${
                  isSelected
                    ? "bg-zinc-900 border-indigo-500 ring-1 ring-indigo-500/40 shadow-lg shadow-indigo-950/50"
                    : "bg-zinc-900/60 border-zinc-800/80 hover:border-zinc-700 hover:bg-zinc-900"
                }`}
              >
                {/* Header row: Sequence #, Speaker badge, and Review status */}
                <div className="flex items-center justify-between gap-1.5 mb-1.5">
                  <div className="flex items-center gap-1.5">
                    {/* Sequence Badge */}
                    <span
                      className={`w-5 h-5 rounded-md flex items-center justify-center font-mono text-[10px] font-bold ${
                        isSelected
                          ? "bg-indigo-600 text-white"
                          : "bg-zinc-800 text-zinc-300 group-hover:bg-zinc-700"
                      }`}
                    >
                      {seg.sequence}
                    </span>

                    {/* Speaker Chip */}
                    <div className="flex items-center gap-1 bg-zinc-950 px-1.5 py-0.5 rounded border border-zinc-800">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: accentColor }}
                      />
                      <span className="text-[11px] font-semibold text-zinc-200 truncate max-w-[110px]">
                        {seg.speaker_name}
                      </span>
                    </div>

                    {/* Speaker Type tag */}
                    {seg.speaker_type === "NARRATOR" ? (
                      <span className="text-[9px] uppercase tracking-wider font-semibold text-indigo-400 bg-indigo-950/60 px-1 py-0.5 rounded">
                        Voice
                      </span>
                    ) : (
                      <span className="text-[9px] uppercase tracking-wider font-semibold text-emerald-400 bg-emerald-950/60 px-1 py-0.5 rounded">
                        Dialog
                      </span>
                    )}
                  </div>

                  {/* Status Badge */}
                  <div>{getStatusBadge(seg.review_status, seg.generation_status)}</div>
                </div>

                {/* Manga Source Context Preview Box */}
                <div className="flex items-center gap-2 mb-2 p-1.5 rounded-lg bg-zinc-950/80 border border-zinc-800/60">
                  {/* Thumbnail / Manga Panel Preview with real image & SVG fallback */}
                  <div className="w-14 h-9 rounded overflow-hidden shrink-0 bg-zinc-900 border border-zinc-800 flex items-center justify-center relative">
                    {(() => {
                      const imgUrl = seg.source_context.panel_preview_url || seg.source_context.image_url;
                      if (imgUrl) {
                        const resolvedUrl = imgUrl.startsWith("http") || imgUrl.startsWith("data:")
                          ? imgUrl
                          : `http://127.0.0.1:8765${imgUrl.startsWith("/") ? "" : "/"}${imgUrl}`;
                        return (
                          <img
                            src={resolvedUrl}
                            alt={seg.source_context.panel_labels?.[0] || "Panel"}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = "none";
                            }}
                          />
                        );
                      }
                      if (seg.source_context.svg_thumbnail) {
                        return (
                          <div
                            className="w-full h-full object-cover"
                            dangerouslySetInnerHTML={{ __html: seg.source_context.svg_thumbnail }}
                          />
                        );
                      }
                      return (
                        <div className="text-[10px] font-mono text-zinc-500 font-bold flex flex-col items-center">
                          <span>P#{seg.source_context.page_number}</span>
                        </div>
                      );
                    })()}
                  </div>

                  {/* Panel References Label */}
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] font-semibold text-zinc-400 flex items-center gap-1 truncate">
                      <Icons.Layers className="w-3 h-3 text-indigo-400 shrink-0" />
                      <span className="truncate">
                        {seg.source_context.panel_labels?.[0] || `Page ${seg.source_context.page_number}`}
                      </span>
                    </div>
                    {seg.source_context.raw_ocr_dialogue && (
                      <div className="text-[10px] text-zinc-500 italic truncate" title={seg.source_context.raw_ocr_dialogue}>
                        OCR: &ldquo;{seg.source_context.raw_ocr_dialogue}&rdquo;
                      </div>
                    )}
                  </div>
                </div>

                {/* Narration Script Text Excerpt */}
                <p className="text-xs text-zinc-200 line-clamp-2 leading-relaxed mb-2">
                  {seg.narration_text}
                </p>

                {/* Footer Metadata Chips */}
                <div className="flex items-center justify-between text-[10px] text-zinc-400 border-t border-zinc-800/60 pt-1.5">
                  <div className="flex items-center gap-1.5">
                    {/* Emotion Tag */}
                    <span className="px-1.5 py-0.5 rounded bg-zinc-800/80 text-zinc-300 font-medium">
                      {seg.delivery.emotion}
                    </span>
                    <span className="font-mono text-zinc-500">
                      ~{seg.estimated_duration_sec}s
                    </span>
                  </div>

                  {/* Segment Management Actions: Reorder & Duplicate */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onReorderSegment(seg.id, "up");
                      }}
                      disabled={idx === 0}
                      className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 disabled:opacity-20"
                      title="Move Segment Up in Story Order"
                    >
                      ▲
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onReorderSegment(seg.id, "down");
                      }}
                      disabled={idx === filteredSegments.length - 1}
                      className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 disabled:opacity-20"
                      title="Move Segment Down in Story Order"
                    >
                      ▼
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDuplicateSegment(seg.id);
                      }}
                      className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800"
                      title="Duplicate Segment"
                    >
                      <Icons.Copy className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Delete Segment #${seg.sequence}?`)) {
                          onDeleteSegment(seg.id);
                        }
                      }}
                      className="p-1 rounded text-zinc-400 hover:text-rose-400 hover:bg-zinc-800"
                      title="Delete Segment"
                    >
                      <Icons.Trash className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Bottom Sticky Action Area: Add New Segment */}
      <div className="p-3 border-t border-zinc-800/80 bg-zinc-900/60 shrink-0 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onAddSegment("NARRATOR")}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-indigo-600/90 hover:bg-indigo-600 text-white font-semibold text-xs transition-colors shadow-md shadow-indigo-950"
        >
          <Icons.Plus className="w-3.5 h-3.5" />
          <span>Add Narration</span>
        </button>
        <button
          type="button"
          onClick={() => onAddSegment("CHARACTER")}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-semibold text-xs border border-zinc-700 transition-colors"
        >
          <Icons.Plus className="w-3.5 h-3.5" />
          <span>Add Dialogue</span>
        </button>
      </div>
    </aside>
  );
};
