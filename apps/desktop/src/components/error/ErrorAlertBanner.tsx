import React from "react";
import { AlertOctagon, AlertTriangle, Info, X, ChevronRight, Eye } from "lucide-react";
import { useError } from "../../context/ErrorContext";
import type { AppError } from "../../types/error";

export const ErrorAlertBanner: React.FC = () => {
  const { activeErrors, dismissError, clearAllErrors, inspectError, engineHealthy } = useError();
  const oldestId = activeErrors[activeErrors.length - 1]?.id;

  React.useEffect(() => {
    if (!oldestId) return;
    const timer = setTimeout(() => {
      dismissError(oldestId);
    }, 7000);
    return () => clearTimeout(timer);
  }, [oldestId, dismissError]);

  if (activeErrors.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="Error Alerts"
      className="fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-2.5 max-w-sm w-full pointer-events-none select-none"
    >
      {activeErrors.length > 1 && (
        <div className="flex items-center justify-between px-3 py-1 bg-[#0c1433]/90 backdrop-blur-md border border-bad/40 rounded-lg text-xs pointer-events-auto shadow-lg">
          <span className="text-bad font-semibold text-[11px]">
            {activeErrors.length} Active System Alerts
          </span>
          <button
            onClick={clearAllErrors}
            className="text-[11px] text-fg-dim hover:text-fg hover:underline"
          >
            Dismiss All
          </button>
        </div>
      )}

      {activeErrors.slice(0, 3).map((err) => {
        const isSevere = err.severity === "error";
        const isWarning = err.severity === "warning";
        const job = typeof err.rawDetails === "object" && err.rawDetails?.job_id ? err.rawDetails : null;

        return (
          <div
            key={err.id}
            className={`pointer-events-auto rounded-xl border p-3.5 shadow-2xl backdrop-blur-md transition-all duration-200 animate-in slide-in-from-top-2 ${
              isSevere
                ? "bg-[#0c1433]/95 border-bad/60 shadow-bad/50"
                : isWarning
                ? "bg-[#0c1433]/95 border-warn/60 shadow-warn/50"
                : "bg-[#0c1433]/95 border-accent/60 shadow-accent/50"
            }`}
          >
            <div className="flex items-start gap-3">
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  isSevere
                    ? "bg-bad/20 text-bad"
                    : isWarning
                    ? "bg-warn/20 text-warn"
                    : "bg-accent/20 text-info"
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
                  <h4 className="text-xs font-bold text-fg truncate">
                    {err.title}
                  </h4>
                  <span className="text-[10px] text-fg-faint font-mono flex-shrink-0">
                    {new Date(err.timestamp).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>

                <p className="text-[11px] text-fg-dim line-clamp-2 leading-relaxed">
                  {job?.message || err.message}
                </p>

                <div className="flex items-center justify-between pt-1">
                  {job && <span className="text-[10px] text-fg-dim">{job.status} · {Math.round(job.progress * 100)}% · Engine {engineHealthy ? "healthy" : "unavailable"}</span>}
                </div>
                {job && <p className="text-[10px] text-fg-faint break-all font-mono">{job.job_id}</p>}
                {job && <p className="text-[10px] text-fg-dim">Started: {job.started_at ? new Date(/(Z|[+-]\d\d:\d\d)$/.test(job.started_at) ? job.started_at : `${job.started_at}Z`).toLocaleTimeString() : "Waiting"}</p>}
                <div className="flex items-center justify-between pt-1">
                  <button
                    onClick={() => inspectError(err)}
                    className="text-[11px] font-semibold text-info hover:text-info flex items-center gap-1 group transition-colors"
                  >
                    <Eye className="w-3 h-3 text-info" />
                    <span>{err.jobId ? "View Job Details" : "View Error Details"}</span>
                    <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                  </button>

                  <button
                    onClick={() => dismissError(err.id)}
                    className="text-[10px] text-fg-dim hover:text-fg"
                  >
                    Dismiss
                  </button>
                </div>
              </div>

              <button
                onClick={() => dismissError(err.id)}
                className="w-5 h-5 rounded text-fg-dim hover:text-fg hover:bg-flat/50 flex items-center justify-center -mr-1 -mt-1"
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
