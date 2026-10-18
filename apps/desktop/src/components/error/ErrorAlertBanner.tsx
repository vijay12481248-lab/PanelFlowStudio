import React from "react";
import { AlertOctagon, AlertTriangle, Info, X, ChevronRight, Eye } from "lucide-react";
import { useError } from "../../context/ErrorContext";
import type { AppError } from "../../types/error";

export const ErrorAlertBanner: React.FC = () => {
  const { activeErrors, dismissError, clearAllErrors, inspectError } = useError();

  if (activeErrors.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="Error Alerts"
      className="fixed top-16 right-4 z-50 flex flex-col gap-2.5 max-w-md w-full pointer-events-none select-none"
    >
      {activeErrors.length > 1 && (
        <div className="flex items-center justify-between px-3 py-1 bg-[#1a1424]/90 backdrop-blur-md border border-rose-900/40 rounded-lg text-xs pointer-events-auto shadow-lg">
          <span className="text-rose-300 font-semibold text-[11px]">
            {activeErrors.length} Active System Alerts
          </span>
          <button
            onClick={clearAllErrors}
            className="text-[11px] text-zinc-400 hover:text-zinc-200 hover:underline"
          >
            Dismiss All
          </button>
        </div>
      )}

      {activeErrors.slice(0, 3).map((err) => {
        const isSevere = err.severity === "error";
        const isWarning = err.severity === "warning";

        return (
          <div
            key={err.id}
            className={`pointer-events-auto rounded-xl border p-3.5 shadow-2xl backdrop-blur-md transition-all duration-200 animate-in slide-in-from-top-2 ${
              isSevere
                ? "bg-[#180f1a]/95 border-rose-500/60 shadow-rose-950/50"
                : isWarning
                ? "bg-[#1a160f]/95 border-amber-500/60 shadow-amber-950/50"
                : "bg-[#101424]/95 border-indigo-500/60 shadow-indigo-950/50"
            }`}
          >
            <div className="flex items-start gap-3">
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  isSevere
                    ? "bg-rose-500/20 text-rose-400"
                    : isWarning
                    ? "bg-amber-500/20 text-amber-400"
                    : "bg-indigo-500/20 text-indigo-400"
                }`}
              >
                {isSevere ? (
                  <AlertOctagon className="w-4 h-4" />
                ) : isWarning ? (
                  <AlertTriangle className="w-4 h-4" />
                ) : (
                  <Info className="w-4 h-4" />
                )}
              </div>

              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center justify-between gap-1">
                  <h4 className="text-xs font-bold text-zinc-100 truncate">
                    {err.title}
                  </h4>
                  <span className="text-[10px] text-zinc-500 font-mono flex-shrink-0">
                    {new Date(err.timestamp).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>

                <p className="text-[11px] text-zinc-300 line-clamp-2 leading-relaxed">
                  {err.message}
                </p>

                <div className="flex items-center justify-between pt-1">
                  <button
                    onClick={() => inspectError(err)}
                    className="text-[11px] font-semibold text-cyan-300 hover:text-cyan-200 flex items-center gap-1 group transition-colors"
                  >
                    <Eye className="w-3 h-3 text-cyan-400" />
                    <span>View Error Details</span>
                    <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                  </button>

                  <button
                    onClick={() => dismissError(err.id)}
                    className="text-[10px] text-zinc-400 hover:text-zinc-200"
                  >
                    Dismiss
                  </button>
                </div>
              </div>

              <button
                onClick={() => dismissError(err.id)}
                className="w-5 h-5 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 flex items-center justify-center -mr-1 -mt-1"
                title="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
