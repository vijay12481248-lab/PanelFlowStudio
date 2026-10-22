import React from "react";
import { Icons } from "@panelflow/ui";

export type LeftRailTab = "pages" | "story" | "narration" | "motion" | "audio" | "settings";

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
              className={`relative flex min-h-[72px] shrink-0 flex-col items-center justify-center gap-2 py-3 px-1 rounded-lg transition-colors duration-150 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400 ${
                isActive
                  ? "bg-gradient-to-br from-violet-600/20 to-indigo-600/10 text-violet-300 font-semibold shadow-[inset_0_0_24px_#713fff12]"
                  : "text-slate-300 hover:text-white hover:bg-white/5"
              }`}
              title={tab.label}
            >
              {isActive && (
                <span aria-hidden="true" className="absolute -left-2 top-1/2 -translate-y-1/2 w-1 h-12 bg-violet-500 rounded-r-full shadow-[0_0_14px_#8b5cf680]" />
              )}
              <span aria-hidden="true" className={isActive ? "text-violet-400" : "text-slate-300"}>
                {tab.icon}
              </span>
              <span className="text-[11px] lg:text-xs tracking-tight leading-none">
                {tab.label}
              </span>
            </button>
          );
        })}
      </nav>
      <div role="status" aria-live="polite" className="mx-2 mt-3 flex self-stretch shrink-0 flex-col items-center gap-1 rounded-lg border border-[#30364a] bg-[#0b0d15] px-1 py-2.5 text-[10px] lg:text-xs">
        <span className="flex items-center gap-1.5 text-slate-300">
          <span aria-hidden="true" className={`h-2 w-2 rounded-full border ${engineConnected === true ? "border-emerald-400 bg-emerald-400/20" : engineConnected === false ? "border-rose-400 bg-rose-400/20" : "border-amber-400 bg-amber-400/20"}`} />Engine
        </span>
        <span className={`font-semibold ${engineConnected === true ? "text-emerald-400" : engineConnected === false ? "text-rose-400" : "text-amber-300"}`}>
          {engineConnected === true ? "Healthy" : engineConnected === false ? "Offline" : "Checking"}
        </span>
      </div>
    </aside>
  );
};
