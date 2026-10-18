import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from "react";
import type { AppError } from "../types/error";
import { api } from "@panelflow/api-client";
import type { Job } from "@panelflow/shared-types";
import { generateSuggestions } from "./errorSuggestions";

export { generateSuggestions };

interface ErrorContextValue {
  activeErrors: AppError[];
  historyErrors: AppError[];
  selectedError: AppError | null;
  reportError: (
    err: Partial<AppError> & { title: string; message: string }
  ) => string;
  dismissError: (id: string) => void;
  clearAllErrors: () => void;
  inspectError: (err: AppError) => void;
  closeInspector: () => void;
  retryJob: (jobId: string) => Promise<boolean>;
}

const ErrorContext = createContext<ErrorContextValue | undefined>(undefined);

export const ErrorProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [activeErrors, setActiveErrors] = useState<AppError[]>([]);
  const [historyErrors, setHistoryErrors] = useState<AppError[]>([]);
  const [selectedError, setSelectedError] = useState<AppError | null>(null);

  // Track known failed/alerted jobs to prevent duplicate alerts
  const alertedJobStatesRef = useRef<Map<string, string>>(new Map());
  const recentReportKeysRef = useRef<Map<string, number>>(new Map());

  const reportError = useCallback(
    (err: Partial<AppError> & { title: string; message: string }): string => {
      // Deduplicate rapid identical reports (within 4 seconds)
      const dedupKey = `${err.title}::${err.message}::${err.jobId || ""}`;
      const now = Date.now();
      const lastReported = recentReportKeysRef.current.get(dedupKey) || 0;
      if (now - lastReported < 4000) {
        return "";
      }
      recentReportKeysRef.current.set(dedupKey, now);

      const id = err.id || `err_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      const timestamp = err.timestamp || new Date().toISOString();
      const severity = err.severity || "error";
      const source = err.source || "system";

      const suggestions =
        err.suggestions && err.suggestions.length > 0
          ? err.suggestions
          : generateSuggestions(err.title, err.message, err.jobType, err.rawDetails);

      const newError: AppError = {
        id,
        title: err.title,
        message: err.message,
        severity,
        source,
        timestamp,
        jobId: err.jobId,
        projectId: err.projectId,
        jobType: err.jobType,
        statusCode: err.statusCode,
        rawDetails: err.rawDetails,
        stack: err.stack,
        suggestions,
        acknowledged: false,
      };

      console.error("[PanelFlow Error Alert]", newError);

      setActiveErrors((prev) => [newError, ...prev.filter((e) => e.id !== id)]);
      setHistoryErrors((prev) => [newError, ...prev.filter((e) => e.id !== id)].slice(0, 50));

      return id;
    },
    []
  );

  const dismissError = useCallback((id: string) => {
    setActiveErrors((prev) => prev.filter((e) => e.id !== id));
    setHistoryErrors((prev) =>
      prev.map((e) => (e.id === id ? { ...e, acknowledged: true } : e))
    );
  }, []);

  const clearAllErrors = useCallback(() => {
    setActiveErrors([]);
  }, []);

  const inspectError = useCallback((err: AppError) => {
    setSelectedError(err);
  }, []);

  const closeInspector = useCallback(() => {
    setSelectedError(null);
  }, []);

  const retryJob = useCallback(
    async (jobId: string): Promise<boolean> => {
      try {
        await api.retryJob(jobId);
        // Clear active error for this job
        setActiveErrors((prev) => prev.filter((e) => e.jobId !== jobId));
        if (selectedError?.jobId === jobId) {
          setSelectedError(null);
        }
        return true;
      } catch (e: any) {
        reportError({
          title: "Retry Failed",
          message: e.message || "Failed to trigger retry on server.",
          severity: "error",
          source: "job",
          jobId,
          rawDetails: e,
        });
        return false;
      }
    },
    [reportError, selectedError]
  );

  // Global uncaught exception and promise rejection listeners
  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const message =
        reason instanceof Error
          ? reason.message
          : typeof reason === "string"
          ? reason
          : JSON.stringify(reason || "Unhandled Promise Rejection");

      // Ignore standard user cancellations or intentional aborts
      if (message.includes("abort") || message.includes("cancelled")) return;

      reportError({
        title: "Unhandled Asynchronous Error",
        message,
        severity: "error",
        source: "ui",
        stack: reason instanceof Error ? reason.stack : undefined,
        rawDetails: reason,
      });
    };

    const handleError = (event: ErrorEvent) => {
      if (event.message?.includes("ResizeObserver")) return; // benign browser warning
      reportError({
        title: "Client Application Error",
        message: event.message || "An unexpected error occurred in the desktop UI.",
        severity: "error",
        source: "ui",
        stack: event.error?.stack,
        rawDetails: {
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
        },
      });
    };

    window.addEventListener("unhandledrejection", handleUnhandledRejection);
    window.addEventListener("error", handleError);

    return () => {
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
      window.removeEventListener("error", handleError);
    };
  }, [reportError]);

  // Periodic Job Queue Monitor to detect failed/stalled jobs and alert user
  useEffect(() => {
    let mounted = true;

    const checkJobAlerts = async () => {
      try {
        const jobs = await api.listJobs().catch(() => [] as Job[]);
        if (!mounted || !jobs || jobs.length === 0) return;

        for (const job of jobs) {
          const stateKey = `${job.job_id}::${job.status}::${job.error || ""}`;
          const previousState = alertedJobStatesRef.current.get(job.job_id);

          if (job.status === "FAILED" || job.status === "CANCELLED") {
            if (previousState !== stateKey) {
              alertedJobStatesRef.current.set(job.job_id, stateKey);
              const jobTitle = (job.job_type || "TASK").replace(/_/g, " ");
              reportError({
                title: `Job Failed: ${jobTitle}`,
                message:
                  job.error ||
                  job.message ||
                  "The background processing job encountered an error.",
                severity: "error",
                source: "job",
                jobId: job.job_id,
                projectId: job.project_id,
                jobType: job.job_type,
                rawDetails: job,
              });
            }
          } else if (
            job.status === "QUEUED" &&
            job.error &&
            job.error.trim().length > 0
          ) {
            // Retrying backoff state
            if (previousState !== stateKey) {
              alertedJobStatesRef.current.set(job.job_id, stateKey);
              const jobTitle = (job.job_type || "TASK").replace(/_/g, " ");
              reportError({
                title: `Job Warning: ${jobTitle} Retrying`,
                message: `${job.error} (${job.message || "Backoff retry in progress"})`,
                severity: "warning",
                source: "job",
                jobId: job.job_id,
                projectId: job.project_id,
                jobType: job.job_type,
                rawDetails: job,
              });
            }
          } else {
            // Update seen state for running / succeeded
            alertedJobStatesRef.current.set(job.job_id, stateKey);
          }
        }
      } catch {
        // Ignore polling errors
      }
    };

    // Run immediately then poll every 5 seconds
    checkJobAlerts();
    const interval = setInterval(checkJobAlerts, 5000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [reportError]);

  return (
    <ErrorContext.Provider
      value={{
        activeErrors,
        historyErrors,
        selectedError,
        reportError,
        dismissError,
        clearAllErrors,
        inspectError,
        closeInspector,
        retryJob,
      }}
    >
      {children}
    </ErrorContext.Provider>
  );
};

export const useError = (): ErrorContextValue => {
  const context = useContext(ErrorContext);
  if (!context) {
    throw new Error("useError must be used within an ErrorProvider");
  }
  return context;
};
