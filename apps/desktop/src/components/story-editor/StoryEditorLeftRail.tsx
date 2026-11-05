import React from "react";
import { Icons } from "@panelflow/ui";

export type LeftRailTab = "pages" | "story" | "narration" | "motion" | "chronoflow" | "audio" | "settings";

interface StoryEditorLeftRailProps {
  activeTab: LeftRailTab;
  onSelectTab: (tab: LeftRailTab) => void;
  engineConnected?: boolean;
}

export const StoryEditorLeftRail: React.FC<StoryEditorLeftRailProps> = ({
  activeTab,
  onSelectTab,
  engineConnected,
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
      id: "chronoflow",
      label: "AI Video",
      icon: <Icons.Sparkles className="w-5 h-5 text-purple-400" />,
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
    <aside className="w-[72px] lg:w-[100px] min-h-0 bg-[#0d1019] border-r border-[#262a3b] flex flex-col items-center py-3 select-none z-30 shrink-0">
      <nav aria-label="Editor workspaces" className="flex min-h-0 flex-1 flex-col gap-2 w-full overflow-y-auto px-2 pb-3">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onSelectTab(tab.id)}
              aria-pressed={isActive}
              className={`w-full py-2.5 px-1 rounded-xl flex flex-col items-center justify-center gap-1 transition-all ${
                isActive
                  ? tab.id === "chronoflow"
                    ? "bg-[#281347] text-purple-300 font-semibold border border-purple-500/50 shadow-md shadow-purple-900/40"
                    : "bg-[#333d6a] text-white font-semibold border border-indigo-400/40 shadow-sm shadow-indigo-950/50"
                  : tab.id === "chronoflow"
                  ? "text-purple-400 hover:text-purple-200 hover:bg-[#1a132b]"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-[#191d2d]"
              }`}
            >
              <div className="flex items-center justify-center">
                {tab.icon}
              </div>
              <span className="text-[10px] lg:text-[11px] leading-tight text-center font-medium">
                {tab.label}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Engine Status indicator footer */}
      <div className="pt-2 border-t border-[#232738] w-full flex flex-col items-center gap-1 px-1">
        <div className="flex items-center gap-1.5" title={engineConnected ? "Backend Engine Online" : "Backend Engine Offline"}>
          <div className={`w-2 h-2 rounded-full ${engineConnected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"}`} />
          <span className="text-[9px] text-zinc-400 font-mono hidden lg:inline">
            {engineConnected ? "ENGINE" : "OFFLINE"}
          </span>
        </div>
      </div>
    </aside>
  );
};
