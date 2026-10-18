import React from "react";
import { Box, Wrench } from "lucide-react";

interface DashboardHeaderProps {
  engineConnected: boolean;
  engineVersion: string;
  onOpenToolsModels: () => void;
  onRetryEngine?: () => void;
  retryingEngine?: boolean;
}

export const DashboardHeader: React.FC<DashboardHeaderProps> = ({
  engineConnected,
  engineVersion,
  onOpenToolsModels,
  onRetryEngine,
  retryingEngine,
}) => {
  return (
    <header className="h-14 border-b border-[#181c2b] bg-[#0c0e18] px-4 flex items-center justify-between flex-shrink-0 z-20 select-none">
      {/* Left: Logo & Tagline */}
      <div className="flex items-center">
        <div className="flex items-center gap-2.5 cursor-pointer">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-md shadow-indigo-600/30 flex-shrink-0">
            P
          </div>
          <span className="text-zinc-100 font-bold text-sm tracking-tight whitespace-nowrap">
            PanelFlow Studio
          </span>
        </div>

        <div className="hidden md:flex items-center ml-3 pl-3 border-l border-zinc-800">
          <span className="text-xs text-zinc-400 font-normal truncate">
            AI-Assisted Motion Comic Ingestion & Production Engine
          </span>
        </div>
      </div>

      {/* Right: Tools & Models + Engine Status */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenToolsModels}
          className="bg-[#151928] hover:bg-[#1d2338] border border-[#242c44] text-indigo-300 hover:text-indigo-200 text-xs font-medium rounded-lg px-3 py-1.5 flex items-center gap-1.5 transition-colors shadow-sm"
          title="Inspect local models, workers, and tool engines"
        >
          <Box className="w-3.5 h-3.5 text-indigo-400" />
          <span>Tools & Models</span>
        </button>

        <div className="flex items-center gap-2 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              engineConnected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
            }`}
          />
          <span className="text-zinc-300 font-mono text-[11px] hidden sm:inline">
            Local Engine v{engineVersion || "1.0.0-beta.2"}
          </span>
        </div>

        <span
          className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border ${
            engineConnected
              ? "bg-[#062e20] text-emerald-400 border-emerald-700/80"
              : "bg-rose-950/80 text-rose-400 border-rose-800"
          }`}
        >
          {engineConnected ? "CONNECTED" : "OFFLINE"}
        </span>

        {!engineConnected && onRetryEngine && (
          <button
            onClick={onRetryEngine}
            disabled={retryingEngine}
            className="text-[11px] text-rose-300 hover:underline ml-1"
          >
            {retryingEngine ? "Connecting..." : "Retry"}
          </button>
        )}
      </div>
    </header>
  );
};
