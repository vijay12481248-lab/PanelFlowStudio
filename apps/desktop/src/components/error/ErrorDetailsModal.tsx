import React, { useState } from "react";
import {
  AlertTriangle,
  AlertOctagon,
  Info,
  X,
  Copy,
  Check,
  RotateCcw,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Terminal,
  ShieldAlert,
} from "lucide-react";
import type { AppError } from "../../types/error";
import { JobActivityCard } from "../JobActivityPanel";
import { useError } from "../../context/ErrorContext";
import type { Job } from "@panelflow/shared-types";

interface ErrorDetailsModalProps {
  error: AppError | null;
  onClose: () => void;
  onDismissAlert?: (id: string) => void;
  onRetryJob?: (jobId: string) => Promise<boolean>;
}

export const ErrorDetailsModal: React.FC<ErrorDetailsModalProps> = ({
  error,
  onClose,
  onDismissAlert,
  onRetryJob,
}) => {
  const [copied, setCopied] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [showRawJson, setShowRawJson] = useState(true);
  const { cancelJob, engineHealthy } = useError();

  if (!error) return null;
  const liveJob = typeof error.rawDetails === "object" && error.rawDetails?.job_id ? error.rawDetails as Job : null;

  const handleCopyDetails = async () => {
    try {
      const diagnosticReport = [
        `# PanelFlow Studio — Error Diagnostic Report`,
        `**Timestamp**: ${new Date(error.timestamp).toLocaleString()} (${error.timestamp})`,
        `**Title**: ${error.title}`,
        `**Severity**: ${error.severity.toUpperCase()}`,
        `**Source**: ${error.source}`,
        error.jobId ? `**Job ID**: \`${error.jobId}\`` : null,
        error.projectId ? `**Project ID**: \`${error.projectId}\`` : null,
        error.jobType ? `**Job Type**: \`${error.jobType}\`` : null,
        error.statusCode ? `**HTTP Status**: ${error.statusCode}` : null,
        ``,
        `## Error Message`,
        error.message,
        ``,
        error.suggestions && error.suggestions.length > 0
          ? [
              `## Recommended Troubleshooting Actions`,
              ...error.suggestions.map((s, i) => `${i + 1}. ${s}`),
              ``,
            ].join("\n")
          : null,
        error.stack
          ? [
              `## Stack Trace`,
              "```",
              error.stack,
              "```",
              "",
            ].join("\n")
          : null,
        error.rawDetails
          ? [
              `## Raw Diagnostic Payload`,
              "```json",
              typeof error.rawDetails === "string"
                ? error.rawDetails
                : JSON.stringify(error.rawDetails, null, 2),
              "```",
            ].join("\n")
          : null,
      ]
        .filter(Boolean)
        .join("\n");

      await navigator.clipboard.writeText(diagnosticReport);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch (e) {
      console.error("Failed to copy error report:", e);
    }
  };

  const handleRetry = async () => {
    if (!error.jobId || !onRetryJob) return;
    setRetrying(true);
    try {
      await onRetryJob(error.jobId);
    } finally {
      setRetrying(false);
    }
  };

  const isSevere = error.severity === "error";
  const isWarning = error.severity === "warning";

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 select-none animate-in fade-in duration-150"
    >
      <div
        className="bg-[#0f121d] border border-[#232b42] rounded-2xl w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col max-h-[88vh] text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#1c2336] bg-[#131726] flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div
              className={`w-9 h-9 rounded-xl flex items-center justify-center ${
                isSevere
                  ? "bg-rose-500/15 border border-rose-500/30 text-rose-400"
                  : isWarning
                  ? "bg-amber-500/15 border border-amber-500/30 text-amber-400"
                  : "bg-indigo-500/15 border border-indigo-500/30 text-indigo-400"
              }`}
            >
              {isSevere ? (
                <AlertOctagon className="w-5 h-5 text-rose-400" />
              ) : isWarning ? (
                <AlertTriangle className="w-5 h-5 text-amber-400" />
              ) : (
                <Info className="w-5 h-5 text-indigo-400" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-base text-zinc-100">{error.title}</h3>
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                    isSevere
                      ? "bg-rose-950/80 text-rose-300 border border-rose-800"
                      : isWarning
                      ? "bg-amber-950/80 text-amber-300 border border-amber-800"
                      : "bg-indigo-950/80 text-indigo-300 border border-indigo-800"
                  }`}
                >
                  {error.severity}
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                Occurred {new Date(error.timestamp).toLocaleTimeString()} • Source:{" "}
                <span className="text-zinc-300 font-medium capitalize">
                  {error.source}
                </span>
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-[#1a2133] flex items-center justify-center transition-colors"
            title="Close dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="p-6 overflow-y-auto space-y-5 scrollbar-thin scrollbar-thumb-zinc-800">
          {/* Main Error Message Box */}
          <div
            className={`p-4 rounded-xl border ${
              isSevere
                ? "bg-rose-950/20 border-rose-900/50 text-rose-100"
                : isWarning
                ? "bg-amber-950/20 border-amber-900/50 text-amber-100"
                : "bg-indigo-950/20 border-indigo-900/50 text-indigo-100"
            }`}
          >
            <div className="flex items-start gap-3">
              <ShieldAlert
                className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                  isSevere
                    ? "text-rose-400"
                    : isWarning
                    ? "text-amber-400"
                    : "text-indigo-400"
                }`}
              />
              <div className="space-y-1 flex-1">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
                  Diagnostic Message
                </h4>
                <p className="text-sm font-medium leading-relaxed font-mono whitespace-pre-wrap select-text">
                  {error.message}
                </p>
              </div>
            </div>
          </div>

          {/* Context Metadata Grid */}
          {liveJob && <JobActivityCard job={liveJob} engineHealthy={engineHealthy} onCancel={cancelJob} />}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            {error.jobType && (
              <div className="bg-[#141826] border border-[#21293d] rounded-lg p-2.5 space-y-0.5">
                <div className="text-[10px] text-zinc-500 font-semibold uppercase">
                  Operation / Job
                </div>
                <div className="text-xs text-indigo-300 font-mono font-medium truncate">
                  {error.jobType}
                </div>
              </div>
            )}

            {error.jobId && (
              <div className="bg-[#141826] border border-[#21293d] rounded-lg p-2.5 space-y-0.5">
                <div className="text-[10px] text-zinc-500 font-semibold uppercase">
                  Job ID
                </div>
                <div
                  className="text-xs text-zinc-300 font-mono truncate cursor-pointer hover:text-white"
                  title="Click to copy Job ID"
                  onClick={() => navigator.clipboard.writeText(error.jobId!)}
                >
                  {error.jobId.slice(0, 13)}...
                </div>
              </div>
            )}

            {error.projectId && (
              <div className="bg-[#141826] border border-[#21293d] rounded-lg p-2.5 space-y-0.5">
                <div className="text-[10px] text-zinc-500 font-semibold uppercase">
                  Project ID
                </div>
                <div
                  className="text-xs text-zinc-300 font-mono truncate cursor-pointer hover:text-white"
                  title="Click to copy Project ID"
                  onClick={() => navigator.clipboard.writeText(error.projectId!)}
                >
                  {error.projectId.slice(0, 13)}...
                </div>
              </div>
            )}

            <div className="bg-[#141826] border border-[#21293d] rounded-lg p-2.5 space-y-0.5">
              <div className="text-[10px] text-zinc-500 font-semibold uppercase">
                Timestamp
              </div>
              <div className="text-xs text-zinc-300 font-mono truncate">
                {new Date(error.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </div>
            </div>
          </div>

          {/* Actionable Recovery Suggestions */}
          {error.suggestions && error.suggestions.length > 0 && (
            <div className="bg-[#121624] border border-[#222b42] rounded-xl p-4 space-y-2.5">
              <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                <span>💡</span> Recommended Recovery Actions
              </h4>
              <ul className="space-y-1.5 text-xs text-zinc-300 pl-1">
                {error.suggestions.map((suggestion, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-emerald-400 font-bold flex-shrink-0">
                      {idx + 1}.
                    </span>
                    <span className="leading-relaxed select-text">{suggestion}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Collapsible Technical Details / Raw Stack */}
          {(error.stack || error.rawDetails) && (
            <div className="border border-[#1e263c] rounded-xl overflow-hidden bg-[#0a0c14]">
              <button
                onClick={() => setShowRawJson(!showRawJson)}
                className="w-full px-4 py-2.5 bg-[#121624] hover:bg-[#161c2e] flex items-center justify-between text-left text-xs font-semibold text-zinc-300 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Terminal className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Technical Diagnostics & Stack Trace</span>
                </div>
                {showRawJson ? (
                  <ChevronDown className="w-4 h-4 text-zinc-500" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-zinc-500" />
                )}
              </button>

              {showRawJson && (
                <div className="p-4 space-y-3 font-mono text-xs select-text overflow-x-auto max-h-60 bg-[#080910]">
                  {error.stack && (
                    <div className="space-y-1">
                      <div className="text-[10px] text-zinc-500 font-bold uppercase">
                        Stack Trace:
                      </div>
                      <pre className="text-rose-300 text-[11px] leading-relaxed whitespace-pre-wrap">
                        {error.stack}
                      </pre>
                    </div>
                  )}

                  {error.rawDetails && (
                    <div className="space-y-1">
                      <div className="text-[10px] text-zinc-500 font-bold uppercase">
                        Raw Payload / State:
                      </div>
                      <pre className="text-zinc-400 text-[11px] leading-relaxed whitespace-pre-wrap">
                        {typeof error.rawDetails === "string"
                          ? error.rawDetails
                          : JSON.stringify(error.rawDetails, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-[#1c2336] bg-[#121626] flex items-center justify-between gap-3 flex-shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyDetails}
              className="px-3.5 py-1.5 bg-[#1a2133] hover:bg-[#232c45] text-zinc-200 border border-[#2b3652] rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors shadow-sm"
              title="Copy complete error report to clipboard for debugging"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-emerald-400 font-semibold">
                    Copied to Clipboard!
                  </span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-zinc-400" />
                  <span>Copy Error Details</span>
                </>
              )}
            </button>

            {error.jobId && onRetryJob && (!liveJob || liveJob.status === "FAILED" || liveJob.status === "CANCELLED") && (
              <button
                onClick={handleRetry}
                disabled={retrying}
                className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-md shadow-indigo-600/30 disabled:opacity-50"
              >
                <RotateCcw
                  className={`w-3.5 h-3.5 ${retrying ? "animate-spin" : ""}`}
                />
                <span>{retrying ? "Re-queuing..." : "Retry Job"}</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {onDismissAlert && (
              <button
                onClick={() => {
                  onDismissAlert(error.id);
                  onClose();
                }}
                className="px-3 py-1.5 text-zinc-400 hover:text-zinc-200 text-xs font-medium transition-colors"
              >
                Dismiss Alert
              </button>
            )}
            <button
              onClick={onClose}
              className="px-4 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg text-xs font-semibold transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
