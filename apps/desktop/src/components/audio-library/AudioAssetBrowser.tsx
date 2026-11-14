import React, { useState } from "react";
import type {
  AudioAsset,
  AudioFilterState,
  AudioPreviewState,
  AudioSortOption,
} from "./AudioLibrary.types.ts";

interface AudioAssetBrowserProps {
  assets: AudioAsset[];
  filter: AudioFilterState;
  onUpdateFilter: (updates: Partial<AudioFilterState>) => void;
  selectedAssetId: string | null;
  onSelectAsset: (asset: AudioAsset) => void;
  onToggleFavorite: (assetId: string) => void;
  previewState: AudioPreviewState;
  onTogglePlay: (asset: AudioAsset) => void;
  onQuickSendToTimeline?: (asset: AudioAsset) => void;
}

function formatDuration(sec: number): string {
  if (isNaN(sec) || sec < 0) return "0:00";
  const mins = Math.floor(sec / 60);
  const remainingSecs = Math.floor(sec % 60);
  return `${mins}:${remainingSecs.toString().padStart(2, "0")}`;
}

export const AudioAssetBrowser: React.FC<AudioAssetBrowserProps> = ({
  assets,
  filter,
  onUpdateFilter,
  selectedAssetId,
  onSelectAsset,
  onToggleFavorite,
  previewState,
  onTogglePlay,
  onQuickSendToTimeline,
}) => {
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  // Filter logic
  const filteredAssets = assets.filter((asset) => {
    // Type filter
    if (filter.selected_type !== "all" && asset.type !== filter.selected_type) {
      return false;
    }

    // Category filter
    if (filter.selected_category === "favorites") {
      if (!asset.is_favorite) return false;
    } else if (filter.selected_category === "background_music") {
      if (asset.type !== "music") return false;
    } else if (filter.selected_category) {
      if (asset.category !== filter.selected_category) return false;
    }

    // Loopable filter
    if (filter.only_loopable && !asset.loopable) {
      return false;
    }

    // Search query filter
    if (filter.search_query.trim()) {
      const q = filter.search_query.toLowerCase().trim();
      const matchName = asset.name.toLowerCase().includes(q);
      const matchDesc = asset.description.toLowerCase().includes(q);
      const matchTags = asset.tags.some((t) => t.toLowerCase().includes(q));
      const matchAuthor = asset.license.author_or_source.toLowerCase().includes(q);
      const matchKey = asset.key?.toLowerCase().includes(q) ?? false;
      if (!matchName && !matchDesc && !matchTags && !matchAuthor && !matchKey) {
        return false;
      }
    }

    return true;
  });

  // Sort logic
  const sortedAssets = [...filteredAssets].sort((a, b) => {
    switch (filter.sort_by) {
      case "name_asc":
        return a.name.localeCompare(b.name);
      case "name_desc":
        return b.name.localeCompare(a.name);
      case "duration_asc":
        return a.duration_sec - b.duration_sec;
      case "duration_desc":
        return b.duration_sec - a.duration_sec;
      case "bpm_asc":
        return (a.bpm ?? 0) - (b.bpm ?? 0);
      case "recent":
      default:
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    }
  });

  return (
    <div className="flex-1 flex flex-col h-full bg-navy min-w-0 overflow-hidden">
      {/* Top Search & Filter Bar */}
      <div className="p-3.5 border-b border-edge bg-ink/70 flex flex-wrap items-center justify-between gap-3 shrink-0">
        {/* Search Input */}
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-fg-faint text-xs">
            🔍
          </span>
          <input
            type="text"
            value={filter.search_query}
            onChange={(e) => onUpdateFilter({ search_query: e.target.value })}
            placeholder="Search audio by title, tag, tempo, key, author..."
            className="w-full pl-8 pr-8 py-1.5 bg-navy border border-edge rounded-lg text-xs text-fg placeholder-fg-faint focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
          />
          {filter.search_query && (
            <button
              type="button"
              onClick={() => onUpdateFilter({ search_query: "" })}
              className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-fg-faint hover:text-fg-dim text-xs"
              title="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        {/* Right Controls: Sort & View Toggle */}
        <div className="flex items-center gap-2">
          {/* Loopable Filter Toggle */}
          <button
            type="button"
            onClick={() => onUpdateFilter({ only_loopable: !filter.only_loopable })}
            className={`px-2.5 py-1.5 rounded-lg border text-xs font-medium flex items-center gap-1.5 transition-colors ${
              filter.only_loopable
                ? "bg-warn/20 border-warn/50 text-warn"
                : "bg-navy border-edge text-fg-dim hover:text-fg"
            }`}
            title="Filter loopable audio assets"
          >
            <span>🔁</span>
            <span className="hidden sm:inline">Loopable</span>
          </button>

          {/* Sort Dropdown */}
          <div className="flex items-center gap-1.5 bg-navy border border-edge rounded-lg px-2.5 py-1">
            <span className="text-[10px] text-fg-faint font-medium uppercase">Sort:</span>
            <select
              value={filter.sort_by}
              onChange={(e) => onUpdateFilter({ sort_by: e.target.value as AudioSortOption })}
              className="bg-transparent text-xs text-fg focus:outline-none cursor-pointer"
            >
              <option value="recent">Recently Added</option>
              <option value="name_asc">Name (A → Z)</option>
              <option value="name_desc">Name (Z → A)</option>
              <option value="duration_asc">Duration (Short → Long)</option>
              <option value="duration_desc">Duration (Long → Short)</option>
              <option value="bpm_asc">BPM (Slow → Fast)</option>
            </select>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center bg-navy border border-edge rounded-lg p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`p-1.5 rounded text-xs transition-colors ${
                viewMode === "list"
                  ? "bg-flat text-fg shadow-sm"
                  : "text-fg-faint hover:text-fg-dim"
              }`}
              title="List View"
            >
              ☰
            </button>
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`p-1.5 rounded text-xs transition-colors ${
                viewMode === "grid"
                  ? "bg-flat text-fg shadow-sm"
                  : "text-fg-faint hover:text-fg-dim"
              }`}
              title="Grid View"
            >
              ⊞
            </button>
          </div>
        </div>
      </div>

      {/* Asset List / Grid Container */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-2 min-h-0 custom-scrollbar">
        {/* Results Counter & Active Category Badge */}
        <div className="flex items-center justify-between text-xs text-fg-dim pb-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-fg">
              {sortedAssets.length} {sortedAssets.length === 1 ? "asset" : "assets"} found
            </span>
            {filter.search_query && (
              <span className="text-[11px] bg-flat text-fg-dim px-2 py-0.5 rounded-full">
                &ldquo;{filter.search_query}&rdquo;
              </span>
            )}
          </div>
          <span className="text-[11px] text-fg-faint">
            Click an asset to inspect, preview & send to timeline
          </span>
        </div>

        {/* Empty State */}
        {sortedAssets.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center border border-dashed border-edge rounded-xl bg-ink/40 p-6">
            <div className="w-12 h-12 rounded-full bg-flat/80 flex items-center justify-center text-xl mb-3 text-fg-dim">
              🎵
            </div>
            <h3 className="text-sm font-semibold text-fg mb-1">No audio assets found</h3>
            <p className="text-xs text-fg-faint max-w-sm mb-4">
              Try adjusting your search keywords, switching categories, or clearing active filters.
            </p>
            <button
              type="button"
              onClick={() =>
                onUpdateFilter({
                  search_query: "",
                  selected_type: "all",
                  selected_category: "background_music",
                  only_loopable: false,
                })
              }
              className="px-3.5 py-1.5 bg-accent hover:bg-accent text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
            >
              Reset Filters
            </button>
          </div>
        )}

        {/* List View */}
        {viewMode === "list" && sortedAssets.length > 0 && (
          <div className="space-y-1.5">
            {sortedAssets.map((asset) => {
              const isSelected = selectedAssetId === asset.id;
              const isPlaying =
                previewState.playing_asset_id === asset.id && previewState.is_playing;
              const isMissing = asset.availability === "MISSING_FILE";

              return (
                <div
                  key={asset.id}
                  onClick={() => onSelectAsset(asset)}
                  className={`group relative flex items-center gap-3 p-2.5 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? "bg-accent/30 border-accent/60 shadow-md ring-1 ring-accent/40"
                      : "bg-ink/60 border-edge/80 hover:bg-navy hover:border-edge"
                  }`}
                >
                  {/* Play / Pause Button */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onTogglePlay(asset);
                    }}
                    disabled={isMissing}
                    className={`w-9 h-9 rounded-lg flex items-center justify-center text-sm shrink-0 transition-transform active:scale-95 shadow-sm ${
                      isMissing
                        ? "bg-flat/50 text-fg-faint cursor-not-allowed"
                        : isPlaying
                        ? "bg-warn text-ink font-bold hover:bg-warn"
                        : "bg-flat text-fg hover:bg-accent hover:text-white"
                    }`}
                    title={
                      isMissing
                        ? "Audio file missing on disk"
                        : isPlaying
                        ? "Pause preview"
                        : "Play preview"
                    }
                  >
                    {isMissing ? "⚠️" : isPlaying ? "⏸" : "▶"}
                  </button>

                  {/* Asset Details */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-semibold text-xs text-fg truncate group-hover:text-info transition-colors">
                        {asset.name}
                      </span>

                      {/* Type Badge */}
                      <span
                        className={`text-[10px] uppercase font-bold px-1.5 py-0.2 rounded ${
                          asset.type === "music"
                            ? "bg-accent/20 text-info border border-accent/60"
                            : "bg-ok/20 text-ok border border-ok/60"
                        }`}
                      >
                        {asset.type}
                      </span>

                      {/* Loopable Badge */}
                      {asset.loopable && (
                        <span
                          className="text-[10px] text-warn bg-warn/10 border border-warn/20 px-1 rounded flex items-center gap-0.5"
                          title="Seamless loopable"
                        >
                          🔁 Loop
                        </span>
                      )}

                      {/* Availability Badge */}
                      {isMissing ? (
                        <span className="text-[10px] font-semibold text-bad bg-bad/15 border border-bad/30 px-1.5 py-0.2 rounded">
                          Missing File
                        </span>
                      ) : asset.availability === "PREVIEW_ONLY" ? (
                        <span className="text-[10px] font-medium text-info bg-info/15 border border-info/30 px-1.5 py-0.2 rounded">
                          Preview Only
                        </span>
                      ) : null}
                    </div>

                    {/* Metadata Subline */}
                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-fg-dim">
                      <span className="font-mono text-fg-dim">
                        ⏱ {formatDuration(asset.duration_sec)}
                      </span>
                      {asset.bpm && <span>• {asset.bpm} BPM</span>}
                      {asset.key && <span>• {asset.key}</span>}
                      <span>• {asset.file_format.toUpperCase()}</span>
                      <span className="text-fg-faint truncate max-w-[180px]">
                        By {asset.license.author_or_source}
                      </span>
                    </div>

                    {/* Waveform vs Unmeasured Notice */}
                    <div className="mt-1.5 h-6 flex items-center">
                      {asset.measured_peaks && asset.measured_peaks.length > 0 ? (
                        <div
                          className="w-full max-w-md h-5 bg-navy/90 rounded px-1.5 flex items-center gap-0.5 overflow-hidden border border-edge/60"
                          title="Real measured audio waveform"
                        >
                          {asset.measured_peaks.map((peak, idx) => {
                            const progress =
                              isPlaying && previewState.duration_sec > 0
                                ? previewState.current_time_sec / previewState.duration_sec
                                : 0;
                            const barProgress = idx / asset.measured_peaks!.length;
                            const isPast = isPlaying && barProgress <= progress;

                            return (
                              <div
                                key={idx}
                                className={`flex-1 rounded-sm transition-colors ${
                                  isPast
                                    ? "bg-warn"
                                    : isPlaying
                                    ? "bg-accent/80"
                                    : "bg-fg-faint hover:bg-fg-dim"
                                }`}
                                style={{
                                  height: `${Math.max(15, Math.min(100, Math.round(peak * 100)))}%`,
                                }}
                              />
                            );
                          })}
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-[10px] text-fg-faint italic bg-navy/50 px-2 py-0.5 rounded border border-edge/40">
                          <span>📊</span>
                          <span>Real waveform unmeasured</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Actions & Favorite */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    {/* Favorite Button */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(asset.id);
                      }}
                      className={`p-1.5 rounded-lg text-sm transition-colors ${
                        asset.is_favorite
                          ? "text-warn hover:text-warn"
                          : "text-fg-faint hover:text-fg-dim"
                      }`}
                      title={asset.is_favorite ? "Remove from favorites" : "Add to favorites"}
                    >
                      {asset.is_favorite ? "⭐" : "☆"}
                    </button>

                    {/* Quick Send to Timeline Button */}
                    {onQuickSendToTimeline && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onQuickSendToTimeline(asset);
                        }}
                        disabled={isMissing}
                        className={`px-2 py-1 rounded text-[11px] font-semibold border transition-all ${
                          isMissing
                            ? "opacity-40 cursor-not-allowed border-edge text-fg-faint"
                            : "bg-accent/20 hover:bg-accent text-info hover:text-white border-accent/40 shadow-sm"
                        }`}
                        title="Add this audio cue to Timeline"
                      >
                        + Timeline
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Grid View */}
        {viewMode === "grid" && sortedAssets.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {sortedAssets.map((asset) => {
              const isSelected = selectedAssetId === asset.id;
              const isPlaying =
                previewState.playing_asset_id === asset.id && previewState.is_playing;
              const isMissing = asset.availability === "MISSING_FILE";

              return (
                <div
                  key={asset.id}
                  onClick={() => onSelectAsset(asset)}
                  className={`group flex flex-col p-3 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? "bg-accent/30 border-accent/60 shadow-md ring-1 ring-accent/40"
                      : "bg-ink/60 border-edge/80 hover:bg-navy hover:border-edge"
                  }`}
                >
                  {/* Card Header */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <h4 className="font-semibold text-xs text-fg truncate group-hover:text-info transition-colors">
                        {asset.name}
                      </h4>
                      <span className="text-[11px] text-fg-dim">
                        {formatDuration(asset.duration_sec)} • {asset.category.replace("_", " ")}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(asset.id);
                      }}
                      className={`text-sm shrink-0 ${
                        asset.is_favorite ? "text-warn" : "text-fg-faint hover:text-fg-dim"
                      }`}
                    >
                      {asset.is_favorite ? "⭐" : "☆"}
                    </button>
                  </div>

                  {/* Waveform / Unmeasured Display */}
                  <div className="h-10 bg-navy rounded-lg p-1.5 mb-2.5 flex items-center justify-center border border-edge/60 overflow-hidden">
                    {asset.measured_peaks && asset.measured_peaks.length > 0 ? (
                      <div className="w-full h-full flex items-center gap-0.5">
                        {asset.measured_peaks.map((peak, idx) => {
                          const progress =
                            isPlaying && previewState.duration_sec > 0
                              ? previewState.current_time_sec / previewState.duration_sec
                              : 0;
                          const barProgress = idx / asset.measured_peaks!.length;
                          const isPast = isPlaying && barProgress <= progress;

                          return (
                            <div
                              key={idx}
                              className={`flex-1 rounded-sm ${
                                isPast
                                  ? "bg-warn"
                                  : isPlaying
                                  ? "bg-accent/80"
                                  : "bg-fg-faint"
                              }`}
                              style={{
                                height: `${Math.max(15, Math.min(100, Math.round(peak * 100)))}%`,
                              }}
                            />
                          );
                        })}
                      </div>
                    ) : (
                      <span className="text-[10px] text-fg-faint italic">
                        Real waveform unmeasured
                      </span>
                    )}
                  </div>

                  {/* Tags & Badges */}
                  <div className="flex flex-wrap gap-1 mb-3">
                    <span
                      className={`text-[9px] uppercase font-bold px-1.5 py-0.2 rounded ${
                        asset.type === "music"
                          ? "bg-accent/20 text-info border border-accent/60"
                          : "bg-ok/20 text-ok border border-ok/60"
                      }`}
                    >
                      {asset.type}
                    </span>
                    {asset.loopable && (
                      <span className="text-[9px] text-warn bg-warn/10 px-1 rounded">
                        🔁 Loop
                      </span>
                    )}
                    {isMissing && (
                      <span className="text-[9px] font-semibold text-bad bg-bad/15 px-1 rounded">
                        Missing
                      </span>
                    )}
                  </div>

                  {/* Card Bottom: Play & Action */}
                  <div className="mt-auto flex items-center justify-between pt-2 border-t border-edge/60">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onTogglePlay(asset);
                      }}
                      disabled={isMissing}
                      className={`px-3 py-1 rounded text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                        isMissing
                          ? "bg-flat/50 text-fg-faint cursor-not-allowed"
                          : isPlaying
                          ? "bg-warn text-ink"
                          : "bg-flat text-fg hover:bg-glass-hi"
                      }`}
                    >
                      <span>{isPlaying ? "⏸" : "▶"}</span>
                      <span>{isPlaying ? "Pause" : "Play"}</span>
                    </button>

                    {onQuickSendToTimeline && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onQuickSendToTimeline(asset);
                        }}
                        disabled={isMissing}
                        className={`text-[11px] font-semibold px-2 py-1 rounded border ${
                          isMissing
                            ? "opacity-30 border-edge text-fg-faint"
                            : "bg-accent/20 hover:bg-accent text-info hover:text-white border-accent/30"
                        }`}
                      >
                        + Timeline
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
