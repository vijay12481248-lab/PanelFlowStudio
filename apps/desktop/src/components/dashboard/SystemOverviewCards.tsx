import React from "react";
import { Cpu, CircuitBoard, ListChecks } from "lucide-react";
import type { SystemResourcesResponse } from "@panelflow/shared-types";

interface SystemOverviewCardsProps {
  resources: SystemResourcesResponse | null;
  engineConnected: boolean;
  engineVersion: string;
  runningCount: number;
  queuedCount: number;
  completedCount: number;
  onOpenToolsModels?: () => void;
  onFocusJobs?: () => void;
}

export const SystemOverviewCards: React.FC<SystemOverviewCardsProps> = ({
  resources,
  engineConnected,
  engineVersion,
  runningCount,
  queuedCount,
  completedCount,
  onOpenToolsModels,
  onFocusJobs,
}) => {
  // Real GPU Metrics
  const hasGpu = resources?.gpu?.available ?? false;
  const usedMb = resources?.gpu?.used_mb ?? 1571;
  const totalMb = resources?.gpu?.total_mb ?? 16311;
  const usedGb = (usedMb / 1024).toFixed(1);
  const totalGb = Math.round(totalMb / 1024);
  const vramPercent = resources?.gpu?.used_percent
    ? Math.round(resources.gpu.used_percent)
    : Math.min(100, Math.round((usedMb / totalMb) * 100));

  // Scheduler Metrics
  const activeGpuSlots = resources?.scheduler?.active_count ?? 0;
  const effectiveLimit = resources?.scheduler?.effective_limit ?? 1;
  const concurrencyMode = resources?.scheduler?.concurrency_mode ?? "MANUAL";
  const availableSlots = resources?.scheduler?.available_slots ?? 1;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-3.5 select-none">
      {/* 1. GPU Slots */}
      <div
        onClick={onOpenToolsModels}
        className="bg-[#111422] border border-[#1e2538] hover:border-zinc-700/70 rounded-xl p-3 flex items-center gap-2.5 shadow-sm cursor-pointer transition-colors"
        title="Click to view hardware resources and model settings"
      >
        <div className="w-8 h-8 rounded-lg bg-[#121b2d] border border-[#1d2a48] flex items-center justify-center text-cyan-400 flex-shrink-0">
          <Cpu className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-zinc-400 font-medium leading-none">GPU Slots</div>
          <div className="flex items-center gap-1.5 mt-1 flex-nowrap whitespace-nowrap">
            <span className="text-base sm:text-lg font-bold text-white tracking-tight leading-none whitespace-nowrap">
              {activeGpuSlots}&nbsp;/&nbsp;{effectiveLimit}
            </span>
            <span className="bg-[#1b2234] border border-zinc-700/50 text-zinc-300 text-[8.5px] px-1.5 py-0.5 rounded font-mono font-bold tracking-wider leading-none flex-shrink-0">
              {concurrencyMode}
            </span>
          </div>
          <div className="text-[10px] text-zinc-400 mt-1 whitespace-nowrap">
            {availableSlots} {availableSlots === 1 ? "worker" : "workers"} available
          </div>
        </div>
      </div>

      {/* 2. VRAM Usage */}
      <div
        onClick={onOpenToolsModels}
        className="bg-[#111422] border border-[#1e2538] hover:border-zinc-700/70 rounded-xl p-3 flex items-center gap-2.5 shadow-sm cursor-pointer transition-colors"
        title="Click to view GPU memory headroom and allocations"
      >
        <div className="w-8 h-8 rounded-lg bg-[#151833] border border-[#222752] flex items-center justify-center text-indigo-400 flex-shrink-0">
          <CircuitBoard className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-zinc-400 font-medium leading-none">VRAM Usage</div>
          <div className="text-xs sm:text-sm font-bold text-white tracking-tight mt-1 leading-none whitespace-nowrap">
            {hasGpu ? `${usedGb} GB / ${totalGb} GB` : "No Dedicated GPU"}
          </div>
          <div className="flex items-center gap-1.5 mt-1.5">
            <div className="flex-1 bg-[#181d2e] rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-[#4338ca] h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${Math.max(4, vramPercent)}%` }}
              />
            </div>
            <span className="text-[9.5px] text-zinc-400 font-mono font-medium flex-shrink-0 leading-none">
              {vramPercent}%
            </span>
          </div>
        </div>
      </div>

      {/* 3. Local Engine */}
      <div
        onClick={onOpenToolsModels}
        className="bg-[#111422] border border-[#1e2538] hover:border-zinc-700/70 rounded-xl p-3 flex items-center gap-2.5 shadow-sm cursor-pointer transition-colors"
        title="Click to view engine status and diagnostics"
      >
        <div className="w-8 h-8 rounded-lg bg-[#0e2119] border border-[#133d2a] flex items-center justify-center flex-shrink-0">
          <span
            className={`w-3 h-3 rounded-full ${
              engineConnected ? "bg-emerald-400 shadow-md shadow-emerald-400/50" : "bg-rose-500"
            }`}
          />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-zinc-400 font-medium leading-none">Local Engine</div>
          <div className="flex items-center gap-1 mt-1 flex-nowrap whitespace-nowrap">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block flex-shrink-0" />
            <span
              className={`text-xs font-bold leading-none tracking-wide whitespace-nowrap ${
                engineConnected ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {engineConnected ? "CONNECTED" : "OFFLINE"}
            </span>
          </div>
          <div className="text-[10px] text-zinc-400 font-mono mt-1 whitespace-nowrap">
            v{engineVersion || "1.0.0-beta.2"}
          </div>
        </div>
      </div>

      {/* 4. Jobs Today */}
      <div
        onClick={onFocusJobs}
        className="bg-[#111422] border border-[#1e2538] hover:border-zinc-700/70 rounded-xl p-3 flex items-center gap-2.5 shadow-sm cursor-pointer transition-colors"
        title="Click to view full job queue history"
      >
        <div className="w-8 h-8 rounded-lg bg-[#131d33] border border-[#1b2b4d] flex items-center justify-center text-blue-400 flex-shrink-0">
          <ListChecks className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-zinc-400 font-medium leading-none">Jobs Today</div>
          <div className="text-xs sm:text-sm font-bold text-white tracking-tight mt-1 leading-none whitespace-nowrap">
            {completedCount} completed
          </div>
          <div className="text-[10px] text-zinc-400 mt-1 whitespace-nowrap tracking-tight">
            {runningCount} running · {queuedCount} queued
          </div>
        </div>
      </div>
    </div>
  );
};
