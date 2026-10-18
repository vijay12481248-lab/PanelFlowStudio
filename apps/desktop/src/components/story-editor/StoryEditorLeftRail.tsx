import React from "react";
import { Icons } from "@panelflow/ui";

export type LeftRailTab = "pages" | "story" | "narration" | "motion" | "audio" | "settings";

interface StoryEditorLeftRailProps {
  activeTab: LeftRailTab;
  onSelectTab: (tab: LeftRailTab) => void;
}

export const StoryEditorLeftRail: React.FC<StoryEditorLeftRailProps> = ({
  activeTab,
  onSelectTab,
}) => {
  const tabs: Array<{ id: LeftRailTab; label: string; icon: React.ReactNode }> = [
    {
      id: "pages",
      label: "Pages",
      icon: <Icons.BookOpen className="w-5 h-5" />,
    },
    {
      id: "story",
      label: "Story",
      icon: <Icons.Film className="w-5 h-5" />,
    },
    {
      id: "narration",
      label: "Voice",
      icon: <Icons.MessageSquare className="w-5 h-5" />,
    },
    {
      id: "motion",
      label: "Motion",
      icon: <Icons.Sparkles className="w-5 h-5" />,
    },
    {
      id: "audio",
      label: "Audio",
      icon: <Icons.Music className="w-5 h-5" />,
    },
    {
      id: "settings",
      label: "Settings",
      icon: <Icons.Sliders className="w-5 h-5" />,
    },
  ];

  return (
    <aside className="w-16 bg-zinc-950 border-r border-zinc-800 flex flex-col items-center py-3 select-none z-30 shrink-0">
      <div className="flex flex-col gap-1.5 w-full px-2">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onSelectTab(tab.id)}
              className={`relative flex flex-col items-center justify-center py-2.5 px-1 rounded-xl transition-all duration-150 group ${
                isActive
                  ? "bg-indigo-600/15 text-indigo-400 font-semibold border border-indigo-500/30 shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60"
              }`}
              title={tab.label}
            >
              {isActive && (
                <span className="absolute -left-2 top-1/2 -translate-y-1/2 w-1 h-5 bg-indigo-500 rounded-r-full shadow-sm shadow-indigo-500/50" />
              )}
              <div className="transition-transform duration-150 group-hover:scale-110">
                {tab.icon}
              </div>
              <span className="text-[10px] mt-1 tracking-tight leading-none">
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
};
