import React from "react";
import { Box } from "lucide-react";
import { ErrorNotificationBell } from "../error";

interface DashboardHeaderProps {
  engineConnected: boolean;
  engineVersion: string;
  onOpenToolsModels: () => void;
  onRetryEngine?: () => void;
  retryingEngine?: boolean;
  onRestartEngine?: () => void;
  restartingEngine?: boolean;
}

export const DashboardHeader: React.FC<DashboardHeaderProps> = ({
  engineConnected,
  engineVersion,
  onOpenToolsModels,
  onRetryEngine,
  retryingEngine,
  onRestartEngine,
  restartingEngine,
}) => {
  return (
    <header className="h-16 border-b border-[#1d2538] bg-[#0b0f18]/95 px-5 flex items-center justify-between flex-shrink-0 z-20 select-none backdrop-blur-xl">
      {/* Left: Logo & Tagline */}
      <div className="flex items-center">
        <div className="flex items-center gap-2.5 cursor-pointer">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-[#6d5dfc] to-[#3f37c9] flex items-center justify-center text-white font-black text-sm shadow-lg shadow-indigo-900/40 flex-shrink-0">
            <span className="-rotate-6">P</span>
          </div>
          <span className="text-zinc-100 font-semibold text-[15px] tracking-tight whitespace-nowrap">
            PanelFlow Studio
          </span>
        </div>

        <div className="hidden md:flex items-center ml-3 pl-3 border-l border-zinc-800">
          <span className="text-[11px] text-zinc-500 font-normal truncate">
            Story-to-motion production workspace
          </span>
        </div>
      </div>

      {/* Right: Alerts Bell + Tools & Models + Engine Status */}
      <div className="flex items-center gap-3">
        <ErrorNotificationBell />

        <button
          onClick={onOpenToolsModels}
          className="bg-[#151b2a] hover:bg-[#20283d] border border-[#27324c] text-indigo-200 hover:text-white text-xs font-medium rounded-lg px-3 py-2 flex items-center gap-1.5 transition-colors shadow-sm"
          title="Inspect local models, workers, and tool engines"
        >
          <Box className="w-3.5 h-3.5 text-indigo-300" />
          <span>Workspace health</span>
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
          className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wider uppercase border ${
            engineConnected
              ? "bg-[#062e20] text-emerald-400 border-emerald-700/80"
              : "bg-rose-950/80 text-rose-400 border-rose-800"
          }`}
        >
          {engineConnected ? "CONNECTED" : "OFFLINE"}
        </span>

        {onRestartEngine && (
          <button onClick={onRestartEngine} disabled={!engineConnected || restartingEngine || retryingEngine}
            className="text-xs text-zinc-300 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {restartingEngine ? "Restarting…" : "Restart Engine"}
          </button>
        )}
        {!engineConnected && onRetryEngine && !restartingEngine && (
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
