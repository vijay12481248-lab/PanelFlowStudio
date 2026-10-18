import React from "react";
import { Home, Folder, Layers, BookOpen, Settings } from "lucide-react";
import type { NavTabId } from "./types";

interface AppNavigationRailProps {
  activeTab: NavTabId;
  onSelectTab: (tab: NavTabId) => void;
  onOpenSettings: () => void;
  onOpenLibrary?: () => void;
}

export const AppNavigationRail: React.FC<AppNavigationRailProps> = ({
  activeTab,
  onSelectTab,
  onOpenSettings,
  onOpenLibrary,
}) => {
  const navItems = [
    { id: "home" as NavTabId, label: "Home", icon: Home },
    { id: "projects" as NavTabId, label: "Projects", icon: Folder },
    { id: "jobs" as NavTabId, label: "Jobs", icon: Layers },
    { id: "library" as NavTabId, label: "Library", icon: BookOpen },
  ];

  return (
    <nav
      className="w-[68px] bg-[#0c0e17] border-r border-[#181c2b] flex flex-col items-center py-3 flex-shrink-0 z-10 justify-between select-none"
      aria-label="Application Navigation"
    >
      {/* Top Group */}
      <div className="flex flex-col items-center gap-2 w-full px-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <button
              key={item.id}
              onClick={() => {
                if (item.id === "library" && onOpenLibrary) {
                  onOpenLibrary();
                } else {
                  onSelectTab(item.id);
                }
              }}
              className={`w-12 h-12 rounded-xl flex flex-col items-center justify-center gap-1 transition-all ${
                isActive
                  ? "bg-[#3b49df] text-white shadow-md shadow-indigo-600/30"
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-[#141826]"
              }`}
              title={item.label}
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              <span className="text-[10px] font-medium leading-none tracking-tight">
                {item.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Bottom Group (Settings) */}
      <div className="flex flex-col items-center gap-2 w-full px-2 pb-1">
        <button
          onClick={onOpenSettings}
          className={`w-12 h-12 rounded-xl flex flex-col items-center justify-center gap-1 transition-all ${
            activeTab === "settings"
              ? "bg-[#3b49df] text-white shadow-md shadow-indigo-600/30"
              : "text-zinc-400 hover:text-zinc-100 hover:bg-[#141826]"
          }`}
          title="Settings & Diagnostics"
        >
          <Settings className="w-5 h-5 flex-shrink-0" />
          <span className="text-[10px] font-medium leading-none tracking-tight">
            Settings
          </span>
        </button>
      </div>
    </nav>
  );
};
