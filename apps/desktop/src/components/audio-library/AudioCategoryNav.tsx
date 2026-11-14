import React from "react";
import { Icons, Badge } from "@panelflow/ui";
import type { AudioCategory, AudioFilterState, AudioAsset } from "./AudioLibrary.types.ts";

interface AudioCategoryNavProps {
  filter: AudioFilterState;
  onUpdateFilter: (updates: Partial<AudioFilterState>) => void;
  assets: AudioAsset[];
}

interface CategoryDefinition {
  id: AudioCategory;
  label: string;
  icon: string;
  type: "music" | "sfx" | "both";
  description: string;
}

const CATEGORIES: CategoryDefinition[] = [
  { id: "background_music", label: "Background Music", icon: "🎵", type: "music", description: "All continuous background scores" },
  { id: "cinematic", label: "Cinematic", icon: "🎬", type: "music", description: "Orchestral and filmic storytelling cues" },
  { id: "suspense", label: "Suspense", icon: "🕵️", type: "music", description: "Drones, tension and dark pulses" },
  { id: "emotional", label: "Emotional", icon: "💔", type: "music", description: "Melancholic piano and solo strings" },
  { id: "action", label: "Action", icon: "⚡", type: "music", description: "Driving percussion and high-tempo battle themes" },
  { id: "fantasy", label: "Fantasy", icon: "🐉", type: "music", description: "Mythical harps, flutes and majestic skies" },
  { id: "ambient", label: "Ambient", icon: "🌌", type: "music", description: "Atmospheric textures and subtle pads" },
  { id: "environmental", label: "Environmental", icon: "🌲", type: "sfx", description: "Wind, weather, rain and natural acoustics" },
  { id: "character", label: "Character Sounds", icon: "👤", type: "sfx", description: "Foley, cloth rustles, weapons and footfalls" },
  { id: "transitions", label: "Transitions", icon: "🔀", type: "sfx", description: "Whooshes, risers, page turns and wipes" },
  { id: "magic_fx", label: "Magic & FX", icon: "✨", type: "sfx", description: "Energy blasts, crystal spells and detonations" },
  { id: "favorites", label: "Favorites", icon: "⭐", type: "both", description: "Your starred and bookmarked audio cues" },
];

export const AudioCategoryNav: React.FC<AudioCategoryNavProps> = ({
  filter,
  onUpdateFilter,
  assets,
}) => {
  // Count assets per category
  const getCategoryCount = (catId: AudioCategory) => {
    if (catId === "favorites") {
      return assets.filter((a) => a.is_favorite).length;
    }
    if (catId === "background_music") {
      return assets.filter((a) => a.type === "music").length;
    }
    return assets.filter((a) => a.category === catId).length;
  };

  const favoriteCount = getCategoryCount("favorites");

  return (
    <aside className="w-64 bg-ink border-r border-edge flex flex-col h-full select-none shrink-0 overflow-hidden">
      {/* Top Header */}
      <div className="p-3.5 border-b border-edge bg-ink/80 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-warn/15 text-warn border border-warn/30 flex items-center justify-center text-xs font-bold shadow-sm">
            ♫
          </div>
          <span className="text-xs font-extrabold uppercase tracking-wider text-fg">
            Audio Library
          </span>
        </div>
        <span className="text-[10px] text-fg-faint font-mono">
          {assets.length} Assets
        </span>
      </div>

      {/* Type Filter Tabs: All | Music | SFX */}
      <div className="p-2 border-b border-edge/60 bg-navy/40 shrink-0">
        <div className="grid grid-cols-3 gap-1 bg-ink p-1 rounded-lg border border-edge text-[11px] font-medium">
          <button
            type="button"
            onClick={() => onUpdateFilter({ selected_type: "all" })}
            className={`py-1 rounded text-center transition-colors ${
              filter.selected_type === "all"
                ? "bg-accent text-white font-bold shadow-sm"
                : "text-fg-dim hover:text-fg"
            }`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => onUpdateFilter({
              selected_type: "music",
              selected_category: ["environmental", "character", "transitions", "magic_fx"].includes(filter.selected_category)
                ? "background_music"
                : filter.selected_category,
            })}
            className={`py-1 rounded text-center transition-colors ${
              filter.selected_type === "music"
                ? "bg-accent text-white font-bold shadow-sm"
                : "text-fg-dim hover:text-fg"
            }`}
          >
            Music
          </button>
          <button
            type="button"
            onClick={() => onUpdateFilter({
              selected_type: "sfx",
              selected_category: filter.selected_category === "background_music" || ["cinematic", "suspense", "emotional", "action", "fantasy", "ambient"].includes(filter.selected_category)
                ? "character"
                : filter.selected_category,
            })}
            className={`py-1 rounded text-center transition-colors ${
              filter.selected_type === "sfx"
                ? "bg-accent text-white font-bold shadow-sm"
                : "text-fg-dim hover:text-fg"
            }`}
          >
            SFX
          </button>
        </div>
      </div>

      {/* Categories List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5 min-h-0 custom-scrollbar">
        {/* Special Favorites Pin */}
        <button
          type="button"
          onClick={() => onUpdateFilter({ selected_category: "favorites" })}
          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
            filter.selected_category === "favorites"
              ? "bg-warn/15 text-warn font-bold border border-warn/30 shadow-sm"
              : "text-fg-dim hover:bg-navy/80 hover:text-white"
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="text-sm">⭐</span>
            <span>Favorites</span>
          </div>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full font-mono bg-flat text-fg-dim">
            {favoriteCount}
          </span>
        </button>

        <div className="pt-2 pb-1 px-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-fg-faint">
            Music Categories
          </span>
        </div>

        {CATEGORIES.filter((c) => c.type === "music").map((cat) => {
          const isActive = filter.selected_category === cat.id;
          const count = getCategoryCount(cat.id);
          return (
            <button
              key={cat.id}
              type="button"
              onClick={() => onUpdateFilter({ selected_category: cat.id })}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? "bg-accent/20 text-info font-bold border border-accent/30 shadow-sm"
                  : "text-fg-dim hover:bg-navy/60 hover:text-fg"
              }`}
            >
              <div className="flex items-center gap-2 truncate">
                <span className="text-sm shrink-0">{cat.icon}</span>
                <span className="truncate">{cat.label}</span>
              </div>
              <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-navy text-fg-faint border border-edge shrink-0">
                {count}
              </span>
            </button>
          );
        })}

        <div className="pt-3 pb-1 px-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-fg-faint">
            Sound Effects
          </span>
        </div>

        {CATEGORIES.filter((c) => c.type === "sfx").map((cat) => {
          const isActive = filter.selected_category === cat.id;
          const count = getCategoryCount(cat.id);
          return (
            <button
              key={cat.id}
              type="button"
              onClick={() => onUpdateFilter({ selected_category: cat.id })}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? "bg-accent/20 text-info font-bold border border-accent/30 shadow-sm"
                  : "text-fg-dim hover:bg-navy/60 hover:text-fg"
              }`}
            >
              <div className="flex items-center gap-2 truncate">
                <span className="text-sm shrink-0">{cat.icon}</span>
                <span className="truncate">{cat.label}</span>
              </div>
              <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-navy text-fg-faint border border-edge shrink-0">
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Bottom Option: Loopable Only Filter */}
      <div className="p-3 border-t border-edge/80 bg-ink shrink-0">
        <label className="flex items-center gap-2 text-xs text-fg-dim cursor-pointer hover:text-fg">
          <input
            type="checkbox"
            checked={filter.only_loopable}
            onChange={(e) => onUpdateFilter({ only_loopable: e.target.checked })}
            className="rounded bg-navy border-edge text-accent focus:ring-0 focus:outline-none accent-accent"
          />
          <span>Loopable Assets Only</span>
        </label>
      </div>
    </aside>
  );
};
