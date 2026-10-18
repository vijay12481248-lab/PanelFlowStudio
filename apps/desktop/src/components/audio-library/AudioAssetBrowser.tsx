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
    <div className="flex-1 flex flex-col h-full bg-zinc-900 min-w-0 overflow-hidden">
      {/* Top Search & Filter Bar */}
      <div className="p-3.5 border-b border-zinc-800 bg-zinc-950/70 flex flex-wrap items-center justify-between gap-3 shrink-0">
        {/* Search Input */}
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-zinc-500 text-xs">
            🔍
          </span>
          <input
            type="text"
            value={filter.search_query}
            onChange={(e) => onUpdateFilter({ search_query: e.target.value })}
            placeholder="Search audio by title, tag, tempo, key, author..."
            className="w-full pl-8 pr-8 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
          />
          {filter.search_query && (
            <button
              type="button"
              onClick={() => onUpdateFilter({ search_query: "" })}
              className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-zinc-500 hover:text-zinc-300 text-xs"
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
                ? "bg-amber-500/20 border-amber-500/50 text-amber-300"
                : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
            }`}
            title="Filter loopable audio assets"
          >
            <span>🔁</span>
            <span className="hidden sm:inline">Loopable</span>
          </button>

          {/* Sort Dropdown */}
          <div className="flex items-center gap-1.5 bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1">
            <span className="text-[10px] text-zinc-500 font-medium uppercase">Sort:</span>
            <select
              value={filter.sort_by}
              onChange={(e) => onUpdateFilter({ sort_by: e.target.value as AudioSortOption })}
              className="bg-transparent text-xs text-zinc-200 focus:outline-none cursor-pointer"
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
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`p-1.5 rounded text-xs transition-colors ${
                viewMode === "list"
                  ? "bg-zinc-800 text-zinc-100 shadow-sm"
                  : "text-zinc-500 hover:text-zinc-300"
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
                  ? "bg-zinc-800 text-zinc-100 shadow-sm"
                  : "text-zinc-500 hover:text-zinc-300"
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
        <div className="flex items-center justify-between text-xs text-zinc-400 pb-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-zinc-200">
              {sortedAssets.length} {sortedAssets.length === 1 ? "asset" : "assets"} found
            </span>
            {filter.search_query && (
              <span className="text-[11px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded-full">
                &ldquo;{filter.search_query}&rdquo;
              </span>
            )}
          </div>
          <span className="text-[11px] text-zinc-500">
            Click an asset to inspect, preview & send to timeline
          </span>
        </div>

        {/* Empty State */}
        {sortedAssets.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center border border-dashed border-zinc-800 rounded-xl bg-zinc-950/40 p-6">
            <div className="w-12 h-12 rounded-full bg-zinc-800/80 flex items-center justify-center text-xl mb-3 text-zinc-400">
              🎵
            </div>
            <h3 className="text-sm font-semibold text-zinc-200 mb-1">No audio assets found</h3>
            <p className="text-xs text-zinc-500 max-w-sm mb-4">
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
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
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
                      ? "bg-indigo-950/30 border-indigo-500/60 shadow-md ring-1 ring-indigo-500/40"
                      : "bg-zinc-950/60 border-zinc-800/80 hover:bg-zinc-900 hover:border-zinc-700"
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
                        ? "bg-zinc-800/50 text-zinc-600 cursor-not-allowed"
                        : isPlaying
                        ? "bg-amber-500 text-zinc-950 font-bold hover:bg-amber-400"
                        : "bg-zinc-800 text-zinc-200 hover:bg-indigo-600 hover:text-white"
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
                      <span className="font-semibold text-xs text-zinc-100 truncate group-hover:text-indigo-300 transition-colors">
                        {asset.name}
                      </span>

                      {/* Type Badge */}
                      <span
                        className={`text-[10px] uppercase font-bold px-1.5 py-0.2 rounded ${
                          asset.type === "music"
                            ? "bg-purple-950 text-purple-300 border border-purple-800/60"
                            : "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                        }`}
                      >
                        {asset.type}
                      </span>

                      {/* Loopable Badge */}
                      {asset.loopable && (
                        <span
                          className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1 rounded flex items-center gap-0.5"
                          title="Seamless loopable"
                        >
                          🔁 Loop
                        </span>
                      )}

                      {/* Availability Badge */}
                      {isMissing ? (
                        <span className="text-[10px] font-semibold text-rose-400 bg-rose-500/15 border border-rose-500/30 px-1.5 py-0.2 rounded">
                          Missing File
                        </span>
                      ) : asset.availability === "PREVIEW_ONLY" ? (
                        <span className="text-[10px] font-medium text-sky-400 bg-sky-500/15 border border-sky-500/30 px-1.5 py-0.2 rounded">
                          Preview Only
                        </span>
                      ) : null}
                    </div>

                    {/* Metadata Subline */}
                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-zinc-400">
                      <span className="font-mono text-zinc-300">
                        ⏱ {formatDuration(asset.duration_sec)}
                      </span>
                      {asset.bpm && <span>• {asset.bpm} BPM</span>}
                      {asset.key && <span>• {asset.key}</span>}
                      <span>• {asset.file_format.toUpperCase()}</span>
                      <span className="text-zinc-500 truncate max-w-[180px]">
                        By {asset.license.author_or_source}
                      </span>
                    </div>

                    {/* Waveform vs Unmeasured Notice */}
                    <div className="mt-1.5 h-6 flex items-center">
                      {asset.measured_peaks && asset.measured_peaks.length > 0 ? (
                        <div
                          className="w-full max-w-md h-5 bg-zinc-900/90 rounded px-1.5 flex items-center gap-0.5 overflow-hidden border border-zinc-800/60"
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
                                    ? "bg-amber-400"
                                    : isPlaying
                                    ? "bg-indigo-400/80"
                                    : "bg-zinc-600 hover:bg-zinc-400"
                                }`}
                                style={{
                                  height: `${Math.max(15, Math.min(100, Math.round(peak * 100)))}%`,
                                }}
                              />
                            );
                          })}
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 italic bg-zinc-900/50 px-2 py-0.5 rounded border border-zinc-800/40">
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
                          ? "text-amber-400 hover:text-amber-300"
                          : "text-zinc-600 hover:text-zinc-300"
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
                            ? "opacity-40 cursor-not-allowed border-zinc-800 text-zinc-500"
                            : "bg-indigo-600/20 hover:bg-indigo-600 text-indigo-300 hover:text-white border-indigo-500/40 shadow-sm"
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
                      ? "bg-indigo-950/30 border-indigo-500/60 shadow-md ring-1 ring-indigo-500/40"
                      : "bg-zinc-950/60 border-zinc-800/80 hover:bg-zinc-900 hover:border-zinc-700"
                  }`}
                >
                  {/* Card Header */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <h4 className="font-semibold text-xs text-zinc-100 truncate group-hover:text-indigo-300 transition-colors">
                        {asset.name}
                      </h4>
                      <span className="text-[11px] text-zinc-400">
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
                        asset.is_favorite ? "text-amber-400" : "text-zinc-600 hover:text-zinc-300"
                      }`}
                    >
                      {asset.is_favorite ? "⭐" : "☆"}
                    </button>
                  </div>

                  {/* Waveform / Unmeasured Display */}
                  <div className="h-10 bg-zinc-900 rounded-lg p-1.5 mb-2.5 flex items-center justify-center border border-zinc-800/60 overflow-hidden">
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
                                  ? "bg-amber-400"
                                  : isPlaying
                                  ? "bg-indigo-400/80"
                                  : "bg-zinc-600"
                              }`}
                              style={{
                                height: `${Math.max(15, Math.min(100, Math.round(peak * 100)))}%`,
                              }}
                            />
                          );
                        })}
                      </div>
                    ) : (
                      <span className="text-[10px] text-zinc-500 italic">
                        Real waveform unmeasured
                      </span>
                    )}
                  </div>

                  {/* Tags & Badges */}
                  <div className="flex flex-wrap gap-1 mb-3">
                    <span
                      className={`text-[9px] uppercase font-bold px-1.5 py-0.2 rounded ${
                        asset.type === "music"
                          ? "bg-purple-950 text-purple-300 border border-purple-800/60"
                          : "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                      }`}
                    >
                      {asset.type}
                    </span>
                    {asset.loopable && (
                      <span className="text-[9px] text-amber-400 bg-amber-500/10 px-1 rounded">
                        🔁 Loop
                      </span>
                    )}
                    {isMissing && (
                      <span className="text-[9px] font-semibold text-rose-400 bg-rose-500/15 px-1 rounded">
                        Missing
                      </span>
                    )}
                  </div>

                  {/* Card Bottom: Play & Action */}
                  <div className="mt-auto flex items-center justify-between pt-2 border-t border-zinc-800/60">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onTogglePlay(asset);
                      }}
                      disabled={isMissing}
                      className={`px-3 py-1 rounded text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                        isMissing
                          ? "bg-zinc-800/50 text-zinc-600 cursor-not-allowed"
                          : isPlaying
                          ? "bg-amber-500 text-zinc-950"
                          : "bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
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
                            ? "opacity-30 border-zinc-800 text-zinc-600"
                            : "bg-indigo-600/20 hover:bg-indigo-600 text-indigo-300 hover:text-white border-indigo-500/30"
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
