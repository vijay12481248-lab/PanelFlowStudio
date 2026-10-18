import React, { useState, useRef, useEffect } from "react";
import { Bell, AlertOctagon, AlertTriangle, Eye, CheckCircle2, Trash2 } from "lucide-react";
import { useError } from "../../context/ErrorContext";

export const ErrorNotificationBell: React.FC = () => {
  const { activeErrors, historyErrors, inspectError, clearAllErrors } = useError();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const totalUnread = activeErrors.length;
  const displayErrors = historyErrors.slice(0, 10);

  // Close when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen(!open)}
        className={`relative w-8 h-8 rounded-lg flex items-center justify-center transition-colors border ${
          totalUnread > 0
            ? "bg-rose-950/40 border-rose-800/80 text-rose-300 hover:bg-rose-900/50 hover:text-rose-100 animate-pulse"
            : "bg-[#151928] border-[#242c44] text-zinc-400 hover:text-zinc-200 hover:bg-[#1d2338]"
        }`}
        title={
          totalUnread > 0
            ? `${totalUnread} active error alert${totalUnread > 1 ? "s" : ""}`
            : "System Alerts & Diagnostic History"
        }
      >
        <Bell className="w-4 h-4" />
        {totalUnread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full bg-rose-600 text-white text-[9px] font-black flex items-center justify-center border border-rose-900">
            {totalUnread > 9 ? "9+" : totalUnread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 md:w-96 bg-[#0f121d] border border-[#232b42] rounded-xl shadow-2xl z-50 overflow-hidden text-zinc-100 animate-in fade-in zoom-in-95 duration-100">
          <div className="px-4 py-3 border-b border-[#1c2336] bg-[#131726] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-zinc-200">
                System Alerts & Logs
              </span>
              {totalUnread > 0 && (
                <span className="bg-rose-950 text-rose-300 border border-rose-800 text-[10px] px-1.5 py-0.2 rounded font-bold">
                  {totalUnread} active
                </span>
              )}
            </div>
            {totalUnread > 0 && (
              <button
                onClick={() => {
                  clearAllErrors();
                }}
                className="text-[11px] text-zinc-400 hover:text-zinc-200 flex items-center gap-1"
                title="Dismiss all active alerts"
              >
                <Trash2 className="w-3 h-3" />
                <span>Dismiss all</span>
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto divide-y divide-[#171d2e] scrollbar-thin scrollbar-thumb-zinc-800">
            {displayErrors.length === 0 ? (
              <div className="p-6 text-center text-xs text-zinc-500 space-y-2">
                <CheckCircle2 className="w-6 h-6 mx-auto text-emerald-400 opacity-60" />
                <p>All systems healthy. No errors recorded.</p>
              </div>
            ) : (
              displayErrors.map((err) => {
                const isSevere = err.severity === "error";

                return (
                  <div
                    key={err.id}
                    onClick={() => {
                      inspectError(err);
                      setOpen(false);
                    }}
                    className="p-3 hover:bg-[#151929] cursor-pointer transition-colors space-y-1 group"
                  >
                    <div className="flex items-center justify-between gap-1">
                      <div className="flex items-center gap-1.5 truncate">
                        {isSevere ? (
                          <AlertOctagon className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                        ) : (
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                        )}
                        <span className="text-xs font-semibold text-zinc-200 truncate group-hover:text-indigo-300">
                          {err.title}
                        </span>
                      </div>
                      <span className="text-[10px] text-zinc-500 font-mono flex-shrink-0">
                        {new Date(err.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>

                    <p className="text-[11px] text-zinc-400 line-clamp-1">
                      {err.message}
                    </p>

                    <div className="flex items-center justify-between text-[10px] pt-0.5">
                      <span className="text-zinc-500 capitalize">
                        Source: {err.source}
                      </span>
                      <span className="text-indigo-400 font-medium flex items-center gap-0.5 group-hover:underline">
                        <Eye className="w-2.5 h-2.5" /> Details
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
